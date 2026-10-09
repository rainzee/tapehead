import os
from pathlib import Path
from typing import Any

from msgspec import convert
from msgspec.json import Decoder, decode, encode

from tapehead.event import Event
from tapehead.media.mem import MemTape
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import FORMAT, Label
from tapehead.tapes.tape import Access


def read_label(path: Path) -> Label:
    """读取磁带标签, 格式版本不是当前版本时拒绝, 不去解码帧

    参数
    - path: 标签文件
    """

    data: dict[str, Any] = decode(path.read_bytes())
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: 磁带格式 {data.get('format')} 不受支持, 当前版本是 {FORMAT}")

    return convert(data, Label)


class FsTape(MemTape):
    """文件磁带 JSONL"""

    def __init__(self, label: Label, frames_path: Path) -> None:
        super().__init__(label)
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

    async def create(self, label: Label) -> FsTape:
        if label.origin is not None:
            raise NotImplementedError("翻录")
        frames_path = self.directory / f"{label.name}.jsonl"
        frames_path.touch(exist_ok=False)
        (self.directory / f"{label.name}.label.json").write_bytes(encode(label))

        return FsTape(label, frames_path)

    async def open(self, name: str, access: Access) -> FsTape:
        if access != "write":
            raise NotImplementedError("读句柄")
        label = read_label(self.directory / f"{name}.label.json")

        return FsTape(label, self.directory / f"{name}.jsonl")

    async def list(self) -> list[Label]:
        paths = sorted(self.directory.glob("*.label.json"))

        return [read_label(path) for path in paths]
