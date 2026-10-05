from msgspec import Struct

from tapehead.event import AnyEvent


class Frame(Struct):
    """磁带上的一帧, recorded_at 由 Tape.record 填写, 位置由介质提供"""

    recorded_at: float
    event: AnyEvent
