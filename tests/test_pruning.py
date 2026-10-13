import time
from collections.abc import AsyncIterator

import pytest

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.event import Aborted, Compacted, Generated, Pruned, Returned, Yielded
from tapehead.head import Head
from tapehead.kit.tool import tool
from tapehead.media.mem import MemTape
from tapehead.message import Message, ToolMessage, UserMessage
from tapehead.provider import ContextOverflow
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label
from tapehead.tapes.play import Context, cuts, play
from tapehead.testing import ScriptedProvider
from tapehead.tool import ToolSpec

LOG = "timeout path=/api/orders\n" * 200


@tool
def grep_logs(pattern: str) -> str:
    """在服务日志里搜索"""

    return LOG


def searches_then_answers(turns: int) -> ScriptedProvider:
    """第一轮先搜日志再作答, 之后每轮直接作答"""

    return ScriptedProvider(
        [ToolCallDelta(id="call-1", name="grep_logs", arguments='{"pattern": "timeout"}')],
        *([TextDelta(text="最常见的是 /api/orders")] for _ in range(turns)),
    )


def pruned(target: int, content: str = "[已裁剪] 200 行 timeout 日志") -> Pruned:
    return Pruned(target=target, message=ToolMessage(call_id="call-1", content=content))


def returned_at(frames: list[Frame]) -> int:
    return next(i for i, frame in enumerate(frames) if isinstance(frame.event, Returned))


def replayed(frames: list[Frame], inputs: list[Context]) -> bool:
    """磁带上每一次模型调用都能从它之前的前缀精确还原当时的输入"""

    calls = [i for i, frame in enumerate(frames) if isinstance(frame.event, Generated | Aborted)]

    return [play(frames[:i]) for i in calls] == inputs


@pytest.mark.asyncio
async def test_the_host_prunes_a_tool_result_between_turns() -> None:
    """宿主在两轮之间把旧的日志输出换成占位, 之后的调用只看到占位, 之前的调用仍按原文精确重放, 再裁一次以最后一次为准"""

    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = searches_then_answers(3)
    head = Head(provider, [grep_logs])

    async for _ in head.run(tape, "日志里最常见的 timeout 路径"):
        pass
    target = returned_at(await tape.read())
    await head.prune(tape, pruned(target))
    async for _ in head.run(tape, "再确认一下"):
        pass
    await head.prune(tape, pruned(target, "[已裁剪]"))
    async for _ in head.run(tape, "好的"):
        pass

    assert [call.messages[2] for call in provider.calls[1:]] == [
        ToolMessage(call_id="call-1", content=LOG),
        ToolMessage(call_id="call-1", content="[已裁剪] 200 行 timeout 日志"),
        ToolMessage(call_id="call-1", content="[已裁剪]"),
    ]
    assert replayed(await tape.read(), provider.calls)


@pytest.mark.asyncio
async def test_an_illegal_prune_is_refused() -> None:
    """目标不是工具结果, call_id 对不上, 越界, 或已被压缩遮住, 裁剪都不会落带, 一批里有一条不合法则整批不落"""

    tape = MemTape(Label(name="chat", created_at=time.time()))
    head = Head(searches_then_answers(1), [grep_logs])
    async for _ in head.run(tape, "日志里最常见的 timeout 路径"):
        pass
    frames = await tape.read()
    target = returned_at(frames)

    for edit, message in (
        (pruned(0), "只能裁剪 Returned"),
        (Pruned(target=target, message=ToolMessage(call_id="call-x", content="?")), "不一致"),
        (pruned(-1), "不在当前回放的范围"),
    ):
        with pytest.raises(ValueError, match=message):
            await head.prune(tape, pruned(target), edit)
    assert await tape.read() == frames

    await head.compact(tape, Compacted(start=cuts(frames)[-1], message=UserMessage(content="之前的对话摘要: 查过日志")))
    with pytest.raises(ValueError, match="不在当前回放的范围"):
        await head.prune(tape, pruned(target))


@pytest.mark.asyncio
async def test_an_oversized_result_is_pruned_before_the_model_sees_it() -> None:
    """宿主给出裁剪钩子, 过大的日志输出录下后紧接着被裁剪, 模型从没见过原文, 原文仍在带上"""

    async def pruner(message: ToolMessage) -> str | None:
        return f"[已裁剪] 输出共 {len(message.content)} 字符" if len(message.content) > 1000 else None

    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = searches_then_answers(1)
    async for _ in Head(provider, [grep_logs], pruner=pruner).run(tape, "日志里最常见的 timeout 路径"):
        pass

    frames = await tape.read()
    target = returned_at(frames)
    assert frames[target].event == Returned(message=ToolMessage(call_id="call-1", content=LOG))
    placeholder = ToolMessage(call_id="call-1", content=f"[已裁剪] 输出共 {len(LOG)} 字符")
    assert frames[target + 1].event == Pruned(target=target, message=placeholder)
    assert provider.calls[1].messages[-1] == placeholder
    assert replayed(frames, provider.calls)


class Budget:
    """上下文窗口只容得下 limit 个字符, 超出时像真实服务端一样报告溢出, 先搜日志再作答, 并记下每次收到的输入"""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.calls: list[Context] = []

    async def stream(self, messages: list[Message], tools: list[ToolSpec]) -> AsyncIterator[Delta]:
        self.calls.append(Context(messages=list(messages), tools=list(tools)))
        if sum(len(message.content) for message in messages) > self.limit:
            raise ContextOverflow("maximum context length")
        if isinstance(messages[-1], UserMessage):
            yield ToolCallDelta(id="call-1", name="grep_logs", arguments='{"pattern": "timeout"}')
        else:
            yield TextDelta(text="最常见的是 /api/orders")


@pytest.mark.asyncio
async def test_an_overflow_from_one_huge_result_is_rescued_by_pruning() -> None:
    """单个工具结果就超出窗口, 压缩切不掉它, 压缩器改为裁剪它, 这一轮在重试后正常完成, 每次调用仍能精确重放"""

    async def compactor(frames: list[Frame]) -> list[Compacted | Pruned]:
        return [
            Pruned(target=i, message=ToolMessage(call_id=frame.event.message.call_id, content="[已裁剪] 日志过长"))
            for i, frame in enumerate(frames)
            if isinstance(frame.event, Returned) and len(frame.event.message.content) > 1000
        ]

    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = Budget(limit=1000)
    async for _ in Head(provider, [grep_logs], compactor=compactor).run(tape, "日志里最常见的 timeout 路径"):
        pass

    frames = await tape.read()
    assert [type(frame.event) for frame in frames[-5:]] == [Returned, Aborted, Pruned, Generated, Yielded]
    assert frames[-1].event == Yielded(reason="completed")
    assert replayed(frames, provider.calls)
