from msgspec import Struct


class Label(Struct):
    """磁带标签, 创建时写定, 此后不变, 不读帧即可得到"""

    name: str
    created_at: float
