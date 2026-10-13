# 贡献约定

## 分层

- `src/tapehead/core/` 是内核, 定位和边界见 [docs/concepts/core.md](docs/concepts/core.md)
- core 只 import 标准库, msgspec 顶层和 core 自身, 由 `tests/test_layers.py` 守住
- 新东西能否进入 core, 按 core.md 末尾的两个问题判断, 拿不准时留在 core 之外

## 提交

- 标题写 `type(scope): summary`, 正文写为什么
- 改动 core 的提交用 `core` 作为 scope, 例如 `feat(core): ...`, `fix(core): ...`
- 其余部分还没有形成真正的分层, 暂不写 scope

## 检查

提交前全部通过:

    uv run pytest
    uv run ruff check .
    uv run ruff format --check src tests examples
    uvx ty check src tests
