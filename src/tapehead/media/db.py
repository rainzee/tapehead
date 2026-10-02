from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access, Tape


class DbSilo:
    """存在数据库里的磁带库, 占位"""

    async def create(self, header: TapeHeader) -> Tape:
        raise NotImplementedError

    async def open(self, name: str, access: Access) -> Tape:
        raise NotImplementedError

    async def list(self) -> list[TapeHeader]:
        raise NotImplementedError
