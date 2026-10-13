from collections import deque
from collections.abc import AsyncIterator, Sequence

from tapehead.core.delta import Delta
from tapehead.core.message import Message
from tapehead.core.play import Context
from tapehead.core.tool import ToolDefinition

type Step = Sequence[Delta | Exception] | Exception


class ScriptedProvider:
    """按脚本回放模型调用的假提供方"""

    def __init__(self, *steps: Step) -> None:
        """
        参数
        - steps: 每次模型调用按顺序消耗一步, 一步是按序给出的增量, 其中的异常在轮到它时抛出,
          用来模拟流到一半失败, 单独一个异常表示调用一开始就失败, 比如 ContextOverflow
        """

        self.steps: deque[Step] = deque(steps)
        self.calls: list[Context] = []

    async def stream(self, messages: list[Message], tools: list[ToolDefinition]) -> AsyncIterator[Delta]:
        """记下这次调用的输入, 再给出脚本的下一步, 脚本用完时抛出 AssertionError

        参数
        - messages: 从磁带回放得出的上下文
        - tools: 这次调用可用的工具定义
        """

        self.calls.append(Context(messages=list(messages), tools=list(tools)))
        if not self.steps:
            raise AssertionError(f"脚本已用完, 第 {len(self.calls)} 次模型调用没有对应的步骤")

        step = self.steps.popleft()
        if isinstance(step, Exception):
            raise step
        for item in step:
            if isinstance(item, Exception):
                raise item
            yield item
