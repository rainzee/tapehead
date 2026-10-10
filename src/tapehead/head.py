from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from msgspec.json import decode

from tapehead.delta import Delta
from tapehead.event import (
    Aborted,
    Compacted,
    Configured,
    Dispatched,
    Event,
    Generated,
    Prompted,
    Returned,
    Yielded,
    YieldReason,
    settle,
)
from tapehead.message import SystemMessage, ToolCall, ToolMessage, UserMessage
from tapehead.provider import ContextOverflow, Provider
from tapehead.skill import Skill, render_skills, skill_tool
from tapehead.stream import StreamItem
from tapehead.tapes.frame import Frame
from tapehead.tapes.play import admit, configuration, mend, play
from tapehead.tapes.tape import Tape
from tapehead.tool import Tool

type Compactor = Callable[[list[Frame]], Awaitable[Compacted | None]]


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带

    模型的输入只经由 play 从磁带得出, 不在 play 之外加工
    执行工具前和一轮结束时 flush, 工具的副作用发生时 Dispatched 必已落盘
    从读取前缀发起一次模型调用, 到它的 Generated 或 Aborted 落带, 之间不提交改变上下文的事件,
    所以同一盘带同一时刻只能有一个 run 或 compact 在进行, 这由宿主保证
    """

    def __init__(
        self,
        provider: Provider,
        tools: Sequence[Tool] = (),
        system_prompt: str = "",
        skills: Sequence[Skill] = (),
        max_steps: int = 50,
        compactor: Compactor | None = None,
    ) -> None:
        """
        参数
        - provider: 模型提供方
        - tools: 可用的工具
        - system_prompt: 系统提示, 和工具定义一起作为 Configured 落带, 只在变化时写
        - skills: 可用的技能, 目录并入系统提示, 同时多出一个加载正文的 skill 工具
        - max_steps: 单轮最多被接纳的模型调用次数
        - compactor: 输入超出窗口时由它给出压缩, 拿到当前的帧, 从 cuts 里挑切点并写好摘要, 给不出时返回 None
        """

        self.provider = provider
        self.tools = [*tools, *([skill_tool(skills)] if skills else [])]
        self.configured = Configured(
            message=SystemMessage(content="\n\n".join(part for part in (system_prompt, render_skills(skills)) if part)),
            tools=[tool.spec for tool in self.tools],
        )
        self.max_steps = max_steps
        self.compactor = compactor

    async def run(self, tape: Tape, prompt: str) -> AsyncIterator[StreamItem]:
        """在磁带上跑一轮对话, 实时交出已落带的帧和不落带的增量

        参数
        - tape: 磁带, 上下文从它回放, 结果录回它
        - prompt: 用户输入
        """

        frames = await tape.read()
        opening: list[Event] = mend(frames)
        if configuration(frames) != self.configured:
            opening.append(self.configured)
        opening.append(Prompted(message=UserMessage(content=prompt)))
        for frame in await tape.record(*opening):
            yield frame

        reason: YieldReason = "max_steps"
        for _ in range(self.max_steps):
            recovered = False
            while True:
                context = play(await tape.read())
                stream: list[Delta] = []
                try:
                    async for delta in self.provider.stream(context.messages, context.tools):
                        stream.append(delta)
                        yield delta
                    break
                except Exception as error:  # noqa: BLE001 任何失败都先落 Aborted, 除溢出恢复外原样抛出
                    for frame in await tape.record(Aborted(stream=stream, error=f"{type(error).__name__}: {error}")):
                        yield frame
                    try:
                        if not isinstance(error, ContextOverflow) or recovered or self.compactor is None:
                            raise
                        frames = await tape.read()
                        compacted = await self.compactor(frames)
                        if compacted is None:
                            raise
                        admit(frames, compacted)
                    except Exception:
                        for frame in await tape.record(Yielded(reason="failed")):
                            yield frame
                        await tape.flush()
                        raise
                    for frame in await tape.record(compacted):
                        yield frame
                    recovered = True

            message = settle(stream)
            for frame in await tape.record(Generated(stream=stream, message=message)):
                yield frame

            calls = message.tool_calls
            for call in calls:
                for frame in await tape.record(Dispatched(call_id=call.id)):
                    yield frame
                await tape.flush()
                for frame in await tape.record(await self.execute(call)):
                    yield frame

            if not calls:
                reason = "completed"
                break

        for frame in await tape.record(Yielded(reason=reason)):
            yield frame
        await tape.flush()

    async def compact(self, tape: Tape, compacted: Compacted) -> list[Frame]:
        """在两轮之间压缩, 校验切点后落带, 宿主在这盘带上没有 run 进行时调用

        参数
        - tape: 磁带
        - compacted: 宿主从 cuts 里挑了切点并写好摘要的压缩
        """

        admit(await tape.read(), compacted)
        recorded = await tape.record(compacted)
        await tape.flush()

        return recorded

    async def execute(self, call: ToolCall) -> Returned:
        """执行一次工具调用, 工具不存在, 参数不合法, 执行失败都作为出错的结果交还给模型

        参数
        - call: 模型请求的工具调用
        """

        tool = next((tool for tool in self.tools if tool.name == call.name), None)
        if tool is None:
            return Returned(message=ToolMessage(call_id=call.id, content=f"未知工具: {call.name}", is_error=True))

        try:
            content = await tool.call(decode(call.arguments, type=tool.args))
        except Exception as error:  # noqa: BLE001 工具的任何失败都交还给模型
            return Returned(message=ToolMessage(call_id=call.id, content=f"{type(error).__name__}: {error}", is_error=True))

        return Returned(message=ToolMessage(call_id=call.id, content=content))
