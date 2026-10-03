import re
from collections.abc import Sequence
from pathlib import Path

from msgspec import DecodeError, Struct, ValidationError
from msgspec.yaml import decode

from tapehead.tool import Tool, tool

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Skill(Struct):
    """技能"""

    name: str
    description: str
    body: str
    directory: str | None = None


class Frontmatter(Struct):
    """SKILL.md 开头的元数据"""

    name: str
    description: str


def parse_skill(file: Path) -> Skill:
    """解析一个 SKILL.md, 不合法时抛 ValueError

    参数
    - file: SKILL.md 的路径, 它所在目录的名字必须等于技能名
    """

    parts = file.read_text(encoding="utf-8").removeprefix("\ufeff").split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise ValueError(f"{file}: 缺少 frontmatter")
    try:
        meta = decode(parts[1], type=Frontmatter)
    except (DecodeError, ValidationError) as error:
        raise ValueError(f"{file}: {error}") from error
    if len(meta.name) > 64 or not NAME_PATTERN.fullmatch(meta.name):
        raise ValueError(f"{file}: 技能名必须是不超过 64 个字符的 kebab-case, 实际是 {meta.name!r}")
    if meta.name != file.parent.name:
        raise ValueError(f"{file}: 技能名 {meta.name!r} 与目录名 {file.parent.name!r} 不一致")
    if not meta.description.strip() or len(meta.description) > 1024:
        raise ValueError(f"{file}: 描述不能为空, 也不能超过 1024 个字符")

    return Skill(
        name=meta.name,
        description=meta.description.strip(),
        body=parts[2].strip(),
        directory=str(file.parent.resolve()),
    )


def load_skills(*roots: Path) -> list[Skill]:
    """从目录里读取技能, 每个技能是 <root>/<name>/SKILL.md, 任何一个不合法或重名都直接抛 ValueError

    参数
    - roots: 技能目录, 按给定顺序读取
    """

    skills: dict[str, Skill] = {}
    for root in roots:
        for file in sorted(root.glob("*/SKILL.md")):
            skill = parse_skill(file)
            if skill.name in skills:
                raise ValueError(f"技能重名: {skill.name}")
            skills[skill.name] = skill

    return list(skills.values())


def skills_prompt(skills: Sequence[Skill]) -> str:
    """把技能目录渲染成一段系统提示, 没有技能时为空

    参数
    - skills: 可用的技能
    """

    if not skills:
        return ""
    lines = [
        "以下技能提供特定任务的专门指令, 任务匹配某个技能的描述时, 先调用 skill 工具加载它的完整指令",
        "<available_skills>",
        *(f"- {skill.name}: {skill.description}" for skill in skills),
        "</available_skills>",
    ]

    return "\n".join(lines)


def skill_tool(skills: Sequence[Skill]) -> Tool:
    """生成加载技能正文的工具, 正文作为工具结果落带

    参数
    - skills: 可用的技能
    """

    by_name = {skill.name: skill for skill in skills}

    @tool(description="加载一个技能的完整指令, name 取自系统提示里 available_skills 列出的名字")
    async def skill(name: str) -> str:
        found = by_name.get(name)
        if found is None:
            raise ValueError(f"未知技能: {name}, 可用: {', '.join(by_name)}")

        return f"技能目录: {found.directory}\n\n{found.body}" if found.directory else found.body

    return skill
