from typing import Any, Protocol

from msgspec import Struct


class ToolSpec(Struct):
    """模型可见的工具定义"""

    name: str
    description: str
    parameters: dict[str, Any]


class Tool(Protocol):
    """工具, 内核只约定形状, 实现由宿主提供"""

    @property
    def spec(self) -> ToolSpec:
        """给模型看的工具定义, 随 Configured 落带"""
        ...

    async def call(self, arguments: str) -> str:
        """执行一次调用, 返回给模型看的结果, 实参不合法或执行失败时直接抛异常

        参数
        - arguments: 模型给出的 JSON 实参, 未经校验
        """
        ...
