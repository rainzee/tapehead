from collections.abc import AsyncIterator, Sequence

from msgspec.json import decode

from tapehead.delta import AnyDelta, TextDelta, ToolUseDelta
from tapehead.event import (
    AssistantMessage,
    StepEnd,
    StepStart,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnEndReason,
    TurnStart,
    Usage,
    UserMessage,
)
from tapehead.message import Message, ToolUse
from tapehead.model import Model
from tapehead.stream import AsyncStreamEvents, StreamItem
from tapehead.tapes.play import play
from tapehead.tapes.tape import Tape
from tapehead.tool import Tool


def settle(deltas: Sequence[AnyDelta]) -> tuple[str, list[ToolUse]]:
    """把一次模型调用的增量结算成正文和工具调用请求

    参数
    - deltas: 按到达顺序排列的增量
    """

    text = "".join(delta.text for delta in deltas if isinstance(delta, TextDelta))
    uses: dict[str, ToolUse] = {}

    for delta in deltas:
        if isinstance(delta, ToolUseDelta):
            use = uses.setdefault(delta.call_id, ToolUse(call_id=delta.call_id, name="", arguments=""))
            use.name = delta.name or use.name
            use.arguments += delta.arguments

    return text, list(uses.values())


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带"""

    def __init__(self, model: Model, tools: Sequence[Tool] = (), max_steps: int = 50) -> None:
        """
        参数
        - model: 模型调用
        - tools: 可用的工具
        - max_steps: 一轮最多跑几个 step, 用完仍在请求工具时以 max_steps 收尾
        """

        self.model = model
        self.tools = list(tools)
        self.max_steps = max_steps

    async def run(self, tape: Tape, prompt: str) -> AsyncStreamEvents:
        """在磁带上跑一轮对话

        参数
        - tape: 写句柄, 上下文从它回放, 结果录回它
        - prompt: 用户输入
        """

        return AsyncStreamEvents(self.drive(tape, prompt))

    async def execute(self, use: ToolUse) -> tuple[str, bool]:
        """执行一次工具调用, 返回结果文本和是否出错, 工具不存在, 参数不合法, 执行失败都交还给模型

        参数
        - use: 模型请求的工具调用
        """

        tool = next((tool for tool in self.tools if tool.name == use.name), None)
        if tool is None:
            return f"未知工具: {use.name}", True

        try:
            return await tool.call(decode(use.arguments, type=tool.args)), False
        except Exception as error:  # noqa: BLE001 工具的任何失败都交还给模型
            return f"{type(error).__name__}: {error}", True

    async def drive(self, tape: Tape, prompt: str) -> AsyncIterator[StreamItem]:
        turn = sum(isinstance(frame.event, TurnStart) for frame in await tape.read())
        for frame in await tape.record(TurnStart(turn=turn), UserMessage(message=Message(role="user", content=prompt))):
            yield frame

        reason: TurnEndReason = "max_steps"
        for step in range(self.max_steps):
            for frame in await tape.record(StepStart(turn=turn, step=step)):
                yield frame

            deltas: list[AnyDelta] = []
            usage = None

            async for item in self.model.stream(play(await tape.read()), self.tools):
                if isinstance(item, Usage):
                    usage = item
                    continue
                deltas.append(item)
                yield item

            text, uses = settle(deltas)

            message = Message(role="assistant", content=text, tool_uses=uses)
            for frame in await tape.record(AssistantMessage(turn=turn, step=step, message=message, stream=deltas, usage=usage)):
                yield frame

            for use in uses:
                for frame in await tape.record(
                    ToolCall(turn=turn, step=step, call_id=use.call_id, name=use.name, arguments=use.arguments)
                ):
                    yield frame
                content, is_error = await self.execute(use)
                result = Message(role="tool", content=content, tool_call_id=use.call_id)

                for frame in await tape.record(ToolResult(turn=turn, step=step, message=result, is_error=is_error)):
                    yield frame

            for frame in await tape.record(StepEnd(turn=turn, step=step)):
                yield frame

            if not uses:
                reason = "completed"
                break

        for frame in await tape.record(TurnEnd(turn=turn, reason=reason)):
            yield frame
