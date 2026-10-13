import ast
import subprocess
import sys
from pathlib import Path

import tapehead.core


def imports(path: Path) -> list[str]:
    """列出一个模块 import 的全部模块名, 相对导入记为空串"""

    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module if node.level == 0 and node.module else "")

    return names


def test_the_core_depends_on_nothing_but_itself_and_msgspec() -> None:
    """内核只 import 标准库, msgspec 顶层和 tapehead.core 自身, 内核之外的一切都只能往内核方向依赖

    msgspec 的子模块也不行, 比如 msgspec.yaml 运行时需要 pyyaml
    """

    core = Path(tapehead.core.__file__).parent
    offenders = [
        f"{path.relative_to(core)}: {name or '相对导入'}"
        for path in sorted(core.rglob("*.py"))
        for name in imports(path)
        if not (name.split(".")[0] in sys.stdlib_module_names or name == "msgspec" or name.startswith("tapehead.core."))
    ]

    assert offenders == []


def test_testing_never_pulls_in_pytest() -> None:
    """宿主运行时导入 tapehead.testing 不会被迫装上 pytest"""

    code = "import sys, tapehead.testing; assert 'pytest' not in sys.modules, 'tapehead.testing 引入了 pytest'"
    subprocess.run([sys.executable, "-c", code], check=True)
