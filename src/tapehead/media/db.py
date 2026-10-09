from tapehead.tapes.label import Label
from tapehead.tapes.tape import Tape


class DbSilo:
    """数据库介质磁带库"""

    async def create(self, label: Label) -> Tape:
        raise NotImplementedError

    async def open(self, name: str) -> Tape:
        raise NotImplementedError

    async def list(self) -> list[Label]:
        raise NotImplementedError
