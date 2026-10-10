from collections.abc import Sequence
from typing import Literal

from msgspec import Struct

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.message import AssistantMessage, SystemMessage, ToolCall, ToolMessage, UserMessage
from tapehead.tool import ToolSpec


def settle(stream: Sequence[Delta]) -> AssistantMessage:
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


class Configured(Struct, tag="configured"):
    """宿主设定了系统提示和工具, 只在变化时落带, 系统提示为空时不进上下文"""

    message: SystemMessage
    tools: list[ToolSpec] = []


class Prompted(Struct, tag="prompted"):
    """用户发出输入, 一轮由此开始"""

    message: UserMessage


class Generated(Struct, tag="generated"):
    """模型完成一次调用, message 是结果, stream 是过程, 二者必须一致"""

    stream: list[Delta]
    message: AssistantMessage

    def __post_init__(self) -> None:
        if settle(self.stream) != self.message:
            raise ValueError("message 与 stream 结算的结果不一致")


class Aborted(Struct, tag="aborted"):
    """模型调用没有完成, 已收到的增量只记账, 不进上下文"""

    stream: list[Delta]
    error: str


class Dispatched(Struct, tag="dispatched"):
    """harness 开始执行一次工具调用"""

    call_id: str


class Returned(Struct, tag="returned"):
    """工具返回结果"""

    message: ToolMessage


type YieldReason = Literal["completed", "cancelled", "failed", "interrupted", "max_steps"]


class Yielded(Struct, tag="yielded"):
    """agent 把控制权交还用户, 一轮由此结束, interrupted 只由修复方补写"""

    reason: YieldReason


class Compacted(Struct, tag="compacted"):
    """位置 start 之前的历史由摘要 message 代替, 已录的帧不变, 只改变回放

    message 必须能独立代替 [0, start) 的全部历史, 包括之前的摘要, 是与模型提供方无关的纯文本
    """

    start: int
    message: UserMessage


type Event = Configured | Prompted | Generated | Aborted | Dispatched | Returned | Yielded | Compacted
