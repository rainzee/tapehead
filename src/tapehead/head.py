from collections.abc import AsyncIterator, Sequence

from msgspec.json import decode

from tapehead import message as msg
from tapehead.delta import AnyDelta, TextDelta, ToolCallDelta
from tapehead.event import (
    AssistantMessage,
    StepEnd,
    StepStart,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnEndReason,
    TurnStart,
    UserMessage,
)
from tapehead.provider import Provider
from tapehead.skill import Skill, render_skills, skill_tool
from tapehead.stream import AsyncStreamEvents, StreamItem
from tapehead.tapes.play import mend, play
from tapehead.tapes.tape import Tape
from tapehead.tool import Tool


def settle(deltas: Sequence[AnyDelta]) -> tuple[str, list[msg.ToolCall]]:
    """把一次模型调用的增量结算成正文和工具调用请求

    参数
    - deltas: 按到达顺序排列的增量
    """

    text = "".join(delta.text for delta in deltas if isinstance(delta, TextDelta))
    calls: dict[str, msg.ToolCall] = {}

    for delta in deltas:
        if isinstance(delta, ToolCallDelta):
            call = calls.setdefault(delta.id, msg.ToolCall(id=delta.id, name="", arguments=""))
            call.name = delta.name or call.name
            call.arguments += delta.arguments

    return text, list(calls.values())


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带"""

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
        - system_prompt: 系统提示, 不上带, 每次调用模型时放在上下文最前面
        - skills: 可用的技能, 目录并入系统提示, 同时多出一个加载正文的 skill 工具
        - max_steps: 单 turn 最大 setps
        """

        self.provider = provider
        self.system_prompt = "\n\n".join(part for part in (system_prompt, render_skills(skills)) if part)
        self.tools = [*tools, *([skill_tool(skills)] if skills else [])]
        self.max_steps = max_steps

    async def run(self, tape: Tape, prompt: str) -> AsyncStreamEvents:
        """在磁带上跑一轮对话

        参数
        - tape: 写句柄, 上下文从它回放, 结果录回它
        - prompt: 用户输入
        """

        return AsyncStreamEvents(self.drive(tape, prompt))

    async def execute(self, call: msg.ToolCall) -> tuple[str, bool]:
        """执行一次工具调用, 返回结果文本和是否出错, 工具不存在, 参数不合法, 执行失败都交还给模型

        参数
        - call: 模型请求的工具调用
        """

        tool = next((tool for tool in self.tools if tool.name == call.name), None)
        if tool is None:
            return f"未知工具: {call.name}", True

        try:
            return await tool.call(decode(call.arguments, type=tool.args)), False
        except Exception as error:  # noqa: BLE001 工具的任何失败都交还给模型
            return f"{type(error).__name__}: {error}", True

    async def drive(self, tape: Tape, prompt: str) -> AsyncIterator[StreamItem]:
        frames = await tape.read()
        for frame in await tape.record(*mend(frames)):
            yield frame
        turn = sum(isinstance(frame.event, TurnStart) for frame in frames)
        for frame in await tape.record(TurnStart(turn=turn), UserMessage(message=msg.UserMessage(content=prompt))):
            yield frame

        reason: TurnEndReason = "max_steps"
        for step in range(self.max_steps):
            for frame in await tape.record(StepStart(turn=turn, step=step)):
                yield frame

            deltas: list[AnyDelta] = []

            context = play(await tape.read())
            if self.system_prompt:
                context = [msg.SystemMessage(content=self.system_prompt), *context]

            async for delta in self.provider.stream(context, self.tools):
                deltas.append(delta)
                yield delta

            text, calls = settle(deltas)

            message = msg.AssistantMessage(content=text, tool_calls=calls)
            for frame in await tape.record(AssistantMessage(turn=turn, step=step, message=message, stream=deltas)):
                yield frame

            for call in calls:
                for frame in await tape.record(
                    ToolCall(turn=turn, step=step, call_id=call.id, name=call.name, arguments=call.arguments)
                ):
                    yield frame
                content, is_error = await self.execute(call)
                result = msg.ToolMessage(call_id=call.id, content=content, is_error=is_error)

                for frame in await tape.record(ToolResult(turn=turn, step=step, message=result)):
                    yield frame

            for frame in await tape.record(StepEnd(turn=turn, step=step)):
                yield frame

            if not calls:
                reason = "completed"
                break

        for frame in await tape.record(TurnEnd(turn=turn, reason=reason)):
            yield frame
