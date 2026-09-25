from msgspec import Struct


class Origin(Struct):
    """翻录来源, 子带共享父带 seq < at 的前缀"""

    tape: str
    at: int


class TapeHeader(Struct):
    """磁带头, 与帧分开存放, 不参与回放"""

    name: str
    created_at: float
    origin: Origin | None = None
