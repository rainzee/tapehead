from collections.abc import Sequence

from tapehead import message as msg
from tapehead.event import (
    Anchor,
    AnyEvent,
    AssistantMessage,
    StepEnd,
    StepStart,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from tapehead.tapes.frame import Frame


def cue(frames: Sequence[Frame]) -> int:
    """找到回放起点, 即最后一个 Anchor 帧在序列中的下标, 没有时为 0

    参数
    - frames: 按序号排列的帧
    """

    for i in range(len(frames) - 1, -1, -1):
        if isinstance(frames[i].event, Anchor):
            return i

    return 0


def play(frames: Sequence[Frame]) -> list[msg.Message]:
    """从回放起点把帧折叠成模型可见的消息

    参数
    - frames: 按序号排列的帧
    """

    messages: list[msg.Message] = []
    for frame in frames[cue(frames) :]:
        match frame.event:
            case UserMessage(message=message) | AssistantMessage(message=message) | ToolResult(message=message):
                messages.append(message)

    return messages


def mend(frames: Sequence[Frame]) -> list[AnyEvent]:
    """为中断的轮次算出补写事件, 由持有写句柄的一方追加, 从不改写已录的帧

    补写包括缺失的错误 ToolResult, 未闭合的 StepEnd, 以及 TurnEnd(reason="interrupted")

    参数
    - frames: 按序号排列的帧
    """

    for start in range(len(frames) - 1, -1, -1):
        opened = frames[start].event
        if isinstance(opened, TurnStart):
            break
    else:
        return []

    tail = [frame.event for frame in frames[start:]]
    if any(isinstance(event, TurnEnd) for event in tail):
        return []

    turn = opened.turn
    answered = {
        event.message.call_id for event in tail if isinstance(event, ToolResult) and isinstance(event.message, msg.ToolMessage)
    }
    open_step: int | None = None
    fixes: list[AnyEvent] = []
    for event in tail:
        match event:
            case StepStart(step=step):
                open_step = step
            case StepEnd():
                open_step = None
            case AssistantMessage(step=step, message=msg.AssistantMessage(tool_calls=calls)):
                for call in calls:
                    if call.id not in answered:
                        result = msg.ToolMessage(call_id=call.id, content="工具执行被中断, 没有结果", is_error=True)
                        fixes.append(ToolResult(turn=turn, step=step, message=result))
    if open_step is not None:
        fixes.append(StepEnd(turn=turn, step=open_step))
    fixes.append(TurnEnd(turn=turn, reason="interrupted"))

    return fixes
