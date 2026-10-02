from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access, Tape


class DbSilo:
    """数据库介质磁带库"""

    async def create(self, header: TapeHeader) -> Tape:
        raise NotImplementedError

    async def open(self, name: str, access: Access) -> Tape:
        raise NotImplementedError

    async def list(self) -> list[TapeHeader]:
        raise NotImplementedError
