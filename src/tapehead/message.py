from msgspec import Struct


class ToolCall(Struct):
    """工具调用"""

    id: str
    name: str
    arguments: str


class SystemMessage(Struct, tag="system", tag_field="role"):
    """系统消息"""

    content: str


class UserMessage(Struct, tag="user", tag_field="role"):
    """用户消息"""

    content: str


class AssistantMessage(Struct, tag="assistant", tag_field="role"):
    """模型消息"""

    content: str
    tool_calls: list[ToolCall] = []


class ToolMessage(Struct, tag="tool", tag_field="role"):
    """工具消息"""

    call_id: str
    content: str
    is_error: bool = False


type Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage
