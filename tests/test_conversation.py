import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from tapehead.delta import Delta, TextDelta
from tapehead.head import Head
from tapehead.media.fs import FsSilo
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, UserMessage
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.play import play
from tapehead.tool import ToolSpec


class ForgetfulProvider:
    """只靠收到的上下文回答, 被问到名字时, 之前没人说过就答不上来"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
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
    head = Head(ForgetfulProvider())

    async for _ in await head.run(tape, "我叫小明"):
        pass
    async for _ in await head.run(tape, "我叫什么"):
        pass

    assert play(await tape.read()).messages == [
        UserMessage(content="我叫小明"),
        AssistantMessage(content="你好"),
        UserMessage(content="我叫什么"),
        AssistantMessage(content="你叫小明"),
    ]


@pytest.mark.asyncio
async def test_conversation_survives_a_restart(tmp_path: Path) -> None:
    """用户自我介绍后关掉程序, 第二天重新打开同一盘带接着问, 模型仍然知道名字"""

    silo = FsSilo(tmp_path)
    tape = await silo.create(TapeHeader(name="chat", created_at=time.time()))
    async for _ in await Head(ForgetfulProvider()).run(tape, "我叫小明"):
        pass
    await tape.close()

    tape = await FsSilo(tmp_path).open("chat", "write")
    async for _ in await Head(ForgetfulProvider()).run(tape, "我叫什么"):
        pass
    await tape.close()

    tape = await FsSilo(tmp_path).open("chat", "write")
    assert play(await tape.read()).messages == [
        UserMessage(content="我叫小明"),
        AssistantMessage(content="你好"),
        UserMessage(content="我叫什么"),
        AssistantMessage(content="你叫小明"),
    ]
    await tape.close()
