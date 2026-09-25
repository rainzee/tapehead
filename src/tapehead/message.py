from typing import Literal

from msgspec import Struct


class ToolUse(Struct):
    """模型消息里携带的一次工具调用请求"""

    call_id: str
    name: str
    arguments: str


class Message(Struct):
    """模型可见的一条消息"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_uses: list[ToolUse] = []
    tool_call_id: str | None = None
