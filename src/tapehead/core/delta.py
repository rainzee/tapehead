from collections.abc import Sequence

from msgspec import Struct

from tapehead.core.message import AssistantMessage, ToolCall


class TextDelta(Struct, tag="text"):
    """正文增量"""

    chunk: str


class ReasoningDelta(Struct, tag="reasoning"):
    """推理增量"""

    chunk: str


class ToolCallDelta(Struct, tag="tool_call"):
    """工具调用增量, chunk 是参数 JSON 的一段, 同一 id 的片段按序拼接"""

    id: str
    name: str | None = None
    chunk: str = ""


class UsageDelta(Struct, tag="usage"):
    """一次模型调用的 token 用量"""

    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


type Delta = TextDelta | ReasoningDelta | ToolCallDelta | UsageDelta


def settle(stream: Sequence[Delta]) -> AssistantMessage:
    """把一次模型调用的增量结算成模型消息

    参数
    - stream: 按到达顺序排列的增量
    """

    content = "".join(delta.chunk for delta in stream if isinstance(delta, TextDelta))
    reasoning = "".join(delta.chunk for delta in stream if isinstance(delta, ReasoningDelta))
    calls: dict[str, ToolCall] = {}

    for delta in stream:
        if isinstance(delta, ToolCallDelta):
            call = calls.setdefault(delta.id, ToolCall(id=delta.id, name="", arguments=""))
            call.name = delta.name or call.name
            call.arguments += delta.chunk

    return AssistantMessage(content=content, reasoning=reasoning, tool_calls=list(calls.values()))
