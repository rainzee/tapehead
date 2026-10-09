import os
from pathlib import Path
from typing import Any

from msgspec import convert
from msgspec.json import Decoder, decode, encode

from tapehead.event import Event
from tapehead.media.mem import MemTape
from tapehead.tapes.frame import Frame
from tapehead.tapes.header import FORMAT, TapeHeader
from tapehead.tapes.tape import Access


def read_header(path: Path) -> TapeHeader:
    """读取磁带头, 格式版本不是当前版本时拒绝, 不去解码帧

    参数
    - path: 磁带头文件
    """

    data: dict[str, Any] = decode(path.read_bytes())
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: 磁带格式 {data.get('format')} 不受支持, 当前版本是 {FORMAT}")

    return convert(data, TapeHeader)


class FsTape(MemTape):
    """文件磁带 JSONL"""

    def __init__(self, header: TapeHeader, frames_path: Path) -> None:
        super().__init__(header)
        decoder = Decoder(Frame)
        self.frames = [decoder.decode(line) for line in frames_path.read_bytes().splitlines()]
        self.file = frames_path.open("ab")

    async def record(self, *events: Event) -> list[Frame]:
        recorded = await super().record(*events)
        for frame in recorded:
            self.file.write(encode(frame) + b"\n")

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
        (self.directory / f"{header.name}.header.json").write_bytes(encode(header))

        return FsTape(header, frames_path)

    async def open(self, name: str, access: Access) -> FsTape:
        if access != "write":
            raise NotImplementedError("读句柄")
        header = read_header(self.directory / f"{name}.header.json")

        return FsTape(header, self.directory / f"{name}.jsonl")

    async def list(self) -> list[TapeHeader]:
        paths = sorted(self.directory.glob("*.header.json"))

        return [read_header(path) for path in paths]
