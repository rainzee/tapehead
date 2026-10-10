from collections.abc import Sequence

from msgspec import Struct

from tapehead.event import Compacted, Configured, Dispatched, Event, Generated, Prompted, Returned, Yielded
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


def compaction(frames: Sequence[Frame]) -> Compacted | None:
    """找到当前生效的压缩, 即最后一个 Compacted, 没有时为 None

    参数
    - frames: 按位置排列的帧
    """

    return next((frame.event for frame in reversed(frames) if isinstance(frame.event, Compacted)), None)


def cuts(frames: Sequence[Frame]) -> list[int]:
    """列出此刻可以压缩到的位置, 宿主从中挑选, 提交时也按它校验

    位置上是 Prompted 或 Generated, 没有工具调用和它的结果分处两侧, 且在当前生效的切点之后
    保留下来的部分里可以有还没返回的调用, 它们和请求方一起留在上下文里

    参数
    - frames: 按位置排列的帧
    """

    current = compaction(frames)
    floor = current.start if current is not None else 0
    pending: set[str] = set()
    found: list[int] = []

    for i, frame in enumerate(frames):
        if i > floor and not pending and isinstance(frame.event, Prompted | Generated):
            found.append(i)
        match frame.event:
            case Generated(message=message):
                pending.update(call.id for call in message.tool_calls)
            case Returned(message=message):
                pending.discard(message.call_id)

    return found


def admit(frames: Sequence[Frame], compacted: Compacted) -> None:
    """校验一次压缩能否落在这盘带的末尾, 切点不在 cuts 里时拒绝

    参数
    - frames: 按位置排列的帧, 压缩将追加在它们之后
    - compacted: 待提交的压缩
    """

    if compacted.start not in cuts(frames):
        raise ValueError(f"切点 {compacted.start} 不合法, 可以压缩到的位置是 {cuts(frames)}")


def play(frames: Sequence[Frame]) -> Context:
    """把帧投影成模型调用的输入, 每个 Generated 和 Aborted 的输入都等于它之前的前缀的投影

    带 message 的事件进入上下文, 不带的只记账
    配置取前缀里最后一个 Configured, 系统提示始终在最前, 不受压缩影响
    有压缩时, 摘要紧跟系统提示, 之后是从切点起原样保留的消息

    参数
    - frames: 按位置排列的帧
    """

    configured = configuration(frames)
    compacted = compaction(frames)
    messages: list[Message] = []
    if configured is not None and configured.message.content:
        messages.append(configured.message)
    if compacted is not None:
        messages.append(compacted.message)

    for frame in frames[compacted.start if compacted is not None else 0 :]:
        match frame.event:
            case Prompted(message=message) | Generated(message=message) | Returned(message=message):
                messages.append(message)

    return Context(messages=messages, tools=configured.tools if configured is not None else [])


def mend(frames: Sequence[Frame]) -> list[Event]:
    """为中断的一轮算出补写事件, 由调用方追加, 从不改写已录的帧

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
