import os
from pathlib import Path

from msgspec.json import Decoder, decode, encode

from tapehead.event import Event
from tapehead.media.mem import MemTape
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label


def read_label(path: Path) -> Label:
    """读取磁带标签

    参数
    - path: 标签文件
    """

    return decode(path.read_bytes(), type=Label)


class FsTape(MemTape):
    """文件磁带 JSONL, 每帧一行, 以换行结尾

    最后一行没有换行, 说明写到一半时进程崩溃, 这一帧从未落带, 打开时截掉
    """

    def __init__(self, label: Label, frames_path: Path) -> None:
        super().__init__(label)
        data = frames_path.read_bytes()
        complete = data[: data.rfind(b"\n") + 1]
        if len(complete) < len(data):
            with frames_path.open("r+b") as file:
                file.truncate(len(complete))
        decoder = Decoder(Frame)
        self.frames = [decoder.decode(line) for line in complete.splitlines()]
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
        frames_path = self.directory / f"{label.name}.jsonl"
        frames_path.touch(exist_ok=False)
        (self.directory / f"{label.name}.label.json").write_bytes(encode(label))

        return FsTape(label, frames_path)

    async def open(self, name: str) -> FsTape:
        label = read_label(self.directory / f"{name}.label.json")

        return FsTape(label, self.directory / f"{name}.jsonl")

    async def list(self) -> list[Label]:
        paths = sorted(self.directory.glob("*.label.json"))

        return [read_label(path) for path in paths]
