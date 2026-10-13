import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from tapehead.core.delta import TextDelta
from tapehead.core.event import Aborted, Yielded
from tapehead.core.head import Head
from tapehead.core.message import UserMessage
from tapehead.core.provider import ContextOverflow
from tapehead.core.tape import Label
from tapehead.media.fs import FsSilo
from tapehead.media.mem import MemSilo, MemTape
from tapehead.testing import Medium, ScriptedProvider, checks
from tapehead.testing.media import check_names_are_unique


@pytest.fixture(params=["mem", "fs"])
def medium(request: pytest.FixtureRequest, tmp_path: Path) -> Medium:
    if request.param == "mem":
        silo = MemSilo()
        return Medium(connect=lambda: silo, durable=False)

    return Medium(connect=lambda: FsSilo(tmp_path), durable=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("check", checks, ids=lambda check: check.__name__)
async def test_builtin_media_honour_the_tape_contract(medium: Medium, check: Callable[[Medium], Awaitable[None]]) -> None:
    """内置的内存和文件介质都通过介质一致性检查, 宿主自己实现的介质也照这样跑一遍"""

    await check(medium)


class Leaky(MemSilo):
    """create 时不查重名, 后来者覆盖先来者的介质"""

    async def create(self, label: Label) -> MemTape:
        self.tapes[label.name] = MemTape(label)

        return self.tapes[label.name]


@pytest.mark.asyncio
async def test_a_medium_breaking_the_contract_is_caught() -> None:
    """介质违反契约时, 检查直接抛出 AssertionError 并说清哪条没做到, 宿主在自己的测试框架里就能看到"""

    with pytest.raises(AssertionError, match="FileExistsError"):
        silo = Leaky()
        await check_names_are_unique(Medium(connect=lambda: silo, durable=False))


def new_tape() -> MemTape:
    return MemTape(Label(name="chat", created_at=time.time()))


@pytest.mark.asyncio
async def test_a_script_that_runs_out_fails_loudly() -> None:
    """脚本比模型调用少一步, 多出来的那次调用明确失败, 而不是悄悄给出空回答"""

    tape = new_tape()
    provider = ScriptedProvider([TextDelta(text="你好")])
    head = Head(provider)

    async for _ in head.run(tape, "一"):
        pass
    with pytest.raises(AssertionError, match="脚本已用完"):
        async for _ in head.run(tape, "二"):
            pass

    assert [call.messages[-1] for call in provider.calls] == [UserMessage(content="一"), UserMessage(content="二")]


@pytest.mark.asyncio
async def test_a_script_can_fail_before_or_during_the_stream() -> None:
    """一步可以是一开始就失败, 也可以是给出一部分增量后失败, 已收到的增量照样落进 Aborted"""

    for step, stream, error in (
        (ContextOverflow("maximum context length"), [], "ContextOverflow"),
        ([TextDelta(text="半截"), ConnectionError("429")], [TextDelta(text="半截")], "ConnectionError"),
    ):
        tape = new_tape()
        with pytest.raises(Exception, match=r"maximum context length|429"):
            async for _ in Head(ScriptedProvider(step)).run(tape, "一"):
                pass

        events = [frame.event for frame in await tape.read()]
        assert isinstance(events[-2], Aborted) and events[-2].stream == stream
        assert events[-2].error.startswith(error)
        assert events[-1] == Yielded(reason="failed")
