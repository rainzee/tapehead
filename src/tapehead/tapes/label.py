from msgspec import Struct

FORMAT = 1


class Origin(Struct):
    """翻录来源, 子带共享父带位置 < at 的前缀"""

    tape: str
    at: int


class Label(Struct):
    """磁带标签, 一盘磁带的元信息, 与帧分开存放, 不参与回放, format 决定帧按哪一版词汇和投影规则解读"""

    name: str
    created_at: float
    origin: Origin | None = None
    format: int = FORMAT
