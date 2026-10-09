from collections.abc import Sequence
from typing import Any, Literal

from msgspec import Struct

from tapehead.delta import AnyDelta, TextDelta, ToolCallDelta
from tapehead.message import AssistantMessage, SystemMessage, ToolCall, ToolMessage, UserMessage
from tapehead.tool import ToolSpec


def settle(stream: Sequence[AnyDelta]) -> AssistantMessage:
    """把一次模型调用的增量结算成模型消息

    参数
    - stream: 按到达顺序排列的增量
    """

    text = "".join(delta.text for delta in stream if isinstance(delta, TextDelta))
    calls: dict[str, ToolCall] = {}

    for delta in stream:
        if isinstance(delta, ToolCallDelta):
            call = calls.setdefault(delta.id, ToolCall(id=delta.id, name="", arguments=""))
            call.name = delta.name or call.name
            call.arguments += delta.arguments

    return AssistantMessage(content=text, tool_calls=list(calls.values()))


class Event(Struct, tag_field="type"):
    """磁带上的一件事实, 带 message 的事件进入模型上下文"""


class Configured(Event, tag="configured"):
    """宿主设定了系统提示和工具, 只在变化时落带, 系统提示为空时不进上下文"""

    message: SystemMessage
    tools: list[ToolSpec] = []


class Prompted(Event, tag="prompted"):
    """用户发出输入, 一轮由此开始"""

    message: UserMessage


class Generated(Event, tag="generated"):
    """模型完成一次调用, message 是结果, stream 是过程, 二者必须一致"""

    stream: list[AnyDelta]
    message: AssistantMessage

    def __post_init__(self) -> None:
        if settle(self.stream) != self.message:
            raise ValueError("message 与 stream 结算的结果不一致")


class Aborted(Event, tag="aborted"):
    """模型调用没有完成, 已收到的增量只记账, 不进上下文"""

    stream: list[AnyDelta]
    error: str


class Dispatched(Event, tag="dispatched"):
    """harness 开始执行一次工具调用"""

    call_id: str


class Returned(Event, tag="returned"):
    """工具返回结果"""

    message: ToolMessage


type YieldReason = Literal["completed", "cancelled", "failed", "interrupted", "max_steps"]


class Yielded(Event, tag="yielded"):
    """agent 把控制权交还用户, 一轮由此结束, interrupted 只由修复方补写"""

    reason: YieldReason


class Anchored(Event, tag="anchored"):
    """打下回放起点, message 是代替之前全部历史的摘要"""

    name: str
    message: UserMessage | None = None
    state: dict[str, Any] = {}


class Custom(Event, tag="custom"):
    """扩展事件的统一出口, 内核只认 name 和 ignorable

    ignorable 为 False 时, 不认识 name 的读者必须拒绝回放
    """

    name: str
    data: dict[str, Any] = {}
    ignorable: bool = False


type AnyEvent = Configured | Prompted | Generated | Aborted | Dispatched | Returned | Yielded | Anchored | Custom
