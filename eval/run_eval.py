"""Mini SWE-bench — 本地 Agent 问题解决能力评测

每个任务 = 一个 bug 项目 + issue 描述 + 测试用例
Agent 需要读 issue → 分析代码 → 修复 → 让测试通过

用法:
    cd evolving-coding-agent
    python eval/run_eval.py [--max-rounds 3] [--model ollama/qwen3.5-16k]
"""

import sys
import os
import shutil
import subprocess
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# 确保能 import 项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from loop import improvement_loop
from config import load_config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

TASKS_DIR = Path(__file__).parent / "tasks"
WORK_DIR = Path(__file__).parent / "_workdir"


def discover_tasks() -> list[dict]:
    """发现所有任务"""
    tasks = []
    for task_dir in sorted(TASKS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith("_"):
            continue
        issue_file = task_dir / "issue.md"
        if not issue_file.exists():
            continue

        # 找测试文件
        test_files = list(task_dir.glob("test_*.py"))
        if not test_files:
            continue

        # 找源文件（非 test_ 开头的 .py）
        src_files = [f for f in task_dir.glob("*.py") if not f.name.startswith("test_")]

        tasks.append({
            "name": task_dir.name,
            "dir": task_dir,
            "issue": issue_file.read_text(encoding="utf-8").strip(),
            "test_files": [f.name for f in test_files],
            "src_files": [f.name for f in src_files],
        })
    return tasks


def setup_workdir(task: dict) -> Path:
    """为任务创建工作目录（复制源文件）"""
    work = WORK_DIR / task["name"]
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(task["dir"], work)
    return work


def run_task(task: dict, config: dict, max_rounds: int) -> dict:
    """运行单个任务"""
    work = setup_workdir(task)
    orig_cwd = os.getcwd()
    os.chdir(work)

    test_cmd = f"python -m pytest {' '.join(task['test_files'])} -x"
    issue_text = task["issue"]
    src_names = ", ".join(task["src_files"])

    task_desc = (
        f"Issue: {issue_text}\n\n"
        f"修复 {src_names} 中的 bug，让所有测试通过。不要修改测试文件。"
    )

    start = time.time()
    try:
        result = improvement_loop(
            task=task_desc,
            verify_cmd=test_cmd,
            config=config,
            max_rounds=max_rounds,
        )
        duration = time.time() - start
        # 取最后一轮的验证输出
        last_verify = ""
        if result["history"]:
            last_verify = result["history"][-1].get("verify_output", "")
        return {
            "name": task["name"],
            "issue": issue_text,
            "passed": result["passed"],
            "rounds": result["rounds"],
            "duration": duration,
            "verify_output": last_verify,
        }
    except KeyboardInterrupt:
        return {
            "name": task["name"],
            "passed": False,
            "rounds": -1,
            "duration": time.time() - start,
            "error": "interrupted",
        }
    except Exception as e:
        return {
            "name": task["name"],
            "passed": False,
            "rounds": -1,
            "duration": time.time() - start,
            "error": str(e),
        }
    finally:
        os.chdir(orig_cwd)


def main():
    parser = argparse.ArgumentParser(description="Mini SWE-bench eval")
    parser.add_argument("--max-rounds", type=int, default=3, help="每个任务最大循环轮数")
    parser.add_argument("--model", type=str, default=None, help="模型名称")
    args = parser.parse_args()

    config = load_config()
    if args.model:
        config["model"] = args.model
    config["permission_mode"] = "accept-all"

    # 每次 eval 强制清理 workdir
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    tasks = discover_tasks()
    if not tasks:
        console.print("[red]没有找到任务[/red]")
        return

    console.print(Panel(
        f"任务数: {len(tasks)}\n模型: {config['model']}\n每任务最大轮数: {args.max_rounds}",
        title="Mini SWE-bench 评测",
        border_style="cyan",
    ))

    results = []
    for i, task in enumerate(tasks):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(f"[bold cyan]任务 {i+1}/{len(tasks)}: {task['name']}[/bold cyan]")
        console.print(f"[dim]{task['issue'][:100]}[/dim]")
        console.print(f"[bold]{'='*60}[/bold]")

        r = run_task(task, config, args.max_rounds)
        results.append(r)

        status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        console.print(f"\n  {status} ({r['rounds']} rounds, {r['duration']:.1f}s)")

    # 汇总
    console.print(f"\n{'='*60}")
    table = Table(title="评测结果")
    table.add_column("任务", style="cyan")
    table.add_column("结果", justify="center")
    table.add_column("轮数", justify="right")
    table.add_column("耗时", justify="right")

    passed = sum(1 for r in results if r["passed"])
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        style = "green" if r["passed"] else "red"
        table.add_row(
            r["name"],
            f"[{style}]{status}[/{style}]",
            str(r["rounds"]),
            f"{r['duration']:.1f}s",
        )

    console.print(table)

    # 计算综合评分: pass_rate / avg_time
    # 通过率越高越好，时间越短越好
    pass_rate = passed / len(results) * 100
    total_time = sum(r["duration"] for r in results)
    avg_time = total_time / len(results) if results else 1

    # 效率分 = 通过率 / 平均耗时（秒）× 60
    # 含义：每分钟能解决多少百分比的任务
    efficiency = (pass_rate / avg_time * 60) if avg_time > 0 else 0

    console.print(f"\n[bold]通过率: {passed}/{len(results)} ({pass_rate:.0f}%)[/bold]")
    console.print(f"[bold]总耗时: {total_time:.1f}s, 平均: {avg_time:.1f}s/任务[/bold]")
    console.print(f"[bold]效率分: {efficiency:.1f} (通过率%/分钟)[/bold]")

    # 保存结果
    result_file = Path(__file__).parent / f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_file.write_text(json.dumps({
        "model": config["model"],
        "max_rounds": args.max_rounds,
        "score": f"{passed}/{len(results)}",
        "pct": pass_rate,
        "total_time": total_time,
        "avg_time": avg_time,
        "efficiency": efficiency,
        "results": results,
    }, ensure_ascii=False, indent=2))
    console.print(f"[dim]结果保存: {result_file}[/dim]")


if __name__ == "__main__":
    main()
