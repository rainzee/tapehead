import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any, get_type_hints, overload

from msgspec import Struct, defstruct, structs
from msgspec.json import encode, schema_components


def derive_parameters(func: Callable, name: str) -> type[Struct]:
    """从函数签名生成参数 Struct, 类型注解里的 Annotated 元数据原样保留"""

    hints = get_type_hints(func, include_extras=True)
    fields = []

    for parameter in inspect.signature(func).parameters.values():
        annotation = hints.get(parameter.name, Any)
        if parameter.default is parameter.empty:
            fields.append((parameter.name, annotation))
        else:
            fields.append((parameter.name, annotation, parameter.default))

    return defstruct(name, fields)


class ToolSpec(Struct):
    """模型可见的工具定义"""

    name: str
    description: str
    parameters: dict[str, Any]


class Tool:
    """工具对象"""

    def __init__(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        parameters: type[Struct] | None = None,
    ) -> None:
        self.func = func
        self.name = name or func.__name__  # ty: ignore[unresolved-attribute]
        self.description = description if description is not None else (inspect.getdoc(func) or "")
        self.spread = parameters is None
        self.parameters = derive_parameters(func, self.name) if parameters is None else parameters

    @property
    def spec(self) -> ToolSpec:
        """给模型看的工具定义, 参数 schema 由参数 Struct 生成"""

        (ref,), components = schema_components([self.parameters], ref_template="#/$defs/{name}")
        schema = components.pop(ref["$ref"].removeprefix("#/$defs/"))
        if components:
            schema["$defs"] = components

        return ToolSpec(name=self.name, description=self.description, parameters=schema)

    async def call(self, arguments: Struct) -> str:
        """执行一次调用, 返回给模型看的结果, 失败时直接抛异常

        参数
        - arguments: 已经校验过的实参
        """

        if self.spread:
            run = functools.partial(self.func, **structs.asdict(arguments))
        else:
            run = functools.partial(self.func, arguments)
        result = await run() if inspect.iscoroutinefunction(self.func) else await asyncio.to_thread(run)

        return result if isinstance(result, str) else encode(result).decode()


@overload
def tool(func: Callable, /) -> Tool: ...


@overload
def tool(
    *, name: str | None = None, description: str | None = None, parameters: type[Struct] | None = None
) -> Callable[[Callable], Tool]: ...


def tool(
    func: Callable | None = None,
    /,
    *,
    name: str | None = None,
    description: str | None = None,
    parameters: type[Struct] | None = None,
) -> Tool | Callable[[Callable], Tool]:
    """定义工具

    参数
    - func: 被包装的函数, 同步函数会放到线程里执行, 返回值不是 str 时编码成 JSON 文本
    - name: 工具名, 省略时用函数名, 工具名会录上磁带, 改名等于改历史
    - description: 给模型看的描述, 省略时用函数完整的 docstring, 它会原样成为提示词, 所以要完整描述这个工具
    - parameters: 参数 Struct, 省略时从类型注解推导, 给出时函数接收这个 Struct 的实例
    """

    def wrap(func: Callable) -> Tool:
        return Tool(func, name, description, parameters)

    return wrap(func) if func is not None else wrap
