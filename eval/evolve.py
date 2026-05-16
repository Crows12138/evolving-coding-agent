"""DGM self-evolution for the nano-claude coding agent.

This module is the coding-agent-specific *glue* on top of the generic
[dgm-runner](https://github.com/Crows12138/dgm-runner) library. The
library handles the evolution loop (N-eval, LCB, holdout, promote/rollback,
protected-file enforcement). This file provides:

  - HOLDOUT_TASKS / PROTECTED_FILES / EVOLVABLE_FILES (config for this agent)
  - META_AGENT_SYSTEM prompt for the meta-agent
  - CodingAgentEvolver — uses agent_run() to edit context.py / tools.py
  - Rich console formatting for live progress

Usage:
    python eval/evolve.py --generations 3 --max-rounds 2 --n-per-eval 5
    python eval/evolve.py --generations 1 --quick    # debug, N=1
"""
from __future__ import annotations

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from dgm_runner import (
    DGMRunner, ShellEvalRunner, Evolver, TaskResult,
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
CONTEXT_FILE = PROJECT_ROOT / "context.py"
TOOLS_FILE   = PROJECT_ROOT / "tools.py"
EVAL_SCRIPT  = Path(__file__).parent / "run_eval.py"

EVOLVABLE_FILES = [CONTEXT_FILE, TOOLS_FILE]

# Meta-layer files — meta-agent edits to these get reverted via git checkout.
# Paths are posix-relative-to-PROJECT_ROOT, matching `git diff --name-only`.
PROTECTED_FILES = {
    "eval/evolve.py",
    "eval/run_eval.py",
    "eval/explore.py",
    "config.py",
}


# Meta-agent's prompt. Not in EVOLVABLE_FILES → never gets edited by DGM.
# Worker prompt (context.py) evolves freely without corrupting this.
META_AGENT_SYSTEM = """你是 meta-agent，工作是分析一个 coding agent 的失败，\
并通过修改它的 system prompt / 工具实现来改进它。

工作流：
1. Read 提示中指定的 prompt / 工具文件 (context.py / tools.py)
2. 看 verify_output，识别 agent 的行为模式问题（不是单个 bug 的具体原因）
3. Edit 文件，改通用规则 / 工具实现，不写任务特定的解法
4. 不要执行验证 — 验证由外部进程负责，你改完就结束

规则：
- 你的产出是 prompt / 工具改动，不是修业务代码
- 保持文件语法正确，不改函数签名 (worker agent 依赖现有接口)
- 改 prompt 时问自己：「这条规则对这一类任务的所有失败情况都成立吗？」
- 不要把任务名、特定数据结构名、算法暗示写进 prompt"""


# 16/51 tasks (~31%). Diverse coverage so the holdout isn't biased toward
# any single algorithm or task style.
HOLDOUT_TASKS = {
    # 4 hand-rolled tasks (cross-paradigm)
    "task_03_state_machine",
    "task_07_config_parser",
    "task_10_matrix",
    "task_13_file_index",
    # 12 QuixBugs tasks (cross-category)
    "qb_mergesort",                    # sorting
    "qb_depth_first_search",           # graph
    "qb_shortest_path_length",         # graph
    "qb_topological_ordering",         # graph
    "qb_find_in_sorted",               # search
    "qb_levenshtein",                  # DP
    "qb_max_sublist_sum",              # DP
    "qb_knapsack",                     # math/DP
    "qb_sieve",                        # math
    "qb_to_base",                      # math
    "qb_rpn_eval",                     # string/stack
    "qb_is_valid_parenthesization",    # string
}


# ── Evolver: how to actually edit files given failures ────────────────────


class CodingAgentEvolver(Evolver):
    """Uses nano-claude's agent_run() with META_AGENT_SYSTEM to edit
    context.py / tools.py based on observed failures.

    DGM has already filtered out holdout failures, so the failure list this
    sees is train-only — the agent can't accidentally overfit to holdout.
    """

    def __init__(self, config: dict):
        self.config = config

    def evolve(
        self,
        failures: list[TaskResult],
        evolvable_files: list[Path],
    ) -> bool:
        from agent import (
            AgentState, run as agent_run,
            TextChunk, ToolStart, ToolEnd,
        )

        failed_names = ", ".join(f.name for f in failures)
        failure_dicts = [
            {
                "name": f.name,
                "rounds": f.rounds,
                "duration": f.duration,
                "verify_output": f.verify_output[:1500],
            }
            for f in failures
        ]

        current_context = CONTEXT_FILE.read_text(encoding="utf-8")
        current_tools_size = TOOLS_FILE.stat().st_size

        prompt = f"""你需要改进一个 AI coding agent，提升它解决编程问题的能力。

# 当前评测结果（部分任务）
失败任务: {failed_names}

# 失败详情
{json.dumps(failure_dicts, indent=2, ensure_ascii=False)}

# 你可以修改的文件

## 1. context.py — 行为策略（system prompt）
路径: {CONTEXT_FILE}
```python
{current_context}
```
可改内容:
- SYSTEM_PROMPT_STATIC: agent 的行为指令、工作流程、工具使用规则
- build_context_message(): 注入的动态上下文

## 2. tools.py — 工具实现（{current_tools_size} 字节,太长这里没贴全文）
路径: {TOOLS_FILE}
你可以 Read 这个文件查看现有工具,然后:
- 修改现有工具的实现（比如 Read 的截断逻辑、Bash 的输出处理）
- 增加新工具到 TOOL_SCHEMAS 和 execute_tool 函数
- 但务必保持现有工具的接口签名（worker agent 依赖它们）

# 修改规则
1. 修改后两个文件都必须是合法 Python，且能被正常 import
2. context.py: build_system_prompt() 和 build_context_message() 必须返回字符串
3. tools.py: 现有工具名（Read/Write/Edit/Bash/Glob/Grep 等）必须保留,接口不变
4. 不要写死具体任务的解法 — 你看到的失败任务只是评测集的子集，
   改动会用另一批你看不到的任务评估泛化能力；写通用策略/工具，
   不要在代码里出现任务名、特定数据结构名、特定算法暗示
5. **禁止修改** eval/evolve.py、eval/run_eval.py、config.py — 这些是评测和
   回滚机制本身,改了等于改卷子，越权改动会被自动 git checkout 还原

# 分析思路
- 失败任务的 verify_output 显示了什么问题？
- 是 prompt 引导不够（→ 改 context.py）？
- 还是工具能力不足，比如输出被截断看不到错误（→ 改 tools.py）？
- 还是工具缺失，需要新增（→ 在 tools.py 加新工具）？

提示：你可以用 SelfInspect("overview") 查看系统架构和限制。"""

        state = AgentState()
        config_copy = {**self.config, "permission_mode": "accept-all"}

        made_changes = False
        for event in agent_run(prompt, state, config_copy, META_AGENT_SYSTEM):
            if isinstance(event, TextChunk):
                console.print(event.text, end="")
            elif isinstance(event, ToolStart):
                console.print(f"\n  [dim]🔧 {event.name}[/dim]")
                if event.name in ("Edit", "Write"):
                    made_changes = True

        console.print()
        return made_changes


# ── Main ──────────────────────────────────────────────────────────────────


def _on_event(msg: str) -> None:
    """Format library events with rich console."""
    if msg.startswith("==="):
        console.print(f"\n[bold magenta]{msg}[/bold magenta]")
    elif msg.startswith("PROMOTE"):
        console.print(f"[green bold]{msg}[/green bold]")
    elif msg.startswith("ROLLBACK") or msg.startswith("REVERTED") or msg.startswith("SYNTAX ERROR"):
        console.print(f"[red]{msg}[/red]")
    elif msg.startswith("OBSERVE"):
        console.print(f"[yellow]{msg}[/yellow]")
    else:
        console.print(f"[dim]{msg}[/dim]")


def main():
    parser = argparse.ArgumentParser(description="DGM Self-Evolution (coding agent)")
    parser.add_argument("--generations", type=int, default=3, help="进化代数")
    parser.add_argument("--max-rounds", type=int, default=2, help="每个 eval 任务的最大循环轮数")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--n-per-eval", type=int, default=5,
        help="每次评测重复 N 次取中位数 (默认 5)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="强制 N=1,跳过统计严谨性,只用于 debug",
    )
    args = parser.parse_args()

    n_eval = 1 if args.quick else args.n_per_eval

    config = load_config()
    if args.model:
        config["model"] = args.model
    config["permission_mode"] = "accept-all"

    console.print(Panel(
        f"模型: {config['model']}\n进化代数: {args.generations}\n"
        f"每任务最大轮数: {args.max_rounds}\n每代重复 eval: {n_eval} 次",
        title="🧬 DGM Self-Evolution",
        border_style="magenta",
    ))

    # Build the eval runner — wraps eval/run_eval.py as a subprocess
    eval_cmd = [
        sys.executable, "-u", str(EVAL_SCRIPT),
        "--max-rounds", str(args.max_rounds),
        "--model", config["model"],
    ]
    eval_runner = ShellEvalRunner(
        cmd=eval_cmd,
        result_glob="result_*.json",
        result_dir=Path(__file__).parent,
        cwd=PROJECT_ROOT,
    )

    runner = DGMRunner(
        evolvable_files=EVOLVABLE_FILES,
        eval_runner=eval_runner,
        evolver=CodingAgentEvolver(config),
        holdout_tasks=HOLDOUT_TASKS,
        protected_files=PROTECTED_FILES,
        n_per_eval=n_eval,
        cwd=PROJECT_ROOT,
        on_event=_on_event,
        syntax_check=True,
    )

    result = runner.run(generations=args.generations)

    # ── Display summary table ─────────────────────────────────────────
    console.print(f"\n{'='*60}")
    table = Table(title="进化历史 (中位数 ± 半极差)")
    table.add_column("代", justify="center")
    table.add_column("阶段")
    table.add_column("决策", style="bold")
    table.add_column("train", justify="right")
    table.add_column("hold", justify="right")
    table.add_column("hold LCB", justify="right", style="bold")
    table.add_column("all%", justify="right")

    decision_color = {"promote": "green", "rollback": "red", "observe": "yellow", "init": "dim"}
    for h in result.history:
        m = h.metrics
        train_str = f"{m.train_pct_median:.0f}±{m.train_pct_spread/2:.0f}"
        hold_str = f"{m.hold_pct_median:.0f}±{m.hold_pct_spread/2:.0f}"
        color = decision_color.get(h.decision, "")
        decision = f"[{color}]{h.decision}[/{color}]" if color else h.decision
        table.add_row(
            str(h.generation), h.phase, decision,
            train_str, hold_str,
            f"{m.hold_pct_lcb:.1f}",
            f"{m.all_pct_median:.0f}%",
        )

    console.print(table)
    console.print(f"\n[bold]最终最佳 holdout LCB: {result.best_hold_lcb:.1f}[/bold]")
    console.print(f"[dim]Holdout 任务: {', '.join(sorted(result.holdout_tasks))}[/dim]")
    console.print(f"[dim]每代重复评测: {n_eval} 次,决策指标: hold_pct_lcb = median - spread/2[/dim]")

    # Save JSON record (library provides this)
    evo_file = Path(__file__).parent / f"evolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    runner.save_history(evo_file, result)
    console.print(f"\n[dim]进化记录: {evo_file}[/dim]")


if __name__ == "__main__":
    main()
