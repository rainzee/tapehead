import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tapehead.core.delta import Delta, ReasoningDelta, TextDelta, ToolCallDelta, UsageDelta
from tapehead.core.event import (
    Aborted,
    Compacted,
    Configured,
    Dispatched,
    Event,
    Generated,
    Prompted,
    Pruned,
    Returned,
    Yielded,
    settle,
)
from tapehead.core.message import SystemMessage, ToolMessage, UserMessage
from tapehead.core.tape import Frame, Label, Silo, Tape
from tapehead.core.tool import ToolSpec


@dataclass(frozen=True)
class Medium:
    """待检查的一种磁带介质, 对应一份初始为空的存储"""

    connect: Callable[[], Silo | Awaitable[Silo]]
    """每次调用得到一个连到同一份存储的磁带库实例, 非持久介质可以总是返回同一个实例"""

    durable: bool
    """是否持久, 持久介质要求 flush 之后换一个新的库实例也能读回全部帧"""


async def connect(medium: Medium) -> Silo:
    """取得一个连到介质存储的磁带库实例

    参数
    - medium: 介质
    """

    silo = medium.connect()

    return await silo if inspect.isawaitable(silo) else silo


async def reopen(medium: Medium, silo: Silo, name: str) -> Tape:
    """重新打开一盘带, 持久介质换一个新的库实例, 否则沿用原来的库

    参数
    - medium: 介质
    - silo: 原来的库
    - name: 磁带名
    """

    return await (await connect(medium) if medium.durable else silo).open(name)


def expect(condition: bool, message: str) -> None:
    """条件不成立时抛出 AssertionError, 不依赖 assert 语句, 所以不受 python -O 影响

    参数
    - condition: 应当成立的条件
    - message: 失败时的说明
    """

    if not condition:
        raise AssertionError(message)


def new_label(name: str = "conformance") -> Label:
    """检查用的磁带标签"""

    return Label(name=name, created_at=time.time())


def sample_events() -> list[Event]:
    """覆盖每一类事件和每一类增量的样本, 用来检查事件能否原样往返"""

    tools = [ToolSpec(name="lookup", description="查询城市天气", parameters={"type": "object", "properties": {}})]
    calling: list[Delta] = [
        ReasoningDelta(text="先查天气"),
        ToolCallDelta(id="call-1", name="lookup", arguments='{"city": '),
        ToolCallDelta(id="call-1", arguments='"杭州"}'),
        UsageDelta(input_tokens=12, output_tokens=5, cached_tokens=3),
    ]
    answering: list[Delta] = [TextDelta(text="杭州"), TextDelta(text="晴"), UsageDelta(input_tokens=20, output_tokens=2)]

    return [
        Configured(message=SystemMessage(content="你是天气助手"), tools=tools),
        Prompted(message=UserMessage(content="杭州天气")),
        Aborted(stream=[TextDelta(text="半截")], error="ConnectionError: 429 rate limited"),
        Generated(stream=calling, message=settle(calling)),
        Dispatched(call_id="call-1"),
        Returned(message=ToolMessage(call_id="call-1", content="杭州: 晴")),
        Returned(message=ToolMessage(call_id="call-2", content="工具没有执行", is_error=True)),
        Generated(stream=answering, message=settle(answering)),
        Yielded(reason="completed"),
        Compacted(start=1, message=UserMessage(content="之前的对话摘要: 问过杭州天气")),
        Pruned(target=5, message=ToolMessage(call_id="call-1", content="[已裁剪]")),
    ]


async def check_label_means_tape(medium: Medium) -> None:
    """建带之后 list 能看到它的标签, open 得到一盘空带

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    label = new_label()
    tape = await silo.create(label)
    await tape.close()

    expect(label in await silo.list(), f"建带之后 list 看不到标签 {label}")
    tape = await silo.open(label.name)
    expect(tape.label == label, f"open 得到的标签 {tape.label} 与建带时的 {label} 不一致")
    expect(await tape.read() == [], "新建的带 open 之后不是空带")
    await tape.close()


async def check_names_are_unique(medium: Medium) -> None:
    """同名的带第二次 create 抛出 FileExistsError

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    tape = await silo.create(new_label())
    await tape.close()

    try:
        tape = await silo.create(new_label())
    except FileExistsError:
        return
    await tape.close()
    raise AssertionError("同名的带第二次 create 没有抛出 FileExistsError")


