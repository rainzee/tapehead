from typing import Protocol

from tapehead.tapes.label import Label
from tapehead.tapes.tape import Tape


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
