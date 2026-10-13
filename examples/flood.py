# /// script
# requires-python = ">=3.13"
# dependencies = ["openai>=2", "tapehead"]
#
# [tool.uv.sources]
# tapehead = { path = "..", editable = true }
# ///
"""实验: 工具返回大量文本时上下文会怎样, 复用 chat.py 的提供方和渲染

uv run examples/flood.py -t flood --lines 8000 "在日志里搜一下 timeout, 告诉我最常见的路径"
uv run examples/flood.py -t flood --prune ...      # 结果超过预算时录下即裁剪, 只留头尾
uv run examples/flood.py -t flood --compact ...    # 溢出时先裁剪过大的结果, 不够再压到最后一个切点
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

from tapehead.core.event import Compacted, Pruned, Returned
from tapehead.core.head import Head
from tapehead.core.message import ToolMessage, UserMessage
from tapehead.core.play import compaction, cuts
from tapehead.core.tape import Frame
from tapehead.kit.tool import tool
from tapehead.media.fs import FsSilo

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


BUDGET = 8000


async def head_tail(message: ToolMessage) -> str | None:
    """超过预算的结果只留头尾, 占位交代省略了多少"""

    content = message.content
    if len(content) <= BUDGET:
        return None
    keep = BUDGET // 2

    return f"{content[:keep]}\n[... 已省略中间 {len(content) - BUDGET} 字符 ...]\n{content[-keep:]}"


async def prune_then_compact(frames: list[Frame]) -> list[Compacted | Pruned]:
    """先把保留段里过大的工具结果裁成头尾, 没有可裁的再压到最后一个切点, 摘要交代丢了什么"""

    current = compaction(frames)
    floor = current.start if current is not None else 0
    done = {frame.event.target for frame in frames if isinstance(frame.event, Pruned)}
    edits: list[Compacted | Pruned] = []
    for i, frame in enumerate(frames[floor:], floor):
        if isinstance(frame.event, Returned) and i not in done and (content := await head_tail(frame.event.message)):
            edits.append(Pruned(target=i, message=ToolMessage(call_id=frame.event.message.call_id, content=content)))
    available = cuts(frames)
    print(f"\n[compactor 裁剪 {[edit.target for edit in edits if isinstance(edit, Pruned)]}, 可选切点 {available}]")
    if edits or not available:
        return edits

    dropped = sum(isinstance(frame.event, Returned) for frame in frames[floor : available[-1]])
    summary = f"[此前的对话已省略, 其中包括 {dropped} 个工具结果, 需要时请重新调用工具]"

    return [Compacted(start=available[-1], message=UserMessage(content=summary))]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--tape", default="flood")
    parser.add_argument("--lines", type=int, default=8000)
    parser.add_argument("--prune", action="store_true")
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
        pruner=head_tail if args.prune else None,
        compactor=prune_then_compact if args.compact else None,
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
