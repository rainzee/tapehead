from typing import Protocol

from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access, Tape


class Deck(Protocol):
    """磁带机, 负责磁带的存放和出入库, 帧的读写只经由 Tape 句柄"""

    async def create(self, header: TapeHeader) -> Tape:
        """新建一盘带并取得写句柄, header.origin 非空即为翻录

        参数
        - header: 磁带头
        """
        ...

    async def open(self, name: str, access: Access) -> Tape:
        """打开已有的一盘带

        参数
        - name: 磁带名
        - access: read 不占写权, write 独占写权
        """
        ...

    async def list(self) -> list[TapeHeader]:
        """列出所有磁带头, 不读帧"""
        ...
