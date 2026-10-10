import time
from collections.abc import AsyncIterator, Sequence

import pytest

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.event import Aborted, Compacted, Configured, Dispatched, Generated, Prompted, Returned, Yielded, settle
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, ToolMessage, UserMessage
from tapehead.provider import ContextOverflow
from tapehead.providers.openai import overflowed
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label
from tapehead.tapes.play import Context, cuts, play
from tapehead.tool import ToolSpec, tool


def new_tape() -> MemTape:
    return MemTape(Label(name="chat", created_at=time.time()))


class Window:
    """上下文窗口只容得下 limit 条消息, 超出时像真实服务端一样报告溢出, 并记下每次收到的输入"""

    def __init__(self, limit: int = 100) -> None:
        self.limit = limit
        self.inputs: list[Context] = []

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        self.inputs.append(Context(messages=list(messages), tools=list(tools)))
        if len(messages) > self.limit:
            raise ContextOverflow("maximum context length")
        yield TextDelta(text=f"收到 {messages[-1].content}")


def replayed(frames: list[Frame], provider: Window, since: int = 0) -> bool:
    """磁带上从 since 起每一次模型调用, 包括失败的, 都能从它之前的前缀精确还原当时的输入"""

    calls = [i for i, frame in enumerate(frames) if i >= since and isinstance(frame.event, Generated | Aborted)]

    return [play(frames[:i]) for i in calls] == provider.inputs


def latest_prompt(frames: list[Frame]) -> int:
    """宿主的一种策略: 只保留最近一轮, 切在它的用户输入上"""

    return max(i for i in cuts(frames) if isinstance(frames[i].event, Prompted))


def summary(text: str) -> UserMessage:
    return UserMessage(content=f"之前的对话摘要: {text}")


def calls(*ids: str) -> Generated:
    stream: list[Delta] = [ToolCallDelta(id=call_id, name="lookup") for call_id in ids]

    return Generated(stream=stream, message=settle(stream))


def returned(call_id: str) -> Returned:
    return Returned(message=ToolMessage(call_id=call_id, content="晴"))


def answered() -> Generated:
    stream: list[Delta] = [TextDelta(text="都晴")]

    return Generated(stream=stream, message=settle(stream))


@pytest.mark.asyncio
async def test_cuts_never_split_a_call_from_its_result() -> None:
    """切点落在用户输入或模型调用的开头, 不会让工具调用和它的结果分处两侧, 也不会倒退"""

    tape = new_tape()
    await tape.record(
        Prompted(message=UserMessage(content="查两个城市")),
        calls("a", "b"),
        Dispatched(call_id="a"),
        returned("a"),
        Dispatched(call_id="b"),
        returned("b"),
        answered(),
        Yielded(reason="completed"),
        Prompted(message=UserMessage(content="再查一个")),
        calls("c"),
        Dispatched(call_id="c"),
    )

    assert cuts(await tape.read()) == [1, 6, 8, 9]

    await tape.record(Compacted(start=6, message=summary("查了两个城市")))
    assert cuts(await tape.read()) == [8, 9]


@pytest.mark.asyncio
async def test_a_call_left_open_by_a_crash_blocks_every_later_cut() -> None:
    """崩溃留下一个没有结果的调用, 修复之前, 它之后的位置都不能作为切点"""

    tape = new_tape()
    await tape.record(
        Prompted(message=UserMessage(content="查两个城市")),
        calls("a", "b"),
        returned("a"),
        Prompted(message=UserMessage(content="还在吗")),
    )

    assert cuts(await tape.read()) == [1]


@pytest.mark.asyncio
async def test_the_host_compacts_between_turns() -> None:
    """宿主在两轮之间压缩两次, 模型只看到最新的摘要和保留的那一轮, 每一次调用仍能精确重放"""

    tape = new_tape()
    provider = Window()
    head = Head(provider, system_prompt="你是助手")

    for prompt in ("一", "二"):
        async for _ in head.run(tape, prompt):
            pass
    await head.compact(tape, Compacted(start=latest_prompt(await tape.read()), message=summary("说过一")))
    async for _ in head.run(tape, "三"):
        pass
    await head.compact(tape, Compacted(start=latest_prompt(await tape.read()), message=summary("说过一和二")))
    async for _ in head.run(tape, "四"):
        pass

    assert [message.content for message in provider.inputs[-1].messages] == [
        "你是助手",
        "之前的对话摘要: 说过一和二",
        "三",
        "收到 三",
        "四",
    ]
    assert replayed(await tape.read(), provider)


@pytest.mark.asyncio
async def test_a_compaction_at_an_illegal_cut_is_refused() -> None:
    """切点不在 cuts 里, 包括切开调用, 原地不动或倒退, 压缩都不会落带"""

    tape = new_tape()
    await tape.record(
        Prompted(message=UserMessage(content="查两个城市")),
        calls("a", "b"),
        returned("a"),
    )
    head = Head(Window())
    frames = await tape.read()

    for start in (0, 2, 3):
        with pytest.raises(ValueError, match="不合法"):
            await head.compact(tape, Compacted(start=start, message=summary("查天气")))
    assert await tape.read() == frames

    await tape.record(returned("b"))
    await head.compact(tape, Compacted(start=1, message=summary("查天气")))
    with pytest.raises(ValueError, match="不合法"):
        await head.compact(tape, Compacted(start=1, message=summary("查天气")))


