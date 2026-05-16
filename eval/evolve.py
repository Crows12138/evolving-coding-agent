"""DGM Self-Evolution — Agent 通过改自己的 prompt 和工具实现来提升 eval 分数

可进化层 (EVOLVABLE_FILES):
- context.py  ← system prompt / 动态上下文
- tools.py    ← 工具实现 (能改现有工具,也能加新工具)

保护层 (PROTECTED_FILES,改了会被 git checkout 还原):
- eval/evolve.py、eval/run_eval.py  ← 评测+回滚机制,不能让 LLM 改
- config.py  ← 数值参数由 load_config() 按模型自动设

流程:
1. 跑 N 次 eval → 聚合成 (median, spread, LCB) 分布
2. Meta-agent 看代表性 results,改 context.py / tools.py
3. AST 检查 + 越权检查
4. 重跑 N 次 eval → 比较 LCB
5. LCB 涨过 best → promote;LCB 跌幅超过噪声 → rollback;其他 → 保留观察
6. 循环

决策指标 = hold_pct_lcb = median - spread/2
(同时奖励高通过率和低方差,惩罚飘忽的 prompt)
"""

import sys
import os
import json
import shutil
import subprocess
import statistics
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
CONTEXT_FILE = PROJECT_ROOT / "context.py"
TOOLS_FILE   = PROJECT_ROOT / "tools.py"
EVOLVABLE_FILES = [CONTEXT_FILE, TOOLS_FILE]
EVAL_SCRIPT = Path(__file__).parent / "run_eval.py"

# Meta 层 — 绝对不能被 meta-agent 改 (改了等于改卷子/改回滚机制)
# 路径用 PROJECT_ROOT 相对的 posix 形式,跟 git diff 输出对齐
PROTECTED_FILES = {
    "eval/evolve.py",
    "eval/run_eval.py",
    "eval/explore.py",
    "config.py",        # 数值参数由 load_config() 按模型自动设
}


# Meta-agent 的 system prompt — 不在 EVOLVABLE_FILES,DGM 改不到
# 作用：让分析/修复 agent 用稳定 prompt，不被进化中的 worker prompt 污染
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


# Holdout: agent 看不到这些任务的失败详情,用它们的通过率做无偏决策
# 改任务时同步更新,保证 holdout 比例 ~30% (单任务影响 = 1/N,N 越大噪声越低)
# 当前 51 任务,holdout 16 (31%),覆盖多种算法/范式
HOLDOUT_TASKS = {
    # 原 13 任务里挑 4 个 (跨范式)
    "task_03_state_machine",
    "task_07_config_parser",
    "task_10_matrix",
    "task_13_file_index",
    # QuixBugs 38 任务里挑 12 个 (跨算法类别)
    "qb_mergesort",                    # 排序
    "qb_depth_first_search",           # 图
    "qb_shortest_path_length",         # 图
    "qb_topological_ordering",         # 图
    "qb_find_in_sorted",               # 搜索
    "qb_levenshtein",                  # DP
    "qb_max_sublist_sum",              # DP
    "qb_knapsack",                     # 数学/DP
    "qb_sieve",                        # 数学
    "qb_to_base",                      # 数学
    "qb_rpn_eval",                     # 字符串/栈
    "qb_is_valid_parenthesization",    # 字符串
}


def _subset_metrics(results: list[dict], names: set[str]) -> tuple[float, float]:
    """计算某个任务子集的 (通过率%, 效率分)"""
    rs = [r for r in results if r.get("name") in names]
    if not rs:
        return 0.0, 0.0
    passed = sum(1 for r in rs if r.get("passed"))
    pct = passed / len(rs) * 100
    avg = sum(r.get("duration", 1) for r in rs) / len(rs)
    eff = pct / avg * 60 if avg > 0 else 0.0
    return pct, eff


def split_metrics(results: list[dict]) -> dict:
    """切分 train / holdout,返回完整指标"""
    all_names = {r.get("name") for r in results}
    train_names = all_names - HOLDOUT_TASKS
    train_pct, train_eff = _subset_metrics(results, train_names)
    hold_pct, hold_eff = _subset_metrics(results, HOLDOUT_TASKS)
    all_pct, all_eff = _subset_metrics(results, all_names)
    return {
        "train_pct": train_pct, "train_eff": train_eff,
        "hold_pct": hold_pct,   "hold_eff": hold_eff,
        "all_pct":  all_pct,    "all_eff":  all_eff,
    }


