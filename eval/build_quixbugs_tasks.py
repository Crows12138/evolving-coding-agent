"""把 QuixBugs 改造成 nano-claude 的 eval 任务格式。

QuixBugs 是 40 个经典算法的单行 bug 集合 (MIT License)。
这个 adapter 把它们转成 eval/tasks/qb_<name>/{issue.md, X.py, test_X.py, X.json}
的扁平结构，跟现有 task 格式兼容。

用法:
    1. 克隆 QuixBugs:
       git clone https://github.com/jkoppel/QuixBugs eval/_quixbugs

    2. 生成任务:
       python eval/build_quixbugs_tasks.py

    3. (可选) 验证生成的任务确实是 buggy:
       python eval/build_quixbugs_tasks.py --verify

    4. 删除已生成的任务重来:
       python eval/build_quixbugs_tasks.py --clean
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

QUIXBUGS_DEFAULT = Path(__file__).parent / "_quixbugs"
TASKS_DIR = Path(__file__).parent / "tasks"

# 跳过特定 QuixBugs 程序 — bug 触发死循环、eval 会卡住的
# bitcount: n ^= n-1 在 Python 任意精度整数下永不终止
# sqrt:     `while abs(x - approx) > epsilon` 比错对象,Newton 迭代永不收敛
SKIP_PROGRAMS = {"bitcount", "sqrt"}

ISSUE_TEMPLATE = """`{name}.py` 中存在 bug，导致 `test_{name}.py` 中的测试失败。

请：
1. 用 Read 工具读 `{name}.py`，理解它要实现什么算法
2. 用 Bash 跑 `python -m pytest test_{name}.py -x` 看具体哪个测试 fail
3. 定位错误的那一行并用 Edit 修复

