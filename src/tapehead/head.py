from collections.abc import AsyncIterator, Sequence

from msgspec.json import decode

from tapehead.delta import Delta
from tapehead.event import (
    Aborted,
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
from tapehead.provider import Provider
from tapehead.skill import Skill, render_skills, skill_tool
from tapehead.stream import StreamItem
from tapehead.tapes.play import configuration, mend, play
from tapehead.tapes.tape import Tape
from tapehead.tool import Tool


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带

    模型的输入只经由 play 从磁带得出, 不在 play 之外加工
    执行工具前和一轮结束时 flush, 工具的副作用发生时 Dispatched 必已落盘
    """

    def __init__(
        self,
        provider: Provider,
        tools: Sequence[Tool] = (),
        system_prompt: str = "",
        skills: Sequence[Skill] = (),
        max_steps: int = 50,
    ) -> None:
        """
        参数
        - provider: 模型提供方
        - tools: 可用的工具
        - system_prompt: 系统提示, 和工具定义一起作为 Configured 落带, 只在变化时写
        - skills: 可用的技能, 目录并入系统提示, 同时多出一个加载正文的 skill 工具
        - max_steps: 单轮最多被接纳的模型调用次数
        """

        self.provider = provider
        self.tools = [*tools, *([skill_tool(skills)] if skills else [])]
        self.configured = Configured(
            message=SystemMessage(content="\n\n".join(part for part in (system_prompt, render_skills(skills)) if part)),
            tools=[tool.spec for tool in self.tools],
        )
        self.max_steps = max_steps

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
            context = play(await tape.read())
            stream: list[Delta] = []
            try:
                async for delta in self.provider.stream(context.messages, context.tools):
                    stream.append(delta)
                    yield delta
            except Exception as error:
                failed = Aborted(stream=stream, error=f"{type(error).__name__}: {error}")
                for frame in await tape.record(failed, Yielded(reason="failed")):
                    yield frame
                await tape.flush()
                raise

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
