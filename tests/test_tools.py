import asyncio
import json
import time
from pathlib import Path
from typing import Annotated

import pytest
from msgspec import Meta

from tapehead.core.delta import ReasoningDelta, TextDelta, ToolCallDelta
from tapehead.core.event import Generated, Returned, Yielded
from tapehead.core.head import Head
from tapehead.core.message import AssistantMessage, ToolMessage, UserMessage
from tapehead.core.play import play
from tapehead.core.tape import Label
from tapehead.kit.tool import tool
from tapehead.media.mem import MemTape
from tapehead.testing import ScriptedProvider


@tool
async def read_file(path: Annotated[str, Meta(description="文件路径")]) -> str:
    """读取一个 UTF-8 文本文件"""

    return Path(path).read_text(encoding="utf-8")


def reads_then_answers(path: Path) -> ScriptedProvider:
    """先请求读文件, 参数分两段到达, 拿到工具结果后作答"""

    arguments = json.dumps({"path": str(path)})
    half = len(arguments) // 2

    return ScriptedProvider(
        [
            ToolCallDelta(id="call-1", name="read_file", arguments=arguments[:half]),
            ToolCallDelta(id="call-1", arguments=arguments[half:]),
        ],
        [TextDelta(chunk="读完了")],
    )


@pytest.mark.asyncio
async def test_agent_reads_a_file_before_answering(tmp_path: Path) -> None:
    """用户让 agent 读一个文件, 模型先请求调用工具, 拿到文件内容后才作答"""

    note = tmp_path / "note.txt"
    note.write_text("明天下午三点开会", encoding="utf-8")
    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = reads_then_answers(note)

    async for _ in Head(provider, [read_file]).run(tape, f"读一下 {note}"):
        pass

    messages = play(await tape.read()).messages
    match messages:
        case [
            UserMessage(),
            AssistantMessage(tool_calls=[call]),
            ToolMessage(call_id=call_id),
            AssistantMessage(content="读完了"),
        ]:
            assert call.name == "read_file"
            assert call_id == call.id
        case _:
            pytest.fail(f"消息序列不符合预期: {messages}")
    assert provider.calls[-1].messages[-1] == ToolMessage(call_id=call.id, content="明天下午三点开会")


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_to_the_model(tmp_path: Path) -> None:
    """用户让 agent 读一个不存在的文件, 工具失败不会中断这一轮, 失败交还给模型"""

    tape = MemTape(Label(name="chat", created_at=time.time()))
    missing = tmp_path / "missing.txt"
    provider = reads_then_answers(missing)

    async for _ in Head(provider, [read_file]).run(tape, f"读一下 {missing}"):
        pass

    events = [frame.event for frame in await tape.read()]
    results = [event for event in events if isinstance(event, Returned)]
    assert [r.message.is_error for r in results] == [True]
    assert "FileNotFoundError" in results[0].message.content
    assert isinstance(events[-1], Yielded) and events[-1].reason == "completed"
    assert provider.calls[-1].messages[-1] == results[0].message


@tool
def ping() -> str:
    """探活"""

    return "pong"


@pytest.mark.asyncio
async def test_a_model_stuck_on_tools_is_stopped() -> None:
    """模型卡在反复请求工具上, 这一轮在步数上限处收尾, 磁带上不留下没闭合的轮次"""

    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = ScriptedProvider(*([ToolCallDelta(id=f"call-{i}", name="ping", arguments="{}")] for i in range(3)))

    async def drain() -> None:
        async for _ in Head(provider, [ping], max_steps=3).run(tape, "ping 到天荒地老"):
            pass

    await asyncio.wait_for(drain(), timeout=5)

    events = [frame.event for frame in await tape.read()]
    assert sum(isinstance(event, Generated) for event in events) == 3
    assert isinstance(events[-1], Yielded) and events[-1].reason == "max_steps"


@pytest.mark.asyncio
async def test_the_model_sees_its_own_reasoning_between_tool_calls() -> None:
    """模型边想边调工具, 拿到工具结果时还能看到自己调用前的推理, 推理随这一步的消息一起回放"""

    tape = MemTape(Label(name="chat", created_at=time.time()))
    provider = ScriptedProvider(
        [
            ReasoningDelta(chunk="先确认服务"),
            ReasoningDelta(chunk="是否在线"),
            ToolCallDelta(id="call-1", name="ping", arguments="{}"),
        ],
        [TextDelta(chunk="在线")],
    )

    async for _ in Head(provider, [ping]).run(tape, "服务还在吗"):
        pass

    match provider.calls[1].messages:
        case [UserMessage(), AssistantMessage(reasoning=reasoning, tool_calls=[_]), ToolMessage()]:
            assert reasoning == "先确认服务是否在线"
        case messages:
            pytest.fail(f"消息序列不符合预期: {messages}")


def test_two_tools_with_the_same_name_are_refused() -> None:
    """宿主装了两个同名工具, 模型按名字只能调到其中一个, Head 构造时就直接报错, 而不是悄悄让另一个失效"""

    @tool(name="ping")
    def another_ping() -> str:
        """另一个探活"""

        return "pong"

    with pytest.raises(ValueError, match="工具重名: ping"):
        Head(ScriptedProvider(), [ping, another_ping])
