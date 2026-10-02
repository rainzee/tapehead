from typing import Protocol

from msgspec import Struct


class Tool[A: Struct](Protocol):
    """工具, 由宿主提供, 参数用一个 Struct 声明, schema 和校验都出自它"""

    name: str
    description: str
    args: type[A]

    async def call(self, args: A) -> str:
        """执行一次调用, 返回给模型看的结果, 失败时直接抛异常

        参数
        - args: 已经校验过的参数
        """
        ...
