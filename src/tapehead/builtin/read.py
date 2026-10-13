from pathlib import Path
from typing import Annotated

from msgspec import Meta

from tapehead.tool import Tool, tool


def read_tool(*roots: Path, limit: int = 2000) -> Tool:
    """只读文件的工具

    只能读 roots 之内的文本文件, 越界和读不出来都作为错误结果交还给模型
    按行读取并带上限, 超出时提示用 offset 继续

    参数
    - roots: 允许读取的目录, 宿主通常传工作目录和技能目录, 相对路径相对第一个
    - limit: 一次最多返回的行数
    """

    allowed = [root.resolve() for root in roots]

    @tool(description=f"读取一个 UTF-8 文本文件, 一次最多返回 {limit} 行, 没读完时结果末尾会提示下一次的 offset")
    def read(
        path: Annotated[str, Meta(description="文件路径, 相对路径相对工作目录")],
        offset: Annotated[int, Meta(ge=1, description="从第几行开始读, 从 1 起")] = 1,
    ) -> str:
        target = (allowed[0] / path).resolve()
        if not any(target.is_relative_to(root) for root in allowed):
            raise PermissionError(f"{path} 不在允许读取的目录内")
        lines = target.read_text(encoding="utf-8").splitlines()
        stop = offset - 1 + limit
        content = "\n".join(lines[offset - 1 : stop])
        if stop < len(lines):
            content += f"\n\n[还有 {len(lines) - stop} 行, 用 offset={stop + 1} 继续]"

        return content

    return read
