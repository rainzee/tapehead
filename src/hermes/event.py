from typing import Any, Literal

from msgspec import Struct

from hermes.delta import AnyDelta
from hermes.message import Message


class Event(Struct, tag=True):
    """还没落带的一件事实"""


class TurnStart(Event):
    """一轮对话开始"""

    turn: int


type TurnEndReason = Literal["completed", "cancelled", "failed", "interrupted"]


class TurnEnd(Event):
    """一轮对话结束, interrupted 只由修复方补写"""

    turn: int
    reason: TurnEndReason


class StepStart(Event):
    """一个 step 开始"""

    turn: int
    step: int


class StepEnd(Event):
    """一个 step 结束"""

    turn: int
    step: int


class Usage(Struct):
    """一次模型调用的 token 用量"""

    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


class SystemMessage(Event):
    """系统提示"""

    turn: int
    step: int
    message: Message


class UserMessage(Event):
    """用户消息"""

    message: Message


class AssistantMessage(Event):
    """一次模型调用结算后的消息, 连同原始流一起落带"""

    turn: int
    step: int
    message: Message
    stream: list[AnyDelta] = []
    usage: Usage | None = None
    interrupted: bool = False


class ToolCall(Event):
    """一次工具调用的派发记录"""

    turn: int
    step: int
    call_id: str
    name: str
    arguments: str


class ToolResult(Event):
    """工具执行结果"""

    turn: int
    step: int
    message: Message
    is_error: bool = False


class Anchor(Event):
    """磁带上的记号, 回放从最后一个记号开始, summary 代替它之前的全部历史"""

    name: str
    summary: str | None = None
    state: dict[str, Any] = {}


class Custom(Event):
    """扩展事件的统一出口, 内核只认 name 和 ignorable

    ignorable 为 False 时, 不认识 name 的读者必须拒绝回放
    """

    name: str
    data: dict[str, Any] = {}
    ignorable: bool = False


type SurfaceEvent = SystemMessage | UserMessage | AssistantMessage | ToolResult | Anchor
type AnyEvent = (
    TurnStart
    | TurnEnd
    | StepStart
    | StepEnd
    | SystemMessage
    | UserMessage
    | AssistantMessage
    | ToolCall
    | ToolResult
    | Anchor
    | Custom
)
