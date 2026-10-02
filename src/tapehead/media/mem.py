import time

from tapehead.event import AnyEvent
from tapehead.tapes.frame import Frame
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access


class MemTape:
    """内存磁带"""

    def __init__(self, header: TapeHeader) -> None:
        self.header = header
        self.frames: list[Frame] = []

    @property
    def access(self) -> Access:
        return "write"

    @property
    def head(self) -> int:
        return len(self.frames)

    async def record(self, *events: AnyEvent) -> list[Frame]:
        now = time.time()
        recorded = [Frame(seq=self.head + i, time=now, event=event) for i, event in enumerate(events)]
        self.frames.extend(recorded)

        return recorded

    async def read(self, start: int = 0, stop: int | None = None) -> list[Frame]:
        return self.frames[start:stop]

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


class MemSilo:
    """内存磁带库"""

    def __init__(self) -> None:
        self.tapes: dict[str, MemTape] = {}

    async def create(self, header: TapeHeader) -> MemTape:
        if header.origin is not None:
            raise NotImplementedError("翻录")
        if header.name in self.tapes:
            raise FileExistsError(header.name)
        self.tapes[header.name] = MemTape(header)

        return self.tapes[header.name]

    async def open(self, name: str, access: Access) -> MemTape:
        if access != "write":
            raise NotImplementedError("读句柄")

        return self.tapes[name]

    async def list(self) -> list[TapeHeader]:
        return [tape.header for tape in self.tapes.values()]
