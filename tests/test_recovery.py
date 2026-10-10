import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.event import Dispatched
from tapehead.head import Head
from tapehead.media.fs import FsSilo
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, ToolMessage
from tapehead.tapes.label import Label
from tapehead.tool import ToolSpec, tool


class Killed(BaseException):
    """模拟进程被打断, 继承 BaseException 所以不会被当成工具失败"""


@tool
def deploy() -> str:
    """部署服务"""

    raise Killed


class Gateway:
    """像真实网关一样, 拒绝带着没有结果的工具调用的上下文"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        answered = {m.call_id for m in messages if isinstance(m, ToolMessage)}
        for message in messages:
            if isinstance(message, AssistantMessage):
                for call in message.tool_calls:
                    assert call.id in answered, f"工具调用 {call.id} 没有结果"
        if messages[-1].content == "部署":
            yield ToolCallDelta(id="call-1", name="deploy", arguments="{}")
        else:
            yield TextDelta(text="好的")


@pytest.mark.asyncio
async def test_conversation_continues_after_an_interrupted_tool(tmp_path: Path) -> None:
    """部署到一半被打断, 第二天重新打开同一盘带接着聊, 模型不会拿到悬空的工具调用"""

    tape = await FsSilo(tmp_path).create(Label(name="chat", created_at=time.time()))
    with pytest.raises(Killed):
        async for _ in Head(Gateway(), [deploy]).run(tape, "部署"):
            pass
    await tape.close()

    tape = await FsSilo(tmp_path).open("chat")
    async for _ in Head(Gateway(), [deploy]).run(tape, "你还在吗"):
        pass
    await tape.close()


@pytest.mark.asyncio
async def test_a_frame_cut_off_mid_write_does_not_lose_the_tape(tmp_path: Path) -> None:
    """进程在写一帧的中途崩溃, 留下没有换行的残缺尾行, 重新打开时截掉它, 之前的帧完好, 还能接着录"""

    tape = await FsSilo(tmp_path).create(Label(name="chat", created_at=time.time()))
    async for _ in Head(Gateway()).run(tape, "你好"):
        pass
    await tape.close()
    recorded = (tmp_path / "chat.jsonl").read_bytes()
    (tmp_path / "chat.jsonl").write_bytes(recorded + b'{"recorded_at":0,"event":{"type":"pro')

    tape = await FsSilo(tmp_path).open("chat")
    assert len(await tape.read()) == len(recorded.splitlines())
    async for _ in Head(Gateway()).run(tape, "还在吗"):
        pass
    await tape.close()

    tape = await FsSilo(tmp_path).open("chat")
    assert [type(frame.event).__name__ for frame in await tape.read()][-3:] == ["Prompted", "Generated", "Yielded"]
    await tape.close()


class Watched(MemTape):
    """记下每次 flush 时已经录了多少帧"""

    def __init__(self) -> None:
        super().__init__(Label(name="chat", created_at=time.time()))
        self.flushed: list[int] = []

    async def flush(self) -> None:
        self.flushed.append(len(self.frames))


@pytest.mark.asyncio
async def test_a_tool_runs_only_after_its_dispatch_is_durable() -> None:
    """工具的副作用发生时, 派发记录已经落盘, 崩溃后修复不会把执行过的工具当成没执行"""

    tape = Watched()
    seen: list[list[int]] = []

    @tool
    def ping() -> str:
        """探活"""

        seen.append(list(tape.flushed))
        return "pong"

    class Pings:
        async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
            if isinstance(messages[-1], ToolMessage):
                yield TextDelta(text="通")
            else:
                yield ToolCallDelta(id="call-1", name="ping", arguments="{}")

    async for _ in Head(Pings(), [ping]).run(tape, "ping"):
        pass

    frames = await tape.read()
    dispatched = next(i for i, frame in enumerate(frames) if isinstance(frame.event, Dispatched))
    assert seen == [[dispatched + 1]]
    assert tape.flushed[-1] == len(frames)
