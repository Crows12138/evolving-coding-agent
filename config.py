"""Configuration management for nano claude (multi-provider)."""
import os
import json
from pathlib import Path

CONFIG_DIR   = Path.home() / ".evolving_coding_agent"
CONFIG_FILE  = CONFIG_DIR  / "config.json"
HISTORY_FILE = CONFIG_DIR  / "input_history.txt"
SESSIONS_DIR = CONFIG_DIR  / "sessions"

MR_SESSION_DIR = SESSIONS_DIR / "mr_sessions"

DEFAULTS = {
    "model":            "ollama/qwen3.5-16k",
    "max_tokens":       4096,     # local-friendly; cloud 模型由 MODEL_DEFAULTS 提升
    "permission_mode":  "auto",   # auto | accept-all | manual
    "verbose":          False,
    "thinking":         False,
    "thinking_budget":  10000,
    "custom_base_url":  "",       # for "custom" provider
    "max_tool_output":  20000,    # local-friendly; cloud 提升到 64000
    "max_agent_depth":  3,
    "max_concurrent_agents": 3,
    # Per-provider API keys (optional; env vars take priority)
    # "anthropic_api_key": "sk-ant-..."
    # "openai_api_key":    "sk-..."
    # "gemini_api_key":    "..."
    # "kimi_api_key":      "..."
    # "qwen_api_key":      "..."
    # "zhipu_api_key":     "..."
    # "deepseek_api_key":  "..."
}


# 按模型类型自动调整 token 预算。本地小模型上下文窗口小 (~16K),
# max_tokens 要给 input 留空间;云端大模型不缺空间,可以放大。
# 用户在 config.json 里显式设的值优先级最高,不会被覆盖。
_LOCAL_PROVIDER_PREFIXES = ("ollama/", "lmstudio/", "custom/")

MODEL_DEFAULTS = {
    "local": {"max_tokens": 4096, "max_tool_output": 20000},
    "cloud": {"max_tokens": 8192, "max_tool_output": 64000},
}


def _model_class(model: str) -> str:
    return "local" if model.startswith(_LOCAL_PROVIDER_PREFIXES) else "cloud"


def load_config() -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    cfg = dict(DEFAULTS)

    user_keys: set[str] = set()
    if CONFIG_FILE.exists():
        try:
            user_cfg = json.loads(CONFIG_FILE.read_text())
            user_keys = set(user_cfg.keys())
            cfg.update(user_cfg)
        except Exception:
            pass

    # 按模型自动设 token 预算 — 仅填充用户没显式设的键
    mc = _model_class(cfg.get("model", ""))
    for k, v in MODEL_DEFAULTS[mc].items():
        if k not in user_keys:
            cfg[k] = v

    # Backward-compat: legacy single api_key → anthropic_api_key
    if cfg.get("api_key") and not cfg.get("anthropic_api_key"):
        cfg["anthropic_api_key"] = cfg.pop("api_key")
    # Also accept ANTHROPIC_API_KEY env for backward-compat
    if not cfg.get("anthropic_api_key"):
        cfg["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    return cfg


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    data = dict(cfg)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def current_provider(cfg: dict) -> str:
    from providers import detect_provider
    return detect_provider(cfg.get("model", "claude-opus-4-6"))


def has_api_key(cfg: dict) -> bool:
    """Check whether the active provider has an API key configured."""
    from providers import get_api_key
    pname = current_provider(cfg)
    key = get_api_key(pname, cfg)
    return bool(key)


def calc_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    from providers import calc_cost as _cc
    return _cc(model, in_tokens, out_tokens)
