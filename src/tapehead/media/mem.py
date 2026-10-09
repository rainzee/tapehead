import time

from tapehead.event import Event
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label
from tapehead.tapes.tape import Access


class MemTape:
    """内存磁带"""

    def __init__(self, label: Label) -> None:
        self.label = label
        self.frames: list[Frame] = []

    @property
    def access(self) -> Access:
        return "write"

    @property
    def head(self) -> int:
        return len(self.frames)

    async def record(self, *events: Event) -> list[Frame]:
        now = time.time()
        recorded = [Frame(recorded_at=now, event=event) for event in events]
        self.frames.extend(recorded)
        return recorded

    async def read(self, start: int = 0, stop: int | None = None) -> list[Frame]:
        return self.frames[start:stop]

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


class MemSilo:
    """内存介质磁带库"""

    def __init__(self) -> None:
        self.tapes: dict[str, MemTape] = {}

    async def create(self, label: Label) -> MemTape:
        if label.name in self.tapes:
            raise FileExistsError(label.name)
        self.tapes[label.name] = MemTape(label)

        return self.tapes[label.name]

    async def open(self, name: str, access: Access) -> MemTape:
        if access != "write":
            raise NotImplementedError("读句柄")

        return self.tapes[name]

    async def list(self) -> list[Label]:
        return [tape.label for tape in self.tapes.values()]
