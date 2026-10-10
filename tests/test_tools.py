import asyncio
import json
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Annotated

import pytest
from msgspec import Meta

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.event import Generated, Returned, Yielded
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, ToolMessage, UserMessage
from tapehead.tapes.label import Label
from tapehead.tapes.play import play
from tapehead.tool import ToolSpec, tool


@tool
async def read_file(path: Annotated[str, Meta(description="文件路径")]) -> str:
    """读取一个 UTF-8 文本文件"""

    return Path(path).read_text(encoding="utf-8")


class ReadsThenAnswers:
    """被要求读文件时先请求工具, 拿到工具结果后复述"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            yield TextDelta(text=f"工具返回: {last.content}")
            return
        arguments = json.dumps({"path": last.content.removeprefix("读一下 ")})
        half = len(arguments) // 2
        yield ToolCallDelta(id="call-1", name="read_file", arguments=arguments[:half])
        yield ToolCallDelta(id="call-1", arguments=arguments[half:])


@pytest.mark.asyncio
async def test_agent_reads_a_file_before_answering(tmp_path: Path) -> None:
    """用户让 agent 读一个文件, 模型先请求调用工具, 拿到文件内容后才作答"""

    note = tmp_path / "note.txt"
    note.write_text("明天下午三点开会", encoding="utf-8")
    tape = MemTape(Label(name="chat", created_at=time.time()))

    async for _ in Head(ReadsThenAnswers(), [read_file]).run(tape, f"读一下 {note}"):
        pass

    messages = play(await tape.read()).messages
    match messages:
        case [
            UserMessage(),
            AssistantMessage(tool_calls=[call]),
            ToolMessage(call_id=call_id),
            AssistantMessage(content=answer),
        ]:
            assert call.name == "read_file"
            assert call_id == call.id
        case _:
            pytest.fail(f"消息序列不符合预期: {messages}")
    assert answer == "工具返回: 明天下午三点开会"


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_to_the_model(tmp_path: Path) -> None:
    """用户让 agent 读一个不存在的文件, 工具失败不会中断这一轮, 失败交还给模型"""

    tape = MemTape(Label(name="chat", created_at=time.time()))

    async for _ in Head(ReadsThenAnswers(), [read_file]).run(tape, f"读一下 {tmp_path / 'missing.txt'}"):
        pass

    events = [frame.event for frame in await tape.read()]
    results = [event for event in events if isinstance(event, Returned)]
    assert [r.message.is_error for r in results] == [True]
    assert "FileNotFoundError" in results[0].message.content
    assert isinstance(events[-1], Yielded) and events[-1].reason == "completed"
    assert play(await tape.read()).messages[-1].content.startswith("工具返回: FileNotFoundError")


class NeverSatisfied:
    """每一步都再请求一次工具, 永远不给出最终回答"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        yield ToolCallDelta(id="call-1", name="ping", arguments="{}")


@tool
def ping() -> str:
    """探活"""

    return "pong"


@pytest.mark.asyncio
async def test_a_model_stuck_on_tools_is_stopped() -> None:
    """模型卡在反复请求工具上, 这一轮在步数上限处收尾, 磁带上不留下没闭合的轮次"""

    tape = MemTape(Label(name="chat", created_at=time.time()))

    async def drain() -> None:
        async for _ in Head(NeverSatisfied(), [ping], max_steps=3).run(tape, "ping 到天荒地老"):
            pass

    await asyncio.wait_for(drain(), timeout=5)

    events = [frame.event for frame in await tape.read()]
    assert sum(isinstance(event, Generated) for event in events) == 3
    assert isinstance(events[-1], Yielded) and events[-1].reason == "max_steps"
