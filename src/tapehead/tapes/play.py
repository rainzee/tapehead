from collections.abc import Sequence

from msgspec import Struct

from tapehead.event import Anchored, Configured, Dispatched, Event, Generated, Prompted, Returned, Yielded
from tapehead.message import Message, ToolMessage
from tapehead.tapes.frame import Frame
from tapehead.tool import ToolSpec


class Context(Struct):
    """一次模型调用的输入"""

    messages: list[Message]
    tools: list[ToolSpec]


def configuration(frames: Sequence[Frame]) -> Configured | None:
    """找到当前生效的配置, 即最后一个 Configured, 没有时为 None

    参数
    - frames: 按位置排列的帧
    """

    return next((frame.event for frame in reversed(frames) if isinstance(frame.event, Configured)), None)


def cue(frames: Sequence[Frame]) -> int:
    """找到回放起点, 即最后一个 Anchored 帧的位置, 没有时为 0

    参数
    - frames: 按位置排列的帧
    """

    for i in range(len(frames) - 1, -1, -1):
        if isinstance(frames[i].event, Anchored):
            return i

    return 0


def play(frames: Sequence[Frame]) -> Context:
    """把帧投影成模型调用的输入, 每个 Generated 的输入都等于它之前的前缀的投影

    带 message 的事件进入上下文, 不带的只记账
    配置取整盘带上最后一个 Configured, 消息从回放起点开始收集

    参数
    - frames: 按位置排列的帧
    """

    configured = configuration(frames)
    messages: list[Message] = []
    if configured is not None and configured.message.content:
        messages.append(configured.message)

    for frame in frames[cue(frames) :]:
        match frame.event:
            case Prompted(message=message) | Generated(message=message) | Returned(message=message):
                messages.append(message)
            case Anchored(message=message) if message is not None:
                messages.append(message)

    return Context(messages=messages, tools=configured.tools if configured is not None else [])


def mend(frames: Sequence[Frame]) -> list[Event]:
    """为中断的一轮算出补写事件, 由持有写句柄的一方追加, 从不改写已录的帧

    模型请求过但没有结果的工具调用补一个出错的 Returned, 按是否派发区分原因, 最后补 Yielded(interrupted)

    参数
    - frames: 按位置排列的帧
    """

    for start in range(len(frames) - 1, -1, -1):
        if isinstance(frames[start].event, Prompted):
            break
    else:
        return []

    tail = [frame.event for frame in frames[start:]]
    if any(isinstance(event, Yielded) for event in tail):
        return []

    requested = [call.id for event in tail if isinstance(event, Generated) for call in event.message.tool_calls]
    dispatched = {event.call_id for event in tail if isinstance(event, Dispatched)}
    returned = {event.message.call_id for event in tail if isinstance(event, Returned)}
    fixes: list[Event] = [
        Returned(
            message=ToolMessage(
                call_id=call_id,
                content="工具执行被中断, 结果未知" if call_id in dispatched else "工具没有执行",
                is_error=True,
            )
        )
        for call_id in requested
        if call_id not in returned
    ]

    return [*fixes, Yielded(reason="interrupted")]
