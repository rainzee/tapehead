from msgspec import Struct


class Label(Struct):
    """磁带标签, 一盘磁带的元信息, 与帧分开存放, 不参与回放"""

    name: str
    created_at: float
