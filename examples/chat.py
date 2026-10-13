# /// script
# requires-python = ">=3.13"
# dependencies = ["openai>=2", "tapehead"]
#
# [tool.uv.sources]
# tapehead = { path = "..", editable = true }
# ///
"""用 OpenAI 兼容接口驱动 tapehead 的最小宿主, 磁带存在工作目录的 .tapes 下

    uv run examples/chat.py                    # 交互, 默认磁带 chat
    uv run examples/chat.py -t demo "读一下 README.md"   # 每个参数是一轮输入, 跑完退出

环境变量
- OPENAI_BASE_URL: 默认 http://localhost:8000/v1
- OPENAI_API_KEY: 默认 EMPTY
- TAPEHEAD_MODEL: 默认取服务端列出的第一个模型
"""

import argparse
import asyncio
import os
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

from openai import AsyncOpenAI, BadRequestError, omit
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from tapehead.core.delta import Delta, ReasoningDelta, TextDelta, ToolCallDelta, UsageDelta
from tapehead.core.event import Aborted, Generated, Returned, Yielded
from tapehead.core.head import Head
from tapehead.core.message import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from tapehead.core.provider import ContextOverflow
from tapehead.core.tape import Frame, Label
from tapehead.core.tool import ToolSpec
from tapehead.kit.read import read_tool
from tapehead.media.fs import FsSilo, FsTape

DIM, RESET = "\033[2m", "\033[0m"


class OpenAIProvider:
    """OpenAI 兼容接口的模型提供方"""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client
        self.model = model

    async def stream(self, messages: list[Message], tools: list[ToolSpec]) -> AsyncIterator[Delta]:
        try:
            chunks = await self.client.chat.completions.create(
                model=self.model,
                messages=[encode_message(message) for message in messages],
                tools=[encode_tool(spec) for spec in tools] if tools else omit,
                stream=True,
                stream_options={"include_usage": True},
            )
        except BadRequestError as error:
            if "maximum context length" in str(error):
                raise ContextOverflow(str(error)) from error
            raise

        ids: dict[int, str] = {}
        async for chunk in chunks:
            for choice in chunk.choices:
                if reasoning := getattr(choice.delta, "reasoning", None):
                    yield ReasoningDelta(text=reasoning)
                if choice.delta.content:
                    yield TextDelta(text=choice.delta.content)
                for call in choice.delta.tool_calls or []:
                    if call.id:
                        ids[call.index] = call.id
                    function = call.function
                    yield ToolCallDelta(
                        id=ids[call.index],
                        name=function.name if function else None,
                        arguments=(function.arguments or "") if function else "",
                    )
            if chunk.usage is not None:
                details = chunk.usage.prompt_tokens_details
                yield UsageDelta(
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    cached_tokens=(details.cached_tokens or 0) if details else 0,
                )


def encode_message(message: Message) -> ChatCompletionMessageParam:
    """把消息编码成 chat completions 的格式"""

    match message:
        case SystemMessage(content=content):
            return {"role": "system", "content": content}
        case UserMessage(content=content):
            return {"role": "user", "content": content}
        case AssistantMessage(content=content, reasoning=reasoning, tool_calls=calls):
            encoded: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": content}
            if reasoning:
                encoded["reasoning"] = reasoning  # ty: ignore[invalid-key] vLLM 的扩展字段, 带回哪些由对话模板决定
            if calls:
                encoded["tool_calls"] = [
                    {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                    for call in calls
                ]
            return encoded
        case ToolMessage(call_id=call_id, content=content):
            return {"role": "tool", "tool_call_id": call_id, "content": content}


def encode_tool(spec: ToolSpec) -> ChatCompletionToolParam:
    """把工具定义编码成 chat completions 的格式"""

    return {
        "type": "function",
        "function": {"name": spec.name, "description": spec.description, "parameters": spec.parameters},
    }


def render(item: Frame | Delta) -> None:
    """把一轮里的增量和帧打印到终端, 推理变暗, 工具调用和结果各占一行"""

    match item:
        case ReasoningDelta(text=text):
            print(f"{DIM}{text}{RESET}", end="", flush=True)
        case TextDelta(text=text):
            print(text, end="", flush=True)
        case Frame(event=Generated(message=message)):
            print()
            for call in message.tool_calls:
                print(f"→ {call.name}({call.arguments})")
        case Frame(event=Returned(message=message)):
            head = message.content.splitlines()[0][:80] if message.content else ""
            print(f"{DIM}{'✗' if message.is_error else '←'} {head}{RESET}")
        case Frame(event=Aborted(error=error)):
            print(f"\n✗ {error}")
        case Frame(event=Yielded(reason=reason)) if reason != "completed":
            print(f"[{reason}]")
        case UsageDelta(input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached):
            print(f"{DIM}\n[tokens 输入 {input_tokens} 缓存 {cached} 输出 {output_tokens}]{RESET}", end="")


async def open_tape(silo: FsSilo, name: str) -> FsTape:
    """打开磁带, 不存在时新建"""

    try:
        return await silo.open(name)
    except FileNotFoundError:
        return await silo.create(Label(name=name, created_at=time.time()))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--tape", default="chat")
    parser.add_argument("prompts", nargs="*")
    args = parser.parse_args()

    client = AsyncOpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1"),
        api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
    )
    model = os.environ.get("TAPEHEAD_MODEL") or (await client.models.list()).data[0].id
    head = Head(
        OpenAIProvider(client, model),
        [read_tool(Path.cwd())],
        system_prompt=f"你是一个在 {Path.cwd()} 下工作的助手, 需要了解文件内容时用 read 工具读取",
    )
    tape = await open_tape(FsSilo(Path(".tapes")), args.tape)
    print(f"{DIM}{model} · 磁带 {args.tape} · 已有 {len(await tape.read())} 帧{RESET}")

    try:
        prompts = iter(args.prompts) if args.prompts else None
        while True:
            if prompts is None:
                prompt = input("\n> ").strip()
            elif (prompt := next(prompts, None)) is None:
                break
            else:
                print(f"\n> {prompt}")
            if prompt:
                async for item in head.run(tape, prompt):
                    render(item)
                print()
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        await tape.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]
    asyncio.run(main())
