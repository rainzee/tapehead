from collections.abc import AsyncIterator

from tapehead.delta import TextDelta
from tapehead.event import AssistantMessage, StepEnd, StepStart, TurnEnd, TurnStart, Usage, UserMessage
from tapehead.message import Message
from tapehead.model import Model
from tapehead.stream import AsyncStreamEvents, StreamItem
from tapehead.tapes.play import play
from tapehead.tapes.tape import Tape


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带"""

    def __init__(self, model: Model) -> None:
        self.model = model

    async def run(self, tape: Tape, prompt: str) -> AsyncStreamEvents:
        """在磁带上跑一轮对话

        参数
        - tape: 写句柄, 上下文从它回放, 结果录回它
        - prompt: 用户输入
        """

        return AsyncStreamEvents(self.drive(tape, prompt))

    async def drive(self, tape: Tape, prompt: str) -> AsyncIterator[StreamItem]:
        turn = sum(isinstance(frame.event, TurnStart) for frame in await tape.read())
        for frame in await tape.record(TurnStart(turn=turn), UserMessage(message=Message(role="user", content=prompt))):
            yield frame

        for frame in await tape.record(StepStart(turn=turn, step=0)):
            yield frame
        messages = play(await tape.read())
        deltas = []
        usage = None
        async for item in self.model.stream(messages):
            if isinstance(item, Usage):
                usage = item
                continue
            deltas.append(item)
            yield item
        text = "".join(delta.text for delta in deltas if isinstance(delta, TextDelta))

        reply = AssistantMessage(turn=turn, step=0, message=Message(role="assistant", content=text), stream=deltas, usage=usage)
        for frame in await tape.record(reply, StepEnd(turn=turn, step=0), TurnEnd(turn=turn, reason="completed")):
            yield frame
