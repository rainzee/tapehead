from collections.abc import AsyncIterator

from tapehead.delta import AnyDelta
from tapehead.tapes.frame import Frame

type StreamItem = Frame | AnyDelta


class AsyncStreamEvents:
    """一次运行的实时输出, Frame 是已落带的事实, Delta 是不落带的增量"""

    def __init__(self, iterator: AsyncIterator[StreamItem]) -> None:
        self._iterator = iterator

    def __aiter__(self) -> AsyncIterator[StreamItem]:
        return self._iterator
