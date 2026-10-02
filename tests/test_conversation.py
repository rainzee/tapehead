import time
from collections.abc import AsyncIterator

import pytest

from tapehead.delta import AnyDelta, TextDelta
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import Message
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.play import play


class ForgetfulModel:
    """只靠收到的上下文回答, 被问到名字时, 之前没人说过就答不上来"""

    async def stream(self, messages: list[Message]) -> AsyncIterator[AnyDelta]:
        *earlier, asked = messages
        if "我叫什么" not in asked.content:
            yield TextDelta(text="你好")
        elif any("我叫小明" in message.content for message in earlier):
            yield TextDelta(text="你叫小明")
        else:
            yield TextDelta(text="我不知道")


@pytest.mark.asyncio
async def test_second_turn_remembers_the_first() -> None:
    """用户先自我介绍, 再追问, 模型只能从磁带回放的上下文里知道名字"""

    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))
    head = Head(ForgetfulModel())

    async for _ in await head.run(tape, "我叫小明"):
        pass
    async for _ in await head.run(tape, "我叫什么"):
        pass

    assert [(m.role, m.content) for m in play(await tape.read())] == [
        ("user", "我叫小明"),
        ("assistant", "你好"),
        ("user", "我叫什么"),
        ("assistant", "你叫小明"),
    ]
