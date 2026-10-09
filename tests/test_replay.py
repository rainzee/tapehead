import json
import shutil
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from msgspec import to_builtins

from tapehead.delta import Delta, TextDelta, ToolCallDelta, UsageDelta
from tapehead.event import Aborted, Dispatched, Generated, Prompted, Returned, Yielded, settle
from tapehead.head import Head
from tapehead.media.fs import FsSilo
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, ToolMessage, UserMessage
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.play import Context, mend, play
from tapehead.tool import ToolSpec, tool


@tool
def lookup(city: str) -> str:
    """查询城市天气"""

    return f"{city}: 晴"


class Flaky:
    """记下每次收到的输入, 第一次调用直接失败, 之后先查天气再作答"""

    def __init__(self) -> None:
        self.inputs: list[Context] = []

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        self.inputs.append(Context(messages=list(messages), tools=list(tools)))
        if len(self.inputs) == 1:
            yield TextDelta(text="半截")
            raise ConnectionError("429 rate limited")
        if isinstance(messages[-1], UserMessage):
            yield ToolCallDelta(id="call-1", name="lookup", arguments=json.dumps({"city": "杭州"}))
        else:
            yield TextDelta(text="杭州晴")
        yield UsageDelta(input_tokens=10, output_tokens=2)


@pytest.mark.asyncio
async def test_every_model_call_can_be_replayed_from_the_tape() -> None:
    """模型调用失败一次后用户重问, 磁带上每一次调用, 包括失败的那次, 都能从它之前的前缀精确还原当时的输入"""

    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))
    provider = Flaky()
    head = Head(provider, [lookup], system_prompt="你是天气助手")

    with pytest.raises(ConnectionError):
        async for _ in await head.run(tape, "杭州天气"):
            pass
    async for _ in await head.run(tape, "杭州天气"):
        pass

    frames = await tape.read()
    calls = [i for i, frame in enumerate(frames) if isinstance(frame.event, Generated | Aborted)]
    assert [play(frames[:i]) for i in calls] == provider.inputs
    assert [type(frames[i].event) for i in calls] == [Aborted, Generated, Generated]
    assert all("半截" not in message.content for message in play(frames).messages)


def failed(call_id: str, content: str) -> Returned:
    return Returned(message=ToolMessage(call_id=call_id, content=content, is_error=True))


async def mended(*events: Prompted | Generated | Dispatched | Returned) -> list:
    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))
    await tape.record(*events)

    return mend(await tape.read())


def two_calls() -> Generated:
    stream = [ToolCallDelta(id="a", name="lookup"), ToolCallDelta(id="b", name="lookup")]

    return Generated(stream=stream, message=settle(stream))


@pytest.mark.asyncio
async def test_mend_closes_each_interruption_window() -> None:
    """进程在一轮的不同位置被打断, 修复只为缺结果的调用补写, 并说清是没执行还是执行到一半"""

    prompted = Prompted(message=UserMessage(content="查两个城市"))

    assert await mended(prompted) == [Yielded(reason="interrupted")]
    assert await mended(prompted, two_calls()) == [
        failed("a", "工具没有执行"),
        failed("b", "工具没有执行"),
        Yielded(reason="interrupted"),
    ]
    assert await mended(
        prompted, two_calls(), Dispatched(call_id="a"), Returned(message=ToolMessage(call_id="a", content="晴"))
    ) == [
        failed("b", "工具没有执行"),
        Yielded(reason="interrupted"),
    ]
    assert await mended(prompted, two_calls(), Dispatched(call_id="a")) == [
        failed("a", "工具执行被中断, 结果未知"),
        failed("b", "工具没有执行"),
        Yielded(reason="interrupted"),
    ]


GOLDEN = Path(__file__).parent / "tapes"


@pytest.mark.asyncio
async def test_a_recorded_tape_still_plays_the_same(tmp_path: Path) -> None:
    """录好的样本磁带用当前代码回放, 得出的上下文和录制时一致, 投影规则一变就会在这里暴露"""

    for file in GOLDEN.glob("weather.*"):
        shutil.copy(file, tmp_path)
    tape = await FsSilo(tmp_path).open("weather", "write")

    assert to_builtins(play(await tape.read())) == json.loads((tmp_path / "weather.expected.json").read_text(encoding="utf-8"))
    await tape.close()


@pytest.mark.asyncio
async def test_a_tape_of_an_unknown_format_is_refused(tmp_path: Path) -> None:
    """打开一盘没有格式版本的旧磁带, 直接拒绝, 而不是在解码帧时报出难懂的错误"""

    (tmp_path / "old.header.json").write_text('{"name": "old", "created_at": 0}', encoding="utf-8")
    (tmp_path / "old.jsonl").write_text('{"seq": 0, "time": 0, "event": {"type": "UserMessage"}}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="磁带格式 None 不受支持"):
        await FsSilo(tmp_path).open("old", "write")


def test_a_generation_cannot_disagree_with_its_stream() -> None:
    """模型消息和它的增量流说的不是同一件事时, 这条事实根本构造不出来, 解码磁带时同样被拒绝"""

    with pytest.raises(ValueError, match="不一致"):
        Generated(stream=[TextDelta(text="晴")], message=AssistantMessage(content="雨"))
