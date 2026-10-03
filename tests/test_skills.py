import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from tapehead.delta import AnyDelta, TextDelta, ToolUseDelta
from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.message import Message
from tapehead.skill import load_skills
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.play import play
from tapehead.tool import Tool

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

    async def stream(self, messages: list[Message], tools: Sequence[Tool]) -> AsyncIterator[AnyDelta]:
        system = messages[0].content if messages[0].role == "system" else ""
        if messages[-1].role == "tool":
            yield TextDelta(text=f"按规范办: {messages[-1].content.splitlines()[-1]}")
        elif "deploy-guide: 部署服务时使用" in system and "部署" in messages[-1].content:
            yield ToolUseDelta(call_id="call-1", name="skill", arguments='{"name": "deploy-guide"}')
        else:
            yield TextDelta(text="我不知道")


@pytest.mark.asyncio
async def test_agent_loads_a_skill_listed_in_the_system_prompt(tmp_path: Path) -> None:
    """宿主启动时加载技能目录, 用户问到部署, 模型照着系统提示里的目录加载技能, 再按正文作答"""

    (tmp_path / "deploy-guide").mkdir()
    (tmp_path / "deploy-guide" / "SKILL.md").write_text(DEPLOY_SKILL, encoding="utf-8")
    tape = MemTape(TapeHeader(name="chat", created_at=time.time()))

    async for _ in await Head(FollowsTheCatalog(), skills=load_skills(tmp_path)).run(tape, "怎么部署这个服务"):
        pass

    messages = play(await tape.read())
    assert [m.role for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[1].tool_uses[0].name == "skill"
    assert messages[3].content == "按规范办: 发布前先跑冒烟测试, 发布后看五分钟错误率."


def test_a_broken_skill_stops_startup(tmp_path: Path) -> None:
    """技能目录里有一个名字和目录对不上的技能, 宿主启动时就直接报错, 而不是悄悄少一个技能"""

    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "SKILL.md").write_text(DEPLOY_SKILL, encoding="utf-8")

    with pytest.raises(ValueError, match="与目录名"):
        load_skills(tmp_path)
