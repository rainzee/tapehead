import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from tapehead.delta import AnyDelta, TextDelta, ToolCallDelta
from tapehead.head import Head
from tapehead.media.fs import FsSilo
from tapehead.message import AssistantMessage, Message, ToolMessage
from tapehead.tapes.header import TapeHeader
from tapehead.tool import Tool, tool


class Killed(BaseException):
    """模拟进程被打断, 继承 BaseException 所以不会被当成工具失败"""


@tool
def deploy() -> str:
    """部署服务"""

    raise Killed


class Gateway:
    """像真实网关一样, 拒绝带着没有结果的工具调用的上下文"""

    async def stream(self, messages: list[Message], tools: Sequence[Tool]) -> AsyncIterator[AnyDelta]:
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

    tape = await FsSilo(tmp_path).create(TapeHeader(name="chat", created_at=time.time()))
    with pytest.raises(Killed):
        async for _ in await Head(Gateway(), [deploy]).run(tape, "部署"):
            pass
    await tape.close()

    tape = await FsSilo(tmp_path).open("chat", "write")
    async for _ in await Head(Gateway(), [deploy]).run(tape, "你还在吗"):
        pass
    await tape.close()
