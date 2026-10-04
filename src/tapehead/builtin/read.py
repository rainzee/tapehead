from pathlib import Path

from tapehead.tool import Tool


def read_tool(*roots: Path) -> Tool:
    """只读文件的工具, 占位

    只能读 roots 之内的文本文件, 越界和读不出来都作为错误结果交还给模型
    按行读取并带上限, 超出时提示用 offset 继续

    参数
    - roots: 允许读取的目录, 宿主通常传工作目录和技能目录
    """

    raise NotImplementedError
