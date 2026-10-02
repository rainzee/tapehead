import json
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Annotated, Any

import pytest
from msgspec import Meta

from tapehead.delta import AnyDelta, TextDelta, ToolUseDelta
from tapehead.event import ToolResult, TurnEnd
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import Message
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.play import play
from tapehead.tool import Tool, tool


@tool
async def read_file(path: Annotated[str, Meta(description="文件路径")]) -> str:
    """读取一个 UTF-8 文本文件"""

    return Path(path).read_text(encoding="utf-8")


class ReadsThenAnswers:
    """被要求读文件时先请求工具, 拿到工具结果后复述"""

    async def stream(self, messages: list[Message], tools: Sequence[Tool[Any]]) -> AsyncIterator[AnyDelta]:
        last = messages[-1]
        if last.role == "tool":
            yield TextDelta(text=f"工具返回: {last.content}")
            return
        arguments = json.dumps({"path": last.content.removeprefix("读一下 ")})
        half = len(arguments) // 2
        yield ToolUseDelta(call_id="call-1", name="read_file", arguments=arguments[:half])
        yield ToolUseDelta(call_id="call-1", arguments=arguments[half:])


@pytest.mark.asyncio
async def test_agent_reads_a_file_before_answering(tmp_path: Path) -> None:
    """用户让 agent 读一个文件, 模型先请求调用工具, 拿到文件内容后才作答"""

    note = tmp_path / "note.txt"
    note.write_text("明天下午三点开会", encoding="utf-8")
    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))

    async for _ in await Head(ReadsThenAnswers(), [read_file]).run(tape, f"读一下 {note}"):
        pass

    messages = play(await tape.read())
    assert [m.role for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[1].tool_uses[0].name == "read_file"
    assert messages[2].tool_call_id == messages[1].tool_uses[0].call_id
    assert messages[3].content == "工具返回: 明天下午三点开会"


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_to_the_model(tmp_path: Path) -> None:
    """用户让 agent 读一个不存在的文件, 工具失败不会中断这一轮, 失败交还给模型"""

    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))

    async for _ in await Head(ReadsThenAnswers(), [read_file]).run(tape, f"读一下 {tmp_path / 'missing.txt'}"):
        pass

    events = [frame.event for frame in await tape.read()]
    results = [event for event in events if isinstance(event, ToolResult)]
    assert [r.is_error for r in results] == [True]
    assert "FileNotFoundError" in results[0].message.content
    assert isinstance(events[-1], TurnEnd) and events[-1].reason == "completed"
    assert play(await tape.read())[-1].content.startswith("工具返回: FileNotFoundError")
