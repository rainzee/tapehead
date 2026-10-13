from msgspec import Struct


class TextDelta(Struct, tag="text"):
    """正文增量"""

    text: str


class ReasoningDelta(Struct, tag="reasoning"):
    """推理增量"""

    text: str


class ToolCallDelta(Struct, tag="tool_call"):
    """工具调用增量, 同一 id 的片段按序拼接"""

    id: str
    name: str | None = None
    arguments: str = ""


class UsageDelta(Struct, tag="usage"):
    """一次模型调用的 token 用量"""

    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


type Delta = TextDelta | ReasoningDelta | ToolCallDelta | UsageDelta
