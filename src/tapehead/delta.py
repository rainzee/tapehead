from msgspec import Struct


class Delta(Struct, tag=True):
    """不落带的流式增量"""


class TextDelta(Delta):
    """正文增量"""

    text: str


class ReasoningDelta(Delta):
    """推理增量"""

    text: str


class ToolUseDelta(Delta):
    """工具调用请求增量"""

    call_id: str
    name: str | None = None
    arguments: str = ""


type AnyDelta = TextDelta | ReasoningDelta | ToolUseDelta
