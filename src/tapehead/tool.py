import asyncio
import functools
import inspect
import typing
from collections.abc import Callable
from types import FunctionType
from typing import Any, overload

from msgspec import Struct, defstruct
from msgspec.json import encode


def derive_args(func: FunctionType, name: str) -> type[Struct]:
    """从函数签名生成参数 Struct, 类型注解里的 Annotated 元数据原样保留"""

    hints = typing.get_type_hints(func, include_extras=True)
    fields = []
    for param in inspect.signature(func).parameters.values():
        annotation = hints.get(param.name, Any)
        fields.append((param.name, annotation) if param.default is param.empty else (param.name, annotation, param.default))

    return defstruct(name, fields)


class Tool:
    """工具, 名称, 描述, 参数省略时从函数推导"""

    def __init__(
        self,
        func: FunctionType,
        name: str | None = None,
        description: str | None = None,
        parameters: type[Struct] | None = None,
    ) -> None:
        self.func = func
        self.name = name or func.__name__
        self.description = description if description is not None else (inspect.getdoc(func) or "")
        self.spread = parameters is None
        self.args = derive_args(func, self.name) if parameters is None else parameters

    async def call(self, args: Struct) -> str:
        """执行一次调用, 返回给模型看的结果, 失败时直接抛异常

        参数
        - args: 已经校验过的参数
        """

        if self.spread:
            run = functools.partial(self.func, **{field: getattr(args, field) for field in self.args.__struct_fields__})
        else:
            run = functools.partial(self.func, args)
        result = await run() if inspect.iscoroutinefunction(self.func) else await asyncio.to_thread(run)

        return result if isinstance(result, str) else encode(result).decode()


@overload
def tool(func: FunctionType, /) -> Tool: ...


@overload
def tool(
    *, name: str | None = None, description: str | None = None, parameters: type[Struct] | None = None
) -> Callable[[FunctionType], Tool]: ...


def tool(
    func: FunctionType | None = None,
    /,
    *,
    name: str | None = None,
    description: str | None = None,
    parameters: type[Struct] | None = None,
) -> Tool | Callable[[FunctionType], Tool]:
    """定义工具

    参数
    - func: 被包装的函数, 同步函数会放到线程里执行, 返回值不是 str 时编码成 JSON 文本
    - name: 工具名, 省略时用函数名, 工具名会录上磁带, 改名等于改历史
    - description: 给模型看的描述, 省略时用函数完整的 docstring, 它会原样成为提示词, 所以要完整描述这个工具
    - parameters: 参数 Struct, 省略时从类型注解推导, 给出时函数接收这个 Struct 的实例
    """

    def wrap(func: FunctionType) -> Tool:
        return Tool(func, name, description, parameters)

    return wrap(func) if func is not None else wrap
