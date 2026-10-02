import os
from pathlib import Path

import msgspec

from tapehead.event import AnyEvent
from tapehead.media.mem import MemTape
from tapehead.tapes.frame import Frame
from tapehead.tapes.header import TapeHeader
from tapehead.tapes.tape import Access


class FsTape(MemTape):
    """文件磁带 JSONL"""

    def __init__(self, header: TapeHeader, frames_path: Path) -> None:
        super().__init__(header)
        decoder = msgspec.json.Decoder(Frame)
        self.frames = [decoder.decode(line) for line in frames_path.read_bytes().splitlines()]
        self.file = frames_path.open("ab")

    async def record(self, *events: AnyEvent) -> list[Frame]:
        recorded = await super().record(*events)
        for frame in recorded:
            self.file.write(msgspec.json.encode(frame) + b"\n")

        return recorded

    async def flush(self) -> None:
        self.file.flush()
        os.fsync(self.file.fileno())

    async def close(self) -> None:
        await self.flush()
        self.file.close()


class FsSilo:
    """文件系统介质磁带库"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    async def create(self, header: TapeHeader) -> FsTape:
        if header.origin is not None:
            raise NotImplementedError("翻录")
        frames_path = self.directory / f"{header.name}.jsonl"
        frames_path.touch(exist_ok=False)
        (self.directory / f"{header.name}.header.json").write_bytes(msgspec.json.encode(header))

        return FsTape(header, frames_path)

    async def open(self, name: str, access: Access) -> FsTape:
        if access != "write":
            raise NotImplementedError("读句柄")
        header = msgspec.json.decode((self.directory / f"{name}.header.json").read_bytes(), type=TapeHeader)

        return FsTape(header, self.directory / f"{name}.jsonl")

    async def list(self) -> list[TapeHeader]:
        paths = sorted(self.directory.glob("*.header.json"))

        return [msgspec.json.decode(path.read_bytes(), type=TapeHeader) for path in paths]
