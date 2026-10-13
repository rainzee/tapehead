from collections.abc import AsyncIterator
from typing import Protocol

from tapehead.core.delta import Delta
from tapehead.core.message import Message
from tapehead.core.tool import ToolSpec


class ContextOverflow(Exception):
    """模型提供方明确报告输入超出上下文窗口, 只在服务端给出这一信号时抛出, 不靠猜测"""


class Provider(Protocol):
    """模型提供方, 内核只约定形状, 实现由宿主提供"""

    def stream(self, messages: list[Message], tools: list[ToolSpec]) -> AsyncIterator[Delta]:
        """以流的形式返回一次模型调用的增量, 用量作为 UsageDelta 给出, 输入超出窗口时抛出 ContextOverflow

        参数
        - messages: 从磁带回放得出的上下文
        - tools: 这次调用可用的工具定义
        """
        ...
