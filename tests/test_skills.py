import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from tapehead.delta import Delta, TextDelta, ToolCallDelta
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from tapehead.skill import load_skills
from tapehead.tapes.label import Label
from tapehead.tapes.play import play
from tapehead.tool import ToolSpec

DEPLOY_SKILL = """\
---
name: deploy-guide
description: 部署服务时使用, 说明发布前后要做的检查
license: MIT
---

# 部署规范

发布前先跑冒烟测试, 发布后看五分钟错误率.
"""


class FollowsTheCatalog:
    """只靠系统提示里的目录知道有哪些技能, 问题匹配时先加载, 拿到正文后照着答"""

    async def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        system = messages[0].content if isinstance(messages[0], SystemMessage) else ""
        if isinstance(messages[-1], ToolMessage):
            yield TextDelta(text=f"按规范办: {messages[-1].content.splitlines()[-1]}")
        elif "deploy-guide: 部署服务时使用" in system and "部署" in messages[-1].content:
            yield ToolCallDelta(id="call-1", name="skill", arguments='{"name": "deploy-guide"}')
        else:
            yield TextDelta(text="我不知道")


@pytest.mark.asyncio
async def test_agent_loads_a_skill_listed_in_the_system_prompt(tmp_path: Path) -> None:
    """宿主启动时加载技能目录, 用户问到部署, 模型照着系统提示里的目录加载技能, 再按正文作答"""

    (tmp_path / "deploy-guide").mkdir()
    (tmp_path / "deploy-guide" / "SKILL.md").write_text(DEPLOY_SKILL, encoding="utf-8")
    tape = MemTape(Label(name="chat", created_at=time.time()))

    async for _ in await Head(FollowsTheCatalog(), skills=load_skills(tmp_path)).run(tape, "怎么部署这个服务"):
        pass

    messages = play(await tape.read()).messages
    match messages:
        case [
            SystemMessage(),
            UserMessage(),
            AssistantMessage(tool_calls=[call]),
            ToolMessage(),
            AssistantMessage(content=answer),
        ]:
            assert call.name == "skill"
        case _:
            pytest.fail(f"消息序列不符合预期: {messages}")
    assert answer == "按规范办: 发布前先跑冒烟测试, 发布后看五分钟错误率."


@pytest.mark.parametrize(
    ("directory", "name", "description", "message"),
    [
        ("deploy", "deploy-guide", "部署服务时使用", "与目录名"),
        ("Deploy-Guide", "Deploy-Guide", "部署服务时使用", "kebab-case"),
        ("deploy-guide", "deploy-guide", "''", "描述不能为空"),
    ],
)
def test_a_broken_skill_stops_startup(tmp_path: Path, directory: str, name: str, description: str, message: str) -> None:
    """技能目录里有一个写坏的技能, 宿主启动时就直接报错, 而不是悄悄少一个技能"""

    (tmp_path / directory).mkdir()
    content = f"---\nname: {name}\ndescription: {description}\n---\n\n正文\n"
    (tmp_path / directory / "SKILL.md").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_skills(tmp_path)