async def check_frames_are_contiguous(medium: Medium) -> None:
    """多次 record 之后 read 按录入顺序给出全部帧, read(start, stop) 符合 [start, stop) 的切片语义

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    tape = await silo.create(new_label())
    events = sample_events()
    recorded: list[Frame] = []
    for batch in (events[:1], events[1:4], [], events[4:]):
        recorded += await tape.record(*batch)

    frames = await tape.read()
    expect([frame.event for frame in frames] == events, "read 读回的事件与录入的顺序或内容不一致")
    expect(frames == recorded, "read 读回的帧与 record 返回的帧不一致")
    for start in range(len(frames) + 1):
        for stop in (None, *range(start, len(frames) + 2)):
            got = await tape.read(start, stop)
            expect(got == frames[start:stop], f"read({start}, {stop}) 不符合 [start, stop) 的切片语义")
    await tape.close()


async def check_recording_time(medium: Medium) -> None:
    """录入时间由磁带填写, record 返回的帧带着它, read 读回的与之一致, 且不随位置倒退

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    tape = await silo.create(new_label())
    recorded = await tape.record(*sample_events()[:2])
    recorded += await tape.record(*sample_events()[2:])

    expect(all(isinstance(frame.recorded_at, float) for frame in recorded), "record 返回的帧没有填写录入时间")
    times = [frame.recorded_at for frame in recorded]
    expect(times == sorted(times), f"录入时间随位置倒退: {times}")
    expect(await tape.read() == recorded, "read 读回的录入时间与 record 返回的不一致")
    await tape.close()


async def check_events_round_trip(medium: Medium) -> None:
    """每一类事件, 包括 Generated 的增量流, Compacted 和 Pruned, 录入后关带重开读回都与原来相等

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    label = new_label()
    tape = await silo.create(label)
    events = sample_events()
    await tape.record(*events)
    await tape.close()

    tape = await reopen(medium, silo, label.name)
    got = [frame.event for frame in await tape.read()]
    for i, (expected, actual) in enumerate(zip(events, got, strict=False)):
        expect(actual == expected, f"位置 {i} 的事件没有原样往返: 录入 {expected}, 读回 {actual}")
    expect(len(got) == len(events), f"录入 {len(events)} 帧, 读回 {len(got)} 帧")
    await tape.close()


async def check_flush_is_durable(medium: Medium) -> None:
    """持久介质 flush 之后, 不关带, 换一个新的库实例 open 同名带能读回全部帧, 非持久介质跳过

    参数
    - medium: 待检查的介质
    """

    if not medium.durable:
        return

    silo = await connect(medium)
    label = new_label()
    tape = await silo.create(label)
    recorded = await tape.record(*sample_events())
    await tape.flush()

    other = await (await connect(medium)).open(label.name)
    expect(await other.read() == recorded, "flush 之后换一个库实例读不回全部帧")
    await other.close()
    await tape.close()


async def check_close_flushes(medium: Medium) -> None:
    """close 先 flush, 关带之后重新打开, 帧完整

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    label = new_label()
    tape = await silo.create(label)
    recorded = await tape.record(*sample_events())
    await tape.close()

    tape = await reopen(medium, silo, label.name)
    expect(await tape.read() == recorded, "close 之后重新打开, 帧不完整")
    await tape.close()


async def check_reopen_appends(medium: Medium) -> None:
    """重新打开后接着录, 位置从原长度继续, 不覆盖已录的帧, 也不留空洞

    参数
    - medium: 待检查的介质
    """

    silo = await connect(medium)
    label = new_label()
    events = sample_events()
    tape = await silo.create(label)
    before = await tape.record(*events[:4])
    await tape.close()

    tape = await reopen(medium, silo, label.name)
    after = await tape.record(*events[4:])
    expect(await tape.read(0, len(before)) == before, "重新打开后接着录, 覆盖了原有的帧")
    expect(await tape.read(len(before)) == after, f"重新打开后接着录, 新帧没有从位置 {len(before)} 开始")
    await tape.close()

    tape = await reopen(medium, silo, label.name)
    expect(await tape.read() == before + after, "重新打开后接着录, 再次打开时帧不完整")
    await tape.close()


checks: tuple[Callable[[Medium], Awaitable[None]], ...] = (
    check_label_means_tape,
    check_names_are_unique,
    check_frames_are_contiguous,
    check_recording_time,
    check_events_round_trip,
    check_flush_is_durable,
    check_close_flushes,
    check_reopen_appends,
)
"""介质一致性检查的全集, 宿主对自己的介质逐个运行, 每个检查都应当拿到一份新的空存储"""
