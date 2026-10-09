from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from tapehead.delta import AnyDelta
from tapehead.message import Message
from tapehead.tool import Tool


class Provider(Protocol):
    """模型提供方, 由宿主提供, 内核不内置任何实现"""

    def stream(self, messages: list[Message], tools: Sequence[Tool]) -> AsyncIterator[AnyDelta]:
        """以流的形式返回一次模型调用的增量, 用量作为 UsageDelta 给出

        参数
        - messages: 从磁带回放得出的上下文
        - tools: 这次调用可用的工具
        """
        ...
