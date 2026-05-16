"""DGM 极速烟雾测试 — 只跑 3 个任务,验证整条管道能跑通。

不测 agent 能力,只测:
- ollama 连接 OK
- task 发现/setup 工作
- agent loop 跑得起来
- verify_cmd 解析正确
- LCB / 决策逻辑无 bug
- meta-agent 能改文件
- 越权检查工作
- 报表输出正常

机制:把其他任务目录改名加 `_smoke_` 前缀让 run_eval 跳过,跑完无论
成功失败都改回来 (try/finally 保证)。

用法:
    python eval/smoke_test.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASKS_DIR = Path(__file__).parent / "tasks"

# 留下的 3 个任务:一个 train original、一个 train quixbugs、一个 holdout quixbugs
KEEP = {"task_01_logic_bug", "qb_gcd", "qb_to_base"}
HIDDEN_PREFIX = "_smoke_"


def hide_other_tasks() -> list[Path]:
    """把不在 KEEP 里的任务目录加 _smoke_ 前缀。返回被改名的列表。"""
    hidden = []
    for d in TASKS_DIR.iterdir():
        if (d.is_dir() and d.name not in KEEP
                and not d.name.startswith("_")):
            new_path = TASKS_DIR / f"{HIDDEN_PREFIX}{d.name}"
            d.rename(new_path)
            hidden.append(new_path)
    return hidden


def restore_tasks(hidden: list[Path]) -> None:
    """改回原名"""
    for d in hidden:
        if d.exists() and d.name.startswith(HIDDEN_PREFIX):
            original = TASKS_DIR / d.name[len(HIDDEN_PREFIX):]
            d.rename(original)


def main() -> int:
    print(f"[smoke] 保留任务: {sorted(KEEP)}")

    # Sanity check: KEEP 里的任务都得存在
    missing = [t for t in KEEP if not (TASKS_DIR / t).is_dir()]
    if missing:
        print(f"[!] 缺失任务: {missing}")
        print(f"    (qb_* 任务用 build_quixbugs_tasks.py 生成)")
        return 1

    hidden = hide_other_tasks()
    print(f"[smoke] 临时隐藏 {len(hidden)} 个其他任务\n")

    try:
        cmd = [
            sys.executable, "-u",
            str(Path(__file__).parent / "evolve.py"),
            "--generations", "1",
            "--quick",
            "--max-rounds", "1",
        ]
        print(f"[smoke] 执行: {' '.join(cmd)}\n" + "="*60)
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
        print("="*60)
        print(f"[smoke] evolve 退出码: {result.returncode}")
        return result.returncode
    finally:
        print(f"\n[smoke] 还原 {len(hidden)} 个任务...")
        restore_tasks(hidden)
        # 二次确认: 检查 _smoke_ 前缀残留
        leftover = [d for d in TASKS_DIR.iterdir() if d.name.startswith(HIDDEN_PREFIX)]
        if leftover:
            print(f"[!] 还有 {len(leftover)} 个未还原: {[d.name for d in leftover]}")
            return 2
        print(f"[smoke] 全部任务已还原")


if __name__ == "__main__":
    raise SystemExit(main())
