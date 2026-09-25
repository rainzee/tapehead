from msgspec import Struct

from hermes.event import AnyEvent


class Frame(Struct):
    """磁带上的一帧, seq 和 time 只有 Tape.record 能填"""

    seq: int
    time: float
    event: AnyEvent
