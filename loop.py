"""Ralph Loop v2 — 持续上下文的自我改进循环

改进：不再每轮清空上下文。模型能记住之前尝试了什么，避免重复犯错。
上下文满了由 compact 机制自动压缩（保留摘要 + 最近对话）。
Git commit 作为检查点，支持断点恢复。

用法:
    from loop import improvement_loop
    result = improvement_loop(
        task="修复 tests/test_math.py 中所有失败的测试",
        verify_cmd="python -m pytest tests/test_math.py",
        max_rounds=5,
    )
"""

from __future__ import annotations

import subprocess
import os
import json
from datetime import datetime
from pathlib import Path

from agent import AgentState, run, TextChunk, ThinkingChunk, ToolStart, ToolEnd, TurnDone
from context import build_system_prompt, build_context_message
from rich.console import Console
from rich.panel import Panel
import providers

console = Console()


# ── Session logging ──────────────────────────────────────────────────────

class LoopSession:
    """持久化 loop 过程到文件"""

    def __init__(self, task: str, verify_cmd: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = Path.home() / ".nano_claude" / "loops" / ts
        self.dir.mkdir(parents=True, exist_ok=True)
        self.task = task
        self.verify_cmd = verify_cmd
        self.rounds: list[dict] = []

        # 写 meta
        meta = {"task": task, "verify_cmd": verify_cmd, "started": ts}
        (self.dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def log_round(self, round_num: int, events: list[str], verify_passed: bool, verify_output: str):
        """保存一轮的记录"""
        data = {
            "round": round_num,
            "events": events,
            "verify_passed": verify_passed,
            "verify_output": verify_output[:2000],
        }
        self.rounds.append(data)
        (self.dir / f"round_{round_num}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def finalize(self, passed: bool, total_rounds: int):
        """写最终总结"""
        summary = {
            "passed": passed,
            "total_rounds": total_rounds,
            "finished": datetime.now().strftime("%Y%m%d_%H%M%S"),
        }
        (self.dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        return str(self.dir)


def _run_verify(cmd: str, timeout: int = 60) -> tuple[bool, str]:
    """运行验证命令，返回 (passed, output)"""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=os.getcwd(),
        )
        output = r.stdout + ("\n" + r.stderr if r.stderr else "")
        output = output.strip()
        if len(output) > 3000:
            output = output[:1500] + "\n...(truncated)...\n" + output[-1000:]
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"验证命令超时 ({timeout}s)"
    except Exception as e:
        return False, f"验证命令出错: {e}"


def _git_snapshot(msg: str):
    """保存当前状态到 git"""
    try:
        subprocess.run(["git", "add", "-A"], capture_output=True, timeout=5)
        subprocess.run(
            ["git", "commit", "-m", f"[loop] {msg}", "--allow-empty"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _run_agent_turn(prompt: str, state: AgentState, config: dict, system_prompt: str) -> list[str]:
    """执行一轮 agent 对话并输出，返回事件日志"""
    text_buf = ""
    event_log = []
    for event in run(prompt, state, config, system_prompt):
        if isinstance(event, TextChunk):
            text_buf += event.text
        elif isinstance(event, ToolStart):
            if text_buf.strip():
                console.print(text_buf.strip())
                event_log.append(f"[text] {text_buf.strip()[:300]}")
                text_buf = ""
            args_preview = str(list(event.inputs.values())[:1])
            if len(args_preview) > 80:
                args_preview = args_preview[:77] + "..."
            console.print(f"  [dim]🔧 {event.name}({args_preview})[/dim]")
            event_log.append(f"[tool] {event.name}({args_preview})")
        elif isinstance(event, ToolEnd):
            if not event.permitted:
                console.print(f"  [red]⛔ {event.name} 被拒绝[/red]")
                event_log.append(f"[denied] {event.name}")
    if text_buf.strip():
        console.print(text_buf.strip())
        event_log.append(f"[text] {text_buf.strip()[:300]}")
    return event_log


def _save_experience(task: str, history: list[dict], passed: bool, config: dict):
    """Loop 结束后用 LLM 提炼经验，存入 memory"""
    if not history:
        return

    # 构建经验总结 prompt
    rounds_summary = ""
    for h in history:
        status = "PASS" if h["passed"] else "FAIL"
        output_preview = h["verify_output"][:200]
        rounds_summary += f"Round {h['round']} [{status}]: {output_preview}\n"

    result_text = "最终通过" if passed else f"未通过（尝试了 {len(history)} 轮）"

    summary_prompt = (
        f"你刚完成了一个修复循环。请用一句话总结这次经验教训，"
        f"让未来遇到类似问题时能更快解决。\n\n"
        f"任务: {task}\n"
        f"结果: {result_text}\n"
        f"过程:\n{rounds_summary}\n"
        f"请用以下格式回复（不要其他内容）:\n"
        f"SCOPE: project 或 user（project=仅当前项目有用, user=通用经验）\n"
        f"EXPERIENCE: 一句话经验总结"
    )

    # 调 LLM 提炼
    experience = ""
    try:
        for event in providers.stream(
            model=config["model"],
            system="You are a concise summarizer. Reply in the same language as the task.",
            messages=[{"role": "user", "content": summary_prompt}],
            tool_schemas=[],
            config={**config, "max_tokens": 200},
        ):
            if isinstance(event, providers.TextChunk):
                experience += event.text
    except Exception:
        return

    experience = experience.strip()
    if not experience or len(experience) < 5:
        return

    # 解析 scope 和经验内容
    scope = "project"
    exp_text = experience
    for line in experience.splitlines():
        line_s = line.strip()
        if line_s.upper().startswith("SCOPE:"):
            val = line_s.split(":", 1)[1].strip().lower()
            if val in ("user", "project"):
                scope = val
        elif line_s.upper().startswith("EXPERIENCE:"):
            exp_text = line_s.split(":", 1)[1].strip()

    if not exp_text or len(exp_text) < 5:
        return

    # 存入 memory
    try:
        from tools import execute_tool
        mem_name = f"loop-exp-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        execute_tool("MemorySave", {
            "name": mem_name,
            "type": "feedback",
            "description": f"Loop experience: {task[:60]}",
            "content": f"{exp_text}\n\n**Task:** {task}\n**Result:** {result_text}, {len(history)} rounds",
            "scope": scope,
        }, config=config)
        console.print(f"  [dim]💡 经验已保存 ({scope}): {exp_text[:100]}[/dim]")
    except Exception as e:
        console.print(f"  [dim]经验保存失败: {e}[/dim]")


def improvement_loop(
    task: str,
    verify_cmd: str,
    config: dict,
    max_rounds: int = 0,  # 0 = 无限
    auto_commit: bool = False,
) -> dict:
    """执行持续上下文的改进循环

    Args:
        task: 要完成的任务描述
        verify_cmd: 验证命令（返回 0 表示通过）
        config: nano-claude-code 配置
        max_rounds: 最大循环轮数
        auto_commit: 是否每轮自动 git commit

    Returns:
        {"passed": bool, "rounds": int, "history": list}
    """
    system_prompt = build_system_prompt()
    history = []

    rounds_display = f"{max_rounds}" if max_rounds else "无限 (Ctrl+C 中断)"
    console.print(Panel(
        f"任务: {task}\n验证: {verify_cmd}\n最大轮数: {rounds_display}",
        title="🔄 Loop 开始",
        border_style="cyan",
    ))

    # 先验证当前状态
    passed, verify_output = _run_verify(verify_cmd)
    if passed:
        console.print("[green]✅ 验证已通过，无需改进[/green]")
        return {"passed": True, "rounds": 0, "history": []}

    # Loop 模式默认跳过权限确认
    config = {**config, "permission_mode": "accept-all"}

    # 一个 state 贯穿所有轮次，compact 自动管理上下文
    state = AgentState()
    context = build_context_message()
    session = LoopSession(task, verify_cmd)

    round_num = 0
    while True:
        round_num += 1
        if max_rounds and round_num > max_rounds:
            break
        label = f"{round_num}/{max_rounds}" if max_rounds else f"{round_num}"
        console.print(f"\n[bold cyan]━━━ 第 {label} 轮 ━━━[/bold cyan]")

        if round_num == 1:
            # 首轮：完整任务描述
            prompt = f"""{context}

# 任务
{task}

# 当前验证结果（失败）
命令: `{verify_cmd}`
输出:
```
{verify_output}
```

请分析失败原因并修复相关文件。"""
        else:
            # 后续轮：只给新的验证结果，模型已有之前的上下文
            prompt = f"""验证仍然失败（第 {round_num} 轮）。

命令: `{verify_cmd}`
输出:
```
{verify_output}
```

分析这次的错误跟上一轮有什么不同，用不同的方法修复。"""

        # 运行 agent（上下文持续累积，compact 自动处理）
        event_log = _run_agent_turn(prompt, state, config, system_prompt)

        # 验证
        passed, verify_output = _run_verify(verify_cmd)
        # 持久化本轮日志
        session.log_round(round_num, event_log, passed, verify_output)
        history.append({
            "round": round_num,
            "passed": passed,
            "verify_output": verify_output[:500],
        })

        if passed:
            if auto_commit:
                _git_snapshot(f"loop: {task[:50]}")
            console.print(Panel(
                f"✅ 第 {round_num} 轮修复后验证通过！",
                border_style="green",
            ))
            log_path = session.finalize(True, round_num)
            console.print(f"  [dim]日志: {log_path}[/dim]")
            _save_experience(task, history, True, config)
            return {"passed": True, "rounds": round_num, "history": history}
        else:
            console.print(f"  [yellow]❌ 验证未通过，继续...[/yellow]")

    log_path = session.finalize(False, round_num)
    console.print(Panel(
        f"达到最大轮数 ({max_rounds})，验证仍未通过\n日志: {log_path}",
        border_style="red",
    ))
    _save_experience(task, history, False, config)
    return {"passed": False, "rounds": round_num, "history": history}
