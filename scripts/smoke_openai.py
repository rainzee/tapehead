"""对着真实网关跑一轮对话, 打印增量序列和落带的帧, 不进 CI

环境变量: TAPEHEAD_BASE_URL (到 /v1 为止), TAPEHEAD_API_KEY, TAPEHEAD_MODEL
参数: --no-think 关闭 Qwen 的思考
"""

import asyncio
import os
import sys
import time

from tapehead.head import Head
from tapehead.media.mem import MemTape
from tapehead.providers.openai import OpenAIProvider
from tapehead.tapes.frame import Frame
from tapehead.tapes.label import Label


async def main() -> None:
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}} if "--no-think" in sys.argv else None
    provider = OpenAIProvider(
        os.environ["TAPEHEAD_BASE_URL"], os.environ["TAPEHEAD_API_KEY"], os.environ["TAPEHEAD_MODEL"], extra_body
    )
    tape = MemTape(Label(name="smoke", created_at=time.time()))
    position = 0
    async for item in Head(provider).run(tape, "9.11 和 9.9 哪个大? 一句话回答"):
        if isinstance(item, Frame):
            print(f"\n[frame {position}] {item.event}")
            position += 1
        else:
            print(f"{type(item).__name__}({item.text!r})" if hasattr(item, "text") else item)


sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]
asyncio.run(main())