def _verify_syntax(filepath: Path) -> tuple[bool, str]:
    """验证单个 Python 文件语法是否正确"""
    result = subprocess.run(
        [sys.executable, "-c", f"import ast; ast.parse(open(r'{filepath}').read()); print('OK')"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip()


def verify_all_syntax() -> tuple[bool, str]:
    """验证所有可进化文件的语法"""
    for f in EVOLVABLE_FILES:
        ok, err = _verify_syntax(f)
        if not ok:
            return False, f"{f.name}: {err}"
    return True, ""


# 向后兼容
verify_context_syntax = verify_all_syntax


def _enforce_protected() -> list[str]:
    """检查 git working tree,把 PROTECTED_FILES 的任何改动强制 checkout 还原。

    返回被还原的文件列表(用于上报)。EVOLVABLE_FILES 不在 PROTECTED,允许被改。
    其他文件 (loop.py / providers.py 等) 也不在 PROTECTED — 当前默认信任,
    将来要扩大可改范围时只需把它们加进 EVOLVABLE_FILES 即可。
    """
    diff = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    ).stdout.strip().splitlines()
    illegal = [f for f in diff if f in PROTECTED_FILES]
    if illegal:
        subprocess.run(
            ["git", "checkout", "--"] + illegal,
            capture_output=True, cwd=PROJECT_ROOT,
        )
    return illegal


def fix_broken_files(error_msg: str, config: dict) -> bool:
    """让 Meta-agent 修复被写坏的文件"""
    from agent import AgentState, run as agent_run, TextChunk, ToolStart, ToolEnd, TurnDone

    console.print(f"[red]语法错误，让 Meta-agent 修复...[/red]")
    console.print(f"[dim]{error_msg[:300]}[/dim]")

    prompt = f"""进化过程中产生了语法错误，请修复。

错误信息:
```
{error_msg}
```

请用 Read 工具读取出错的文件，找到语法错误并用 Edit 修复。
注意保持文件的功能完整性。"""

    state = AgentState()
    system = META_AGENT_SYSTEM
    config_copy = {**config, "permission_mode": "accept-all"}

    for event in agent_run(prompt, state, config_copy, system):
        if isinstance(event, TextChunk):
            console.print(event.text, end="")
        elif isinstance(event, ToolStart):
            console.print(f"\n  [dim]🔧 {event.name}[/dim]")

    console.print()

    # 越权检查 — 修语法时也可能跑去改 PROTECTED 文件
    illegal = _enforce_protected()
    if illegal:
        console.print(f"[red]Meta-agent 修复时越权改了 {illegal},已 checkout 还原[/red]")

    ok, err = verify_all_syntax()
    if ok:
        console.print("[green]语法修复成功[/green]")
    else:
        console.print(f"[red]修复失败，将回滚: {err[:100]}[/red]")
    return ok


def run_eval(config: dict, max_rounds: int) -> tuple[dict, list[dict]]:
    """运行 eval 并返回 (split 指标 dict, 结果列表)

    指标 dict 含 train/hold/all 三套 (pct, eff)，供调用方挑选决策依据
    """
    # 先验证语法 — 坏文件直接返回零分，让外层走修复路径
    ok, err = verify_context_syntax()
    if not ok:
        zeros = {k: 0.0 for k in ("train_pct","train_eff","hold_pct","hold_eff","all_pct","all_eff")}
        return zeros, [{"error": err}]

    # 用子进程跑 eval，避免模块缓存问题
    cmd = [
        sys.executable, "-u", str(EVAL_SCRIPT),
        "--max-rounds", str(max_rounds),
        "--model", config["model"],
    ]
    eval_start = time.time()
    subprocess.run(cmd, timeout=None, cwd=str(Path(__file__).parent.parent))

    # 必须有比这次启动更新的 result 文件 — 否则视为子进程崩了,按最差分处理
    # (防"读到旧 result"漏洞:meta-agent 改坏代码导致 eval import 失败时,
    #  不会写新 result,会让 evolve 误以为分数没变、不触发回滚)
    eval_dir = Path(__file__).parent
    fresh = [
        f for f in eval_dir.glob("result_*.json")
        if f.stat().st_mtime >= eval_start
    ]
    if not fresh:
        console.print("[red]eval 没产生新 result（子进程可能崩了），按全失败处理[/red]")
        zeros = {k: 0.0 for k in ("train_pct","train_eff","hold_pct","hold_eff","all_pct","all_eff")}
        return zeros, []
    fresh.sort(key=lambda f: f.stat().st_mtime)

    latest = json.loads(fresh[-1].read_text())
    results = latest.get("results", [])
    return split_metrics(results), results


def run_eval_n(config: dict, max_rounds: int, n: int) -> tuple[dict, list[dict], list[list[dict]]]:
    """跑 N 次 eval，把每次结果当作随机变量样本，聚合返回:

    - agg: 每个指标的 median / spread / lcb (lcb = median - spread/2)
    - representative_results: 用于 agent 分析的代表性 results (取 hold_pct 最接近中位数那次)
    - all_runs: N 次的 results 列表，便于事后复盘

    LCB (Lower Confidence Bound) 作为决策指标，同时奖励"高分"和"低方差"：
      prompt A: median 90%, spread 30%  → LCB 75%   (飘忽)
      prompt B: median 80%, spread 5%   → LCB 77.5% (稳健,胜出)
    """
    runs = []
    for i in range(n):
        if n > 1:
            console.print(f"  [dim]eval run {i+1}/{n}...[/dim]")
        m, results = run_eval(config, max_rounds)
        runs.append((m, results))

    if not runs:
        return {}, [], []

    keys = list(runs[0][0].keys())
    agg: dict = {}
    for k in keys:
        vals = [r[0][k] for r in runs]
        med = statistics.median(vals)
        spread = max(vals) - min(vals) if len(vals) > 1 else 0.0
        agg[f"{k}_median"] = med
        agg[f"{k}_spread"] = spread
        agg[f"{k}_lcb"] = med - spread / 2

    # 找 hold_pct 最接近中位数的那次作为代表性 results
    target = agg["hold_pct_median"]
    representative_idx = min(
        range(len(runs)),
        key=lambda i: abs(runs[i][0]["hold_pct"] - target),
    )
    representative_results = runs[representative_idx][1]
    all_runs = [r[1] for r in runs]
    return agg, representative_results, all_runs


def analyze_and_evolve(
    score: float,
    results: list[dict],
    generation: int,
    config: dict,
) -> bool:
    """让 meta-agent 分析失败原因并修改 worker 的 prompt / 工具，返回是否做了修改"""
    from agent import AgentState, run as agent_run, TextChunk, ToolStart, ToolEnd, TurnDone

    # 只给 agent 看 train 集的失败 — holdout 用于无偏评估，不暴露
    visible_failed = [
        r for r in results
        if not r.get("passed") and r.get("name") not in HOLDOUT_TASKS
    ]
    if not visible_failed:
        # train 全过但 holdout 可能还有失败 — 没东西给 agent 看，跳过
        console.print("[green]可见任务全部通过，无失败详情可供分析[/green]")
        return False

    failed_names = ", ".join(r["name"] for r in visible_failed)

    # 读取当前可进化文件内容
    current_context = CONTEXT_FILE.read_text(encoding="utf-8")
    current_tools_size = TOOLS_FILE.stat().st_size

    prompt = f"""你需要改进一个 AI coding agent，提升它解决编程问题的能力。

# 当前评测结果（部分任务）
通过率: {score:.0f}%，失败任务: {failed_names}

# 失败详情
{json.dumps(visible_failed, indent=2, ensure_ascii=False)}

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

注意：max_tokens / max_tool_output 等运行参数由外部按模型自动设置，
你不需要也无法修改它们。

提示：你可以用 SelfInspect("overview") 查看系统架构和限制。"""

    state = AgentState()
    system = META_AGENT_SYSTEM
    config_copy = {**config, "permission_mode": "accept-all"}

    made_changes = False
    for event in agent_run(prompt, state, config_copy, system):
        if isinstance(event, TextChunk):
            console.print(event.text, end="")
        elif isinstance(event, ToolStart):
            console.print(f"\n  [dim]🔧 {event.name}[/dim]")
            if event.name in ("Edit", "Write"):
                made_changes = True
        elif isinstance(event, ToolEnd):
            pass

    console.print()
    return made_changes


def main():
    parser = argparse.ArgumentParser(description="DGM Self-Evolution")
    parser.add_argument("--generations", type=int, default=3, help="进化代数")
    parser.add_argument("--max-rounds", type=int, default=2, help="每个 eval 任务的最大循环轮数")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--n-per-eval", type=int, default=5,
        help="每次评测重复 N 次取中位数,用于估计 prompt 的分布而非点估计 (默认 5)",
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

    backups = {f: f.read_text(encoding="utf-8") for f in EVOLVABLE_FILES}
    history = []

    # 决策指标:hold_pct_lcb (median - spread/2,同时奖励高分和低方差)
    best_hold_lcb = -1.0
    best_state = dict(backups)

    def _show(label: str, m: dict):
        console.print(
            f"[bold]{label}[/bold] | "
            f"train: {m['train_pct_median']:.0f}% (±{m['train_pct_spread']/2:.0f}, "
            f"lcb {m['train_pct_lcb']:.0f}%)  "
            f"hold: {m['hold_pct_median']:.0f}% (±{m['hold_pct_spread']/2:.0f}, "
            f"[bold]lcb {m['hold_pct_lcb']:.0f}%[/bold])  "
            f"合并: {m['all_pct_median']:.0f}%"
        )

    for gen in range(1, args.generations + 1):
        console.print(f"\n[bold magenta]{'='*60}[/bold magenta]")
        console.print(f"[bold magenta]第 {gen}/{args.generations} 代[/bold magenta]")
        console.print(f"[bold magenta]{'='*60}[/bold magenta]")

        # 1. 跑 N 次 eval,聚合成分布
        console.print(f"\n[cyan]运行评测 ({n_eval} 次)...[/cyan]")
        m, results, all_runs = run_eval_n(config, args.max_rounds, n_eval)
        _show("当前", m)

        history.append({"generation": gen, "phase": "eval", "n": n_eval, **m})

        if m["hold_pct_lcb"] > best_hold_lcb:
            best_hold_lcb = m["hold_pct_lcb"]
            best_state = {f: f.read_text(encoding="utf-8") for f in EVOLVABLE_FILES}

        # 全通过且方差为 0 才算彻底完成
        if (m["train_pct_median"] == 100.0 and m["hold_pct_median"] == 100.0
                and m["train_pct_spread"] == 0.0 and m["hold_pct_spread"] == 0.0):
            console.print("[green bold]train+holdout 全部稳定通过！进化完成。[/green bold]")
            break

        # 2. Meta-agent 分析失败 (用中位数对应的代表性 results)
        console.print(f"\n[cyan]Meta-agent 分析失败原因并进化...[/cyan]")
        pre_change = {f: f.read_text(encoding="utf-8") for f in EVOLVABLE_FILES}
        changed = analyze_and_evolve(m["train_pct_median"], results, gen, config)

        # 越权检查 — meta-agent 改了 PROTECTED_FILES 立即 checkout 还原
        illegal = _enforce_protected()
        if illegal:
            console.print(f"[red]Meta-agent 越权改了 {illegal},强制 checkout 还原[/red]")

        if not changed:
            console.print("[yellow]Meta-agent 没有做出修改，跳过验证[/yellow]")

        # 3. 验证语法
        if changed:
            ok, err = verify_all_syntax()
            if not ok:
                fixed = fix_broken_files(err, config)
                if not fixed:
                    console.print("[red]修复失败，回滚到修改前[/red]")
                    for f, content in pre_change.items():
                        f.write_text(content, encoding="utf-8")
                    continue

        if not changed:
            continue

        # 4. 重跑 N 次 eval 验证 — 决策用 LCB
        console.print(f"\n[cyan]验证进化后的效果 ({n_eval} 次)...[/cyan]")
        m_new, _, _ = run_eval_n(config, args.max_rounds, n_eval)
        _show("进化后", m_new)
        console.print(
            f"[dim]Δ hold lcb: {m['hold_pct_lcb']:.1f} → {m_new['hold_pct_lcb']:.1f}  "
            f"(median {m['hold_pct_median']:.0f}%→{m_new['hold_pct_median']:.0f}%, "
            f"spread {m['hold_pct_spread']:.0f}→{m_new['hold_pct_spread']:.0f})[/dim]"
        )

        history.append({"generation": gen, "phase": "evolved", "n": n_eval, **m_new})

        # 决策 (基于 LCB):
        # - LCB 提升 → 进化成功,更新 best
        # - LCB 显著下降 (大于 spread 的一半) → 回滚到历史最佳
        # - 否则 → 在噪声里,保留观察
        lcb_old = m["hold_pct_lcb"]
        lcb_new = m_new["hold_pct_lcb"]
        # 用两次极差的最大值作为"可解释的波动幅度"
        noise_floor = max(m["hold_pct_spread"], m_new["hold_pct_spread"]) / 2

        if lcb_new > best_hold_lcb:
            console.print(
                f"[green bold]进化成功！hold LCB {best_hold_lcb:.1f} → {lcb_new:.1f}[/green bold]"
            )
            best_hold_lcb = lcb_new
            best_state = {f: f.read_text(encoding="utf-8") for f in EVOLVABLE_FILES}
        elif lcb_new < lcb_old - noise_floor:
            console.print(
                f"[red]hold LCB 显著下降 {lcb_old:.1f} → {lcb_new:.1f} "
                f"(超过噪声 ±{noise_floor:.0f})，回滚到历史最佳 (LCB {best_hold_lcb:.1f})[/red]"
            )
            for f, content in best_state.items():
                f.write_text(content, encoding="utf-8")
        else:
            console.print(
                f"[yellow]LCB 变化 {lcb_old:.1f} → {lcb_new:.1f} 在噪声 ±{noise_floor:.0f} 内,保留观察[/yellow]"
            )

    # 汇总
    console.print(f"\n{'='*60}")
    table = Table(title="进化历史 (中位数 ± 半极差)")
    table.add_column("代", justify="center")
    table.add_column("阶段")
    table.add_column("train", justify="right")
    table.add_column("hold", justify="right")
    table.add_column("hold LCB", justify="right", style="bold")
    table.add_column("all%", justify="right")

    for h in history:
        train_str = f"{h.get('train_pct_median', 0):.0f}±{h.get('train_pct_spread', 0)/2:.0f}"
        hold_str  = f"{h.get('hold_pct_median', 0):.0f}±{h.get('hold_pct_spread', 0)/2:.0f}"
        table.add_row(
            str(h["generation"]), h["phase"],
            train_str,
            hold_str,
            f"{h.get('hold_pct_lcb', 0):.1f}",
            f"{h.get('all_pct_median', 0):.0f}%",
        )

    console.print(table)
    console.print(f"\n[bold]最终最佳 holdout LCB: {best_hold_lcb:.1f}[/bold]")
    console.print(f"[dim]Holdout 任务: {', '.join(sorted(HOLDOUT_TASKS))}[/dim]")
    console.print(f"[dim]每代重复评测: {n_eval} 次,决策指标: hold_pct_lcb = median - spread/2[/dim]")

    # 显示所有文件变化
    import difflib
    any_changed = False
    for f in EVOLVABLE_FILES:
        current = f.read_text(encoding="utf-8")
        original = backups[f]
        if current != original:
            any_changed = True
            console.print(f"\n[bold cyan]{f.name} 变化:[/bold cyan]")
            diff = difflib.unified_diff(
                original.splitlines(), current.splitlines(),
                fromfile=f"原始 {f.name}", tofile=f"进化后 {f.name}", lineterm=""
            )
            for line in diff:
                if line.startswith("+") and not line.startswith("+++"):
                    console.print(f"[green]{line}[/green]")
                elif line.startswith("-") and not line.startswith("---"):
                    console.print(f"[red]{line}[/red]")
                else:
                    console.print(f"[dim]{line}[/dim]")
    if not any_changed:
        console.print("[dim]文件未发生变化[/dim]")

    # 保存进化记录
    evo_file = Path(__file__).parent / f"evolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    evo_file.write_text(json.dumps({
        "model": config["model"],
        "generations": args.generations,
        "n_per_eval": n_eval,
        "holdout_tasks": sorted(HOLDOUT_TASKS),
        "best_hold_lcb": best_hold_lcb,
        "history": history,
    }, ensure_ascii=False, indent=2))
    console.print(f"\n[dim]进化记录: {evo_file}[/dim]")


if __name__ == "__main__":
    main()
