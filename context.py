"""System context: CLAUDE.md, git info, cwd injection."""
import os
import subprocess
from pathlib import Path
from datetime import datetime

from memory import get_memory_context

# Static system prompt — never changes between requests (enables KV cache reuse)
SYSTEM_PROMPT_STATIC = """\
You are a coding assistant in the terminal. Help with code, files, and shell tasks.

# Rules
- Be concise. Lead with action, not explanation.
- Read files before editing. Use line numbers.
- Use absolute paths. Prefer editing over creating new files.
- If unclear, ask before proceeding."""


def get_git_info() -> str:
    """Return git branch/status summary if in a git repo."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"],
            stderr=subprocess.DEVNULL, text=True).strip()
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            stderr=subprocess.DEVNULL, text=True).strip()
        parts = [f"- Git branch: {branch}"]
        if status:
            lines = status.split('\n')[:10]
            parts.append("- Git status:\n" + "\n".join(f"  {l}" for l in lines))
        if log:
            parts.append("- Recent commits:\n" + "\n".join(f"  {l}" for l in log.split('\n')))
        return "\n".join(parts) + "\n"
    except Exception:
        return ""


def get_claude_md() -> str:
    """Load CLAUDE.md from cwd or parents, and ~/.claude/CLAUDE.md."""
    content_parts = []

    # Global CLAUDE.md
    global_md = Path.home() / ".claude" / "CLAUDE.md"
    if global_md.exists():
        try:
            content_parts.append(f"[Global CLAUDE.md]\n{global_md.read_text()}")
        except Exception:
            pass

    # Project CLAUDE.md (walk up from cwd)
    p = Path.cwd()
    for _ in range(10):
        candidate = p / "CLAUDE.md"
        if candidate.exists():
            try:
                content_parts.append(f"[Project CLAUDE.md: {candidate}]\n{candidate.read_text()}")
            except Exception:
                pass
            break
        parent = p.parent
        if parent == p:
            break
        p = parent

    if not content_parts:
        return ""
    return "\n# Memory / CLAUDE.md\n" + "\n\n".join(content_parts) + "\n"


def build_system_prompt() -> str:
    """Return the static system prompt (cacheable by KV cache)."""
    return SYSTEM_PROMPT_STATIC


def build_context_message() -> str:
    """Return dynamic context as a string to inject into the first user message."""
    import platform
    parts = [f"[Environment: {platform.system()}, CWD: {Path.cwd()}, Date: {datetime.now().strftime('%Y-%m-%d')}]"]
    git = get_git_info()
    if git:
        parts.append(f"[Git: {git.strip()}]")
    claude_md = get_claude_md()
    if claude_md:
        parts.append(claude_md.strip())
    mem = get_memory_context()
    if mem:
        parts.append(f"[Memories]\n{mem}")
    return "\n".join(parts)
