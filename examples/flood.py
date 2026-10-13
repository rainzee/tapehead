# /// script
# requires-python = ">=3.13"
# dependencies = ["openai>=2", "tapehead"]
#
# [tool.uv.sources]
# tapehead = { path = "..", editable = true }
# ///
"""实验: 工具返回大量文本时上下文会怎样, 复用 chat.py 的提供方和渲染

uv run examples/flood.py -t flood --lines 8000 "在日志里搜一下 timeout, 告诉我最常见的路径"
uv run examples/flood.py -t flood --compact ...    # 溢出时压到最后一个切点
"""

import argparse
import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path

from chat import OpenAIProvider, open_tape, render
from openai import AsyncOpenAI

from tapehead.event import Compacted
from tapehead.head import Head
from tapehead.media.fs import FsSilo
from tapehead.message import UserMessage
from tapehead.tapes.frame import Frame
from tapehead.tapes.play import cuts
from tapehead.tool import tool

PATHS = ["/api/orders", "/api/users", "/api/search", "/api/payments", "/health"]


def fake_logs(pattern: str, lines: int) -> str:
    """生成确定的假日志, 每行都包含 pattern"""

    rows = []
    for i in range(lines):
        digest = hashlib.sha1(f"{pattern}{i}".encode()).hexdigest()
        path = PATHS[int(digest[:2], 16) % len(PATHS)]
        rows.append(
            f"2026-10-12T{i // 3600 % 24:02d}:{i // 60 % 60:02d}:{i % 60:02d} WARN {pattern} id={digest[:16]} path={path}"
        )

    return "\n".join(rows)


async def compact_to_last_cut(frames: list[Frame]) -> Compacted | None:
    """压到最后一个切点, 摘要只写占位"""

    available = cuts(frames)
    print(f"\n[compactor 可选切点 {available}]")
    if not available:
        return None

    return Compacted(start=available[-1], message=UserMessage(content="[此前的对话已省略]"))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--tape", default="flood")
    parser.add_argument("--lines", type=int, default=8000)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("prompts", nargs="+")
    args = parser.parse_args()

    @tool
    def grep_logs(pattern: str) -> str:
        """在服务日志里搜索包含 pattern 的行, 返回所有匹配行"""

        return fake_logs(pattern, args.lines)

    client = AsyncOpenAI(base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1"), api_key="EMPTY")
    model = (await client.models.list()).data[0].id
    head = Head(
        OpenAIProvider(client, model),
        [grep_logs],
        system_prompt="你是运维助手, 需要查日志时用 grep_logs",
        compactor=compact_to_last_cut if args.compact else None,
    )
    tape = await open_tape(FsSilo(Path(".tapes")), args.tape)
    try:
        for prompt in args.prompts:
            print(f"\n> {prompt}")
            started = time.time()
            try:
                async for item in head.run(tape, prompt):
                    render(item)
            except Exception as error:  # noqa: BLE001 实验里要看到失败后带子的样子
                print(f"\n!! run 抛出 {type(error).__name__}")
            print(f"\n[{time.time() - started:.1f}s]")
    finally:
        await tape.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]
    asyncio.run(main())
