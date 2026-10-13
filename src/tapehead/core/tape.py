from typing import Protocol

from msgspec import Struct

from tapehead.core.event import Event


class Label(Struct):
    """磁带标签, 创建时写定, 此后不变, 不读帧即可得到"""

    name: str
    created_at: float


class Frame(Struct):
    """磁带上的一帧, recorded_at 由 Tape.record 填写, 位置由介质提供"""

    recorded_at: float
    event: Event


class Tape(Protocol):
    """磁带"""

    @property
    def label(self) -> Label: ...

    async def record(self, *events: Event) -> list[Frame]:
        """把事实按顺序录成连续的帧

        参数
        - events: 还没落带的事实, 录入时间由磁带填写
        """
        ...

    async def read(self, start: int = 0, stop: int | None = None) -> list[Frame]:
        """读取 [start, stop) 的帧

        参数
        - start: 起始位置, 含
        - stop: 结束位置, 不含, 省略时读到末尾
        """
        ...

    async def flush(self) -> None:
        """持久化屏障, 返回后已录的帧保证落盘"""
        ...

    async def close(self) -> None:
        """释放句柄, 先 flush 再释放"""
        ...


class Silo(Protocol):
    """磁带库, 负责磁带的存放和出入库"""

    async def create(self, label: Label) -> Tape:
        """新建一盘带并取得句柄

        参数
        - label: 磁带标签
        """
        ...

    async def open(self, name: str) -> Tape:
        """打开已有的一盘带

        参数
        - name: 磁带名
        """
        ...

    async def list(self) -> list[Label]:
        """列出所有磁带标签"""
        ...
