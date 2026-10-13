import json
from pathlib import Path

import pytest

from tapehead.kit.read import read_tool


def arguments(**values: object) -> str:
    return json.dumps(values)


@pytest.mark.asyncio
async def test_long_files_are_read_page_by_page(tmp_path: Path) -> None:
    """文件超过一次的行数上限时, 结果提示下一页的 offset, 按提示能接着读完"""

    (tmp_path / "long.txt").write_text("\n".join(f"line {i}" for i in range(1, 6)), encoding="utf-8")
    read = read_tool(tmp_path, limit=2)

    first = await read.call(arguments(path="long.txt"))
    last = await read.call(arguments(path="long.txt", offset=5))

    assert first == "line 1\nline 2\n\n[还有 3 行, 用 offset=3 继续]"
    assert last == "line 5"


@pytest.mark.asyncio
async def test_files_outside_the_roots_are_refused(tmp_path: Path) -> None:
    """跳出允许的目录时拒绝读取, 第二个根目录之内的绝对路径可以读"""

    workspace, skills = tmp_path / "workspace", tmp_path / "skills"
    workspace.mkdir()
    skills.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    (skills / "guide.md").write_text("guide", encoding="utf-8")
    read = read_tool(workspace, skills)

    with pytest.raises(PermissionError):
        await read.call(arguments(path="../secret.txt"))
    assert await read.call(arguments(path=str(skills / "guide.md"))) == "guide"
