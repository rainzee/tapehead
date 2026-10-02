from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import msgspec

from tapehead.delta import AnyDelta, ReasoningDelta, TextDelta
from tapehead.event import Usage
from tapehead.message import Message
from tapehead.tool import Tool


class PromptDetails(msgspec.Struct):
    """chunk 里的提示词用量明细"""

    cached_tokens: int | None = None


class ChunkUsage(msgspec.Struct):
    """chunk 里的 token 用量"""

    prompt_tokens: int
    completion_tokens: int
    prompt_tokens_details: PromptDetails | None = None


class ChoiceDelta(msgspec.Struct):
    """chunk 里的增量, 推理内容在不同 vLLM 版本里叫 reasoning_content 或 reasoning"""

    content: str | None = None
    reasoning_content: str | None = None
    reasoning: str | None = None


class Choice(msgspec.Struct):
    """chunk 里的一个候选"""

    delta: ChoiceDelta


class Chunk(msgspec.Struct):
    """流式响应里的一个 chunk, 用量在 choices 为空的最后一个 chunk 里"""

    choices: list[Choice] = []
    usage: ChunkUsage | None = None


class OpenAIModel:
    """OpenAI 兼容的 chat completions, 对接 vLLM 上的 Qwen 系列

    参数
    - base_url: 网关地址, 到 /v1 为止
    - api_key: 访问密钥
    - model: 模型名
    - extra_body: 并入请求体的额外字段, 如 chat_template_kwargs
    - timeout: 读超时秒数, 首个 token 之前也受它约束
    """

    def __init__(
        self, base_url: str, api_key: str, model: str, extra_body: dict[str, Any] | None = None, timeout: float = 600.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.extra_body = extra_body or {}
        self.timeout = timeout

    async def stream(self, messages: list[Message], tools: Sequence[Tool[Any]]) -> AsyncIterator[AnyDelta | Usage]:
        if tools:
            raise NotImplementedError("工具调用")
        body = {
            "model": self.model,
            "messages": [self.encode_message(message) for message in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            **self.extra_body,
        }
        decoder = msgspec.json.Decoder(Chunk)
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client,
            client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as response,
        ):
            if response.status_code >= 400:
                raise RuntimeError(f"{response.status_code}: {(await response.aread()).decode()}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                chunk = decoder.decode(data)
                for choice in chunk.choices:
                    if reasoning := choice.delta.reasoning_content or choice.delta.reasoning:
                        yield ReasoningDelta(text=reasoning)
                    if choice.delta.content:
                        yield TextDelta(text=choice.delta.content)
                if chunk.usage is not None:
                    details = chunk.usage.prompt_tokens_details
                    yield Usage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                        cached_tokens=(details.cached_tokens or 0) if details else 0,
                    )

    @staticmethod
    def encode_message(message: Message) -> dict[str, Any]:
        if message.tool_uses or message.tool_call_id:
            raise NotImplementedError("工具调用")

        return {"role": message.role, "content": message.content}
