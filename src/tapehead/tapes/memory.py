import time

from tapehead.event import AnyEvent
from tapehead.tapes.frame import Frame
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access


class MemoryTape:
    """存在内存里的磁带, 只有写句柄, 不处理翻录"""

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
