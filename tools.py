"""Tool definitions and implementations for nano claude."""
import json
import os
import sys
import re
import glob as _glob
import difflib
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from tool_registry import ToolDef, register_tool
from tool_registry import execute_tool as _registry_execute

# ── AskUserQuestion state ──────────────────────────────────────────────────────
# The main REPL loop drains _pending_questions and fills _question_answers.
_pending_questions: list[dict] = []   # [{id, question, options, allow_freetext, event, result_holder}]
_ask_lock = threading.Lock()

# ── Tool JSON schemas (sent to Claude API) ─────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "Read",
        "description": (
            "Read a file's contents. Returns content with line numbers "
            "(format: 'N\\tline'). Use limit/offset to read large files in chunks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute file path"},
                "limit":     {"type": "integer", "description": "Max lines to read"},
                "offset":    {"type": "integer", "description": "Start line (0-indexed)"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "Write",
        "description": "Write content to a file, creating parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content":   {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "Edit",
        "description": (
            "Replace exact text in a file. old_string must match exactly (including whitespace). "
            "If old_string appears multiple times, use replace_all=true or add more context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string"},
                "old_string":  {"type": "string", "description": "Exact text to replace"},
                "new_string":  {"type": "string", "description": "Replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "Bash",
        "description": "Execute a shell command. Returns stdout+stderr. Stateless (no cd persistence).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "description": "Seconds before timeout (default 120, hard max 120)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "Glob",
        "description": "Find files matching a glob pattern. Returns sorted list of matching paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern e.g. **/*.py"},
                "path":    {"type": "string", "description": "Base directory (default: cwd)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "Grep",
        "description": "Search file contents with regex using ripgrep (falls back to grep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern":      {"type": "string", "description": "Regex pattern"},
                "path":         {"type": "string", "description": "File or directory to search"},
                "glob":         {"type": "string", "description": "File filter e.g. *.py"},
                "output_mode":  {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "content=matching lines, files_with_matches=file paths, count=match counts",
                },
                "case_insensitive": {"type": "boolean"},
                "context":      {"type": "integer", "description": "Lines of context around matches"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "WebFetch",
        "description": "Fetch a URL and return its text content (HTML stripped).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":    {"type": "string"},
                "prompt": {"type": "string", "description": "Hint for what to extract"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "WebSearch",
        "description": "Search the web via DuckDuckGo and return top results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]

# ── Safe bash commands (never ask permission) ───────────────────────────────

_SAFE_PREFIXES = (
    "ls", "cat", "head", "tail", "wc", "pwd", "echo", "printf", "date",
    "which", "type", "env", "printenv", "uname", "whoami", "id",
    "git log", "git status", "git diff", "git show", "git branch",
    "git remote", "git stash list", "git tag",
    "find ", "grep ", "rg ", "ag ", "fd ",
    "python ", "python3 ", "node ", "ruby ", "perl ",
    "pip show", "pip list", "npm list", "cargo metadata",
    "df ", "du ", "free ", "top -bn", "ps ",
    "curl -I", "curl --head",
)

def _is_safe_bash(cmd: str) -> bool:
    c = cmd.strip()
    return any(c.startswith(p) for p in _SAFE_PREFIXES)


# ── Diff helpers ──────────────────────────────────────────────────────────

def generate_unified_diff(old, new, filename, context_lines=3):
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines,
        fromfile=f"a/{filename}", tofile=f"b/{filename}", n=context_lines)
    return "".join(diff)

def maybe_truncate_diff(diff_text, max_lines=80):
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text
    shown = lines[:max_lines]
    remaining = len(lines) - max_lines
    return "\n".join(shown) + f"\n\n[... {remaining} more lines ...]"


# ── Tool implementations ───────────────────────────────────────────────────

def _read(file_path: str, limit: int = None, offset: int = None) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"Error: file not found: {file_path}"
    if p.is_dir():
        return f"Error: {file_path} is a directory"
    try:
        lines = p.read_text(errors="replace").splitlines(keepends=True)
        start = offset or 0
        chunk = lines[start:start + limit] if limit else lines[start:]
        if not chunk:
            return "(empty file)"
        return "".join(f"{start + i + 1}\t{l}" for i, l in enumerate(chunk))
    except Exception as e:
        return f"Error: {e}"


def _write(file_path: str, content: str) -> str:
    p = Path(file_path)
    try:
        is_new = not p.exists()
        old_content = "" if is_new else p.read_text(errors="replace")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        if is_new:
            lc = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return f"Created {file_path} ({lc} lines)"
        filename = p.name
        diff = generate_unified_diff(old_content, content, filename)
        if not diff:
            return f"No changes in {file_path}"
        truncated = maybe_truncate_diff(diff)
        return f"File updated — {file_path}:\n\n{truncated}"
    except Exception as e:
        return f"Error: {e}"


def _edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"Error: file not found: {file_path}"
    try:
        content = p.read_text()
        count = content.count(old_string)
        if count == 0:
            return "Error: old_string not found in file"
        if count > 1 and not replace_all:
            return (f"Error: old_string appears {count} times. "
                    "Provide more context to make it unique, or use replace_all=true.")
        old_content = content
        new_content = content.replace(old_string, new_string) if replace_all else \
                      content.replace(old_string, new_string, 1)
        p.write_text(new_content)
        filename = p.name
        diff = generate_unified_diff(old_content, new_content, filename)
        return f"Changes applied to {filename}:\n\n{diff}"
    except Exception as e:
        return f"Error: {e}"


_BASH_MAX_TIMEOUT = 120  # 硬上限,agent 传更大值会被 clamp 到这里


def _kill_process_tree(pid: int) -> None:
    """杀掉一个进程以及它派生的所有子进程。

    Windows 上 subprocess.run(..., timeout=...) 只杀直接子进程 (通常是 cmd.exe)
    然后 *等管道关闭*,如果孙进程 (python.exe) 还在写就死等到死。所以我们直接
    用 taskkill /F /T 强制递归杀整棵树。
    """
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _bash(command: str, timeout: int = _BASH_MAX_TIMEOUT) -> str:
    """Run a shell command with a hard wall-clock timeout (max 120s).

    Agent-provided timeout is clamped to [_BASH_MAX_TIMEOUT]. On timeout, the
    whole process tree is killed via taskkill /T (Windows) or killpg (Unix),
    so grandchildren can't keep CPU busy after we report timeout.
    """
    timeout = max(1, min(int(timeout), _BASH_MAX_TIMEOUT))
    popen_kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=True, cwd=os.getcwd(),
    )
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True  # so killpg works

    try:
        proc = subprocess.Popen(command, **popen_kwargs)
    except Exception as e:
        return f"Error: {e}"

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc.pid)
        # 给一点时间让管道关闭,但不无限等
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        return f"Error: timed out after {timeout}s (process tree killed)"

    out = stdout or ""
    if stderr:
        out += ("\n" if out else "") + "[stderr]\n" + stderr
    return out.strip() or "(no output)"


def _glob(pattern: str, path: str = None) -> str:
    base = Path(path) if path else Path.cwd()
    try:
        matches = sorted(base.glob(pattern))
        if not matches:
            return "No files matched"
        return "\n".join(str(m) for m in matches[:500])
    except Exception as e:
        return f"Error: {e}"


def _has_rg() -> bool:
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _grep(pattern: str, path: str = None, glob: str = None,
          output_mode: str = "files_with_matches",
          case_insensitive: bool = False, context: int = 0) -> str:
    use_rg = _has_rg()
    cmd = ["rg" if use_rg else "grep", "--no-heading"]
    if case_insensitive:
        cmd.append("-i")
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    else:
        cmd.append("-n")
        if context:
            cmd += ["-C", str(context)]
    if glob:
        cmd += (["--glob", glob] if use_rg else ["--include", glob])
    cmd.append(pattern)
    cmd.append(path or str(Path.cwd()))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        return out[:20000] if out else "No matches found"
    except Exception as e:
        return f"Error: {e}"


def _webfetch(url: str, prompt: str = None) -> str:
    try:
        import httpx
        r = httpx.get(url, headers={"User-Agent": "NanoClaude/1.0"},
                      timeout=30, follow_redirects=True)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "html" in ct:
            text = re.sub(r"<script[^>]*>.*?</script>", "", r.text,
                          flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text,
                          flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
        else:
            text = r.text
        return text[:25000]
    except ImportError:
        return "Error: httpx not installed — run: pip install httpx"
    except Exception as e:
        return f"Error: {e}"


def _websearch(query: str) -> str:
    try:
        import httpx
        url = "https://html.duckduckgo.com/html/"
        r = httpx.get(url, params={"q": query},
                      headers={"User-Agent": "Mozilla/5.0 (compatible)"},
                      timeout=30, follow_redirects=True)
        titles   = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                               r.text, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</div>', r.text, re.DOTALL)
        results = []
        for i, (link, title) in enumerate(titles[:8]):
            t = re.sub(r"<[^>]+>", "", title).strip()
            s = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            results.append(f"**{t}**\n{link}\n{s}")
        return "\n\n".join(results) if results else "No results found"
    except ImportError:
        return "Error: httpx not installed — run: pip install httpx"
    except Exception as e:
        return f"Error: {e}"


# ── Stubs for removed tools (prevent import errors) ─────���─────────────────

def drain_pending_questions() -> bool:
    return False


# ── Dispatcher (backward-compatible wrapper) ──────────────────────────────

def execute_tool(
    name: str,
    inputs: dict,
    permission_mode: str = "auto",
    ask_permission: Optional[Callable[[str], bool]] = None,
    config: dict = None,
) -> str:
    """Dispatch tool execution; ask permission for write/destructive ops.

    Permission checking is done here, then delegation goes to the registry.
    The config dict is forwarded to tool functions so they can access
    runtime context like _depth, _system_prompt, model, etc.
    """
    cfg = config or {}

    def _check(desc: str) -> bool:
        """Return True if action is allowed."""
        if permission_mode == "accept-all":
            return True
        if ask_permission:
            return ask_permission(desc)
        return True  # headless: allow everything

    # --- permission gate ---
    if name == "Write":
        if not _check(f"Write to {inputs['file_path']}"):
            return "Denied: user rejected write operation"
    elif name == "Edit":
        if not _check(f"Edit {inputs['file_path']}"):
            return "Denied: user rejected edit operation"
    elif name == "Bash":
        cmd = inputs["command"]
        if permission_mode != "accept-all" and not _is_safe_bash(cmd):
            if not _check(f"Bash: {cmd}"):
                return "Denied: user rejected bash command"
    return _registry_execute(name, inputs, cfg)


# ── Register built-in tools with the plugin registry ─────────────────────

def _register_builtins() -> None:
    """Register all built-in tools into the central registry."""
    _schemas = {s["name"]: s for s in TOOL_SCHEMAS}

    _tool_defs = [
        ToolDef(
            name="Read",
            schema=_schemas["Read"],
            func=lambda p, c: _read(**p),
            read_only=True,
            concurrent_safe=True,
        ),
        ToolDef(
            name="Write",
            schema=_schemas["Write"],
            func=lambda p, c: _write(**p),
            read_only=False,
            concurrent_safe=False,
        ),
        ToolDef(
            name="Edit",
            schema=_schemas["Edit"],
            func=lambda p, c: _edit(**p),
            read_only=False,
            concurrent_safe=False,
        ),
        ToolDef(
            name="Bash",
            schema=_schemas["Bash"],
            func=lambda p, c: _bash(p["command"], p.get("timeout", _BASH_MAX_TIMEOUT)),
            read_only=False,
            concurrent_safe=False,
        ),
        ToolDef(
            name="Glob",
            schema=_schemas["Glob"],
            func=lambda p, c: _glob(p["pattern"], p.get("path")),
            read_only=True,
            concurrent_safe=True,
        ),
        ToolDef(
            name="Grep",
            schema=_schemas["Grep"],
            func=lambda p, c: _grep(
                p["pattern"], p.get("path"), p.get("glob"),
                p.get("output_mode", "files_with_matches"),
                p.get("case_insensitive", False),
                p.get("context", 0),
            ),
            read_only=True,
            concurrent_safe=True,
        ),
        ToolDef(
            name="WebFetch",
            schema=_schemas["WebFetch"],
            func=lambda p, c: _webfetch(p["url"], p.get("prompt")),
            read_only=True,
            concurrent_safe=True,
        ),
        ToolDef(
            name="WebSearch",
            schema=_schemas["WebSearch"],
            func=lambda p, c: _websearch(p["query"]),
            read_only=True,
            concurrent_safe=True,
        ),
    ]
    for td in _tool_defs:
        register_tool(td)


_register_builtins()

# ── Memory tools (MemorySave, MemoryDelete, MemorySearch, MemoryList) ────
import memory.tools as _memory_tools  # noqa: F401
