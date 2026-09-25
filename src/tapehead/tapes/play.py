from collections.abc import Sequence

from tapehead.event import AnyEvent
from tapehead.message import Message
from tapehead.tapes.frame import Frame


def cue(frames: Sequence[Frame]) -> int:
    """找到回放起点, 即最后一个 Anchor 帧在序列中的下标, 没有时为 0

    参数
    - frames: 按序号排列的帧
    """

    raise NotImplementedError


def play(frames: Sequence[Frame]) -> list[Message]:
    """从回放起点把帧折叠成模型可见的消息

    参数
    - frames: 按序号排列的帧
    """

    raise NotImplementedError


def mend(frames: Sequence[Frame]) -> list[AnyEvent]:
    """为中断的轮次算出补写事件, 由持有写句柄的一方追加, 从不改写已录的帧

    补写包括缺失的错误 ToolResult, 未闭合的 StepEnd, 以及 TurnEnd(reason="interrupted")

    参数
    - frames: 按序号排列的帧
    """

    raise NotImplementedError
