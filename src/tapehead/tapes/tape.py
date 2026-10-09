from typing import Literal, Protocol

from tapehead.event import Event
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label

type Access = Literal["read", "write"]


class Tape(Protocol):
    """磁带"""

    @property
    def label(self) -> Label: ...

    @property
    def access(self) -> Access: ...

    @property
    def head(self) -> int:
        """下一帧的位置, 翻录带从 origin.at 起算"""
        ...

    async def record(self, *events: Event) -> list[Frame]:
        """把事实按顺序录成连续的帧, 读句柄上调用会被拒绝

        参数
        - events: 还没落带的事实, 录入时间由磁带填写
        """
        ...

    async def read(self, start: int = 0, stop: int | None = None) -> list[Frame]:
        """读取 [start, stop) 的帧, 翻录带会先拼上父带前缀

        参数
        - start: 起始位置, 含
        - stop: 结束位置, 不含, 省略时读到末尾
        """
        ...

    async def flush(self) -> None:
        """持久化屏障, 返回后已录的帧保证落盘"""
        ...

    async def close(self) -> None:
        """释放句柄, 写句柄会先 flush 再交出写权"""
        ...