注意：bug 是单行级别的小错误（off-by-one、错误运算符、错误初值等），
不需要重写算法，找到错误的那一行改掉即可。不要修改测试文件。
"""

# 自包含的 testdata 加载器，写在每个 test 文件开头取代 QuixBugs 的 load_testdata
TESTDATA_HELPER = '''import json as _json
import os as _os


def load_json_testcases(name):
    """从同目录的 <name>.json 加载 jsonl 测试数据。"""
    p = _os.path.join(_os.path.dirname(__file__), f"{name}.json")
    with open(p) as f:
        return [_json.loads(line) for line in f]


'''


def rewrite_test(original: str) -> str:
    """改写 QuixBugs 测试文件，让它在扁平的 task 目录里能跑。

    原始结构:
        from load_testdata import load_json_testcases
        if pytest.use_correct:
            from correct_python_programs.X import X
        else:
            from python_programs.X import X

    改成:
        <TESTDATA_HELPER>
        from X import X   # 同目录直接 import
    """
    out = original

    # 1) 去掉 load_testdata import (有的写在文件顶,有的在 try 块里)
    out = re.sub(
        r"^\s*from\s+load_testdata\s+import\s+load_json_testcases\s*$",
        "",
        out,
        flags=re.MULTILINE,
    )

    # 2) 折叠 if pytest.use_correct: ... else: ... 块 → 只保留 else 分支的 buggy import
    #    多种写法都有, 用 DOTALL 抓
    out = re.sub(
        r"if\s+pytest\.use_correct\s*:.*?else\s*:\s*\n\s*from\s+python_programs\.(\w+)\s+import\s+([^\n]+)",
        r"from \1 import \2",
        out,
        flags=re.DOTALL,
    )

    # 3) 兜底：所有 from python_programs.X / from correct_python_programs.X
    #    都改成同目录 import
    out = re.sub(
        r"from\s+python_programs\.(\w+)\s+import",
        r"from \1 import",
        out,
    )
    out = re.sub(
        r"from\s+correct_python_programs\.(\w+)\s+import",
        r"from \1 import",
        out,
    )

    # 4) 在最顶端插入 testdata helper
    return TESTDATA_HELPER + out


def needs_node(program_text: str) -> bool:
    """检查程序是否依赖 node.py (图/链表算法)。"""
    return bool(re.search(r"\bfrom\s+node\b|\bimport\s+node\b", program_text))


def build_task(program_name: str, quixbugs_root: Path) -> Path | None:
    """生成单个 task 目录, 失败返回 None。"""
    program_file = quixbugs_root / "python_programs" / f"{program_name}.py"
    test_file = quixbugs_root / "python_testcases" / f"test_{program_name}.py"
    json_file = quixbugs_root / "json_testcases" / f"{program_name}.json"

    if not program_file.exists() or not test_file.exists():
        return None

    task_dir = TASKS_DIR / f"qb_{program_name}"
    task_dir.mkdir(exist_ok=True)

    # 1. buggy 实现
    program_text = program_file.read_text(encoding="utf-8")
    (task_dir / f"{program_name}.py").write_text(program_text, encoding="utf-8")

    # 2. 改写测试文件 (放到 node.py 检查前 — 测试也可能引用 node)
    test_text = test_file.read_text(encoding="utf-8")
    new_test = rewrite_test(test_text)
    (task_dir / f"test_{program_name}.py").write_text(new_test, encoding="utf-8")

    # 3. node.py — 程序或测试任一引用了就带过来
    if needs_node(program_text) or needs_node(test_text):
        node_file = quixbugs_root / "python_programs" / "node.py"
        if node_file.exists():
            shutil.copy(node_file, task_dir / "node.py")

    # 4. JSON 测试数据
    if json_file.exists():
        shutil.copy(json_file, task_dir / f"{program_name}.json")

    # 5. issue.md
    (task_dir / "issue.md").write_text(
        ISSUE_TEMPLATE.format(name=program_name), encoding="utf-8"
    )

    return task_dir


def verify_task_is_buggy(task_dir: Path) -> tuple[bool, str]:
    """跑 pytest 确认任务确实 fail。返回 (是 buggy, 输出摘要)。

    Buggy = pytest exit code != 0 (有测试失败)
    如果 pass = 适配器有问题或者这道题碰巧没复现 bug, 需要人工检查
    """
    name = task_dir.name.removeprefix("qb_")
    test_file = f"test_{name}.py"
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-x", "--tb=no", "-q"],
            cwd=task_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        is_buggy = r.returncode != 0
        summary = (r.stdout[-200:] if r.stdout else "") + (
            r.stderr[-200:] if r.stderr else ""
        )
        return is_buggy, summary.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QuixBugs eval tasks")
    parser.add_argument(
        "--quixbugs",
        type=Path,
        default=QUIXBUGS_DEFAULT,
        help=f"QuixBugs 仓库路径 (默认 {QUIXBUGS_DEFAULT})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="先删除所有 eval/tasks/qb_* 任务",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="生成后跑 pytest 确认每个任务确实 fail (buggy)",
    )
    args = parser.parse_args()

    if not args.quixbugs.exists():
        print(f"[!] 未找到 QuixBugs: {args.quixbugs}")
        print(f"    先克隆: git clone https://github.com/jkoppel/QuixBugs {args.quixbugs}")
        return 1

    if args.clean:
        n = 0
        for d in TASKS_DIR.glob("qb_*"):
            shutil.rmtree(d)
            n += 1
        print(f"[clean] 删除了 {n} 个旧 qb_* 任务")

    program_dir = args.quixbugs / "python_programs"
    programs = sorted(
        f.stem for f in program_dir.glob("*.py")
        if f.name != "node.py" and f.stem not in SKIP_PROGRAMS
    )

    built: list[str] = []
    skipped: list[str] = []
    for name in programs:
        result = build_task(name, args.quixbugs)
        if result:
            built.append(name)
        else:
            skipped.append(name)

    print(f"\n[build] 生成 {len(built)} 个任务,跳过 {len(skipped)} 个")
    if skipped:
        print(f"  跳过 (缺 program 或 test 文件): {', '.join(skipped)}")

    if args.verify:
        print(f"\n[verify] 跑 pytest 确认每个任务都是 buggy...")
        unexpectedly_passing: list[tuple[str, str]] = []
        broken: list[tuple[str, str]] = []
        for name in built:
            task_dir = TASKS_DIR / f"qb_{name}"
            is_buggy, summary = verify_task_is_buggy(task_dir)
            if not is_buggy:
                if "TIMEOUT" in summary or "ERROR" in summary or "ImportError" in summary:
                    broken.append((name, summary[:100]))
                else:
                    unexpectedly_passing.append((name, summary[:100]))

        if broken:
            print(f"\n  [BROKEN] {len(broken)} 个任务跑不起来 (适配问题):")
            for name, s in broken:
                print(f"    qb_{name}: {s}")
        if unexpectedly_passing:
            print(f"\n  [UNEXPECTED PASS] {len(unexpectedly_passing)} 个任务居然通过了 (bug 没复现):")
            for name, s in unexpectedly_passing:
                print(f"    qb_{name}: {s}")

        ok_count = len(built) - len(broken) - len(unexpectedly_passing)
        print(f"\n  [verify] {ok_count}/{len(built)} 个任务确认为 buggy")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
