from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from tapehead.delta import Delta
from tapehead.message import Message
from tapehead.tool import ToolSpec


class ContextOverflow(Exception):
    """模型提供方明确报告输入超出上下文窗口, 只在服务端给出这一信号时抛出, 不靠猜测"""


class Provider(Protocol):
    """模型提供方, 由宿主提供, 内核不内置任何实现"""

    def stream(self, messages: list[Message], tools: Sequence[ToolSpec]) -> AsyncIterator[Delta]:
        """以流的形式返回一次模型调用的增量, 用量作为 UsageDelta 给出, 输入超出窗口时抛出 ContextOverflow

        参数
        - messages: 从磁带回放得出的上下文
        - tools: 这次调用可用的工具定义
        """
        ...