@pytest.mark.asyncio
async def test_an_overflow_mid_turn_is_compacted_and_retried() -> None:
    """一轮中途输入超出窗口, 先记下失败的调用, 再压缩并重试, 这一轮正常结束, 两次调用都能精确重放"""

    tape = new_tape()
    provider = Window(limit=4)

    async def compactor(frames: list[Frame]) -> Compacted:
        return Compacted(start=latest_prompt(frames), message=summary("说过一和二"))

    head = Head(provider, system_prompt="你是助手", compactor=compactor)
    for prompt in ("一", "二", "三"):
        async for _ in head.run(tape, prompt):
            pass

    frames = await tape.read()
    assert [type(frame.event) for frame in frames[-5:]] == [Prompted, Aborted, Compacted, Generated, Yielded]
    assert frames[-1].event == Yielded(reason="completed")
    assert [message.content for message in play(frames).messages] == ["你是助手", "之前的对话摘要: 说过一和二", "三", "收到 三"]
    assert replayed(frames, provider)


@pytest.mark.asyncio
async def test_an_overflow_that_compaction_cannot_fix_fails_the_turn() -> None:
    """压缩后仍然溢出, 每次调用只恢复一次, 这一轮以失败结束并把溢出交还宿主"""

    tape = new_tape()
    provider = Window(limit=0)

    async def compactor(frames: list[Frame]) -> Compacted:
        return Compacted(start=latest_prompt(frames), message=summary("说过一"))

    await tape.record(Prompted(message=UserMessage(content="一")), answered(), Yielded(reason="completed"))
    with pytest.raises(ContextOverflow):
        async for _ in Head(provider, compactor=compactor).run(tape, "二"):
            pass

    frames = await tape.read()
    assert [type(frame.event) for frame in frames[-5:]] == [Prompted, Aborted, Compacted, Aborted, Yielded]
    assert frames[-1].event == Yielded(reason="failed")
    assert replayed(frames, provider, since=3)


@pytest.mark.asyncio
async def test_an_overflow_without_a_usable_compaction_fails_the_turn() -> None:
    """没有压缩器, 或者压缩器给出非法切点, 溢出都按失败结束这一轮, 不落任何压缩"""

    async def illegal(frames: list[Frame]) -> Compacted:
        return Compacted(start=0, message=summary("全部"))

    for compactor, error in ((None, ContextOverflow), (illegal, ValueError)):
        tape = new_tape()
        with pytest.raises(error):
            async for _ in Head(Window(limit=0), compactor=compactor).run(tape, "一"):
                pass
        assert [type(frame.event) for frame in await tape.read()] == [Configured, Prompted, Aborted, Yielded]


class Killed(BaseException):
    """模拟进程被打断"""


@tool
def deploy() -> str:
    """部署服务"""

    raise Killed


class Gateway:
    """像真实网关一样, 拒绝没有结果的调用, 也拒绝找不到调用的结果"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        requested = [call.id for m in messages if isinstance(m, AssistantMessage) for call in m.tool_calls]
        answered = [m.call_id for m in messages if isinstance(m, ToolMessage)]
        assert sorted(requested) == sorted(answered), f"调用 {requested} 与结果 {answered} 不配对"
        if messages[-1].content == "部署":
            yield ToolCallDelta(id="call-1", name="deploy", arguments="{}")
        else:
            yield TextDelta(text="好的")


@pytest.mark.asyncio
async def test_a_call_cut_off_by_a_crash_stays_paired_after_compaction() -> None:
    """部署到一半崩溃后宿主压缩, 没有结果的调用留在保留区间里, 修复补上结果后调用和结果仍然配对"""

    tape = new_tape()
    head = Head(Gateway(), [deploy])
    async for _ in head.run(tape, "你好"):
        pass
    with pytest.raises(Killed):
        async for _ in head.run(tape, "部署"):
            pass

    await head.compact(tape, Compacted(start=latest_prompt(await tape.read()), message=summary("打过招呼")))
    async for _ in head.run(tape, "你还在吗"):
        pass

    assert await tape.read() and (await tape.read())[-1].event == Yielded(reason="completed")


def test_only_an_explicit_overflow_is_reported_as_one() -> None:
    """只有服务端明确报告上下文超长时才算溢出, 其他 400 照常失败"""

    assert overflowed(400, '{"error": {"code": "context_length_exceeded"}}')
    assert overflowed(400, '{"message": "This model\'s maximum context length is 32768 tokens."}')
    assert not overflowed(400, '{"message": "invalid tool schema"}')
    assert not overflowed(500, "maximum context length")
