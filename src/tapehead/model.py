from collections.abc import AsyncIterator
from typing import Protocol

from tapehead.delta import AnyDelta
from tapehead.event import Usage
from tapehead.message import Message


class Model(Protocol):
    """模型调用, 由宿主提供, 内核不内置任何 provider"""

    def stream(self, messages: list[Message]) -> AsyncIterator[AnyDelta | Usage]:
        """以流的形式返回一次模型调用的增量, 用量在结算时给出

        参数
        - messages: 从磁带回放得出的上下文
        """
        ...
