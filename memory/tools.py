"""Memory tool registrations: MemorySave, MemoryDelete, MemorySearch.

Importing this module registers the three tools into the central registry.
"""
from __future__ import annotations

from datetime import datetime

from tool_registry import ToolDef, register_tool
from .store import MemoryEntry, save_memory, delete_memory, load_index
from .context import find_relevant_memories
from .scan import scan_all_memories, format_memory_manifest


# ── Tool implementations ───────────────────────────────────────────────────

def _memory_save(params: dict, config: dict) -> str:
    """Save or update a persistent memory entry."""
    entry = MemoryEntry(
        name=params["name"],
        description=params["description"],
        type=params["type"],
        content=params["content"],
        created=datetime.now().strftime("%Y-%m-%d"),
    )
    scope = params.get("scope", "user")
    save_memory(entry, scope=scope)

    scope_label = "project" if scope == "project" else "user"
    return f"Memory saved: '{entry.name}' [{entry.type}/{scope_label}]"


def _memory_delete(params: dict, config: dict) -> str:
    """Delete a persistent memory entry by name."""
    name = params["name"]
    scope = params.get("scope", "user")
    delete_memory(name, scope=scope)
    return f"Memory deleted: '{name}' (scope: {scope})"


def _memory_search(params: dict, config: dict) -> str:
    """Search memories by keyword query with optional AI relevance filtering."""
    query = params["query"]
    use_ai = params.get("use_ai", False)
    max_results = params.get("max_results", 5)

    results = find_relevant_memories(
        query, max_results=max_results, use_ai=use_ai, config=config
    )

    if not results:
        return f"No memories found matching '{query}'."

    lines = [f"Found {len(results)} relevant memory/memories for '{query}':", ""]
    for r in results:
        freshness = f"  ⚠ {r['freshness_text']}" if r["freshness_text"] else ""
        lines.append(
            f"[{r['type']}/{r['scope']}] {r['name']}\n"
            f"  {r['description']}\n"
            f"  {r['content'][:200]}{'...' if len(r['content']) > 200 else ''}"
            f"{freshness}"
        )
    return "\n\n".join(lines)


def _memory_list(params: dict, config: dict) -> str:
    """List all memory entries with their manifest (type, scope, age, description)."""
    headers = scan_all_memories()
    if not headers:
        return "No memories stored."

    scope_filter = params.get("scope", "all")
    if scope_filter != "all":
        headers = [h for h in headers if h.scope == scope_filter]
        if not headers:
            return f"No {scope_filter} memories stored."

    manifest = format_memory_manifest(headers)
    return f"{len(headers)} memory/memories:\n\n{manifest}"


# ── Tool registrations ─────────────────────────────────────────────────────

register_tool(ToolDef(
    name="MemorySave",
    schema={
        "name": "MemorySave",
        "description": (
            "Save a persistent memory entry as a markdown file with frontmatter. "
            "Use for information that should persist across conversations: "
            "user preferences, feedback/corrections, project context, or external references. "
            "Do NOT save: code patterns, architecture, git history, or task state.\n\n"
            "For feedback/project memories, structure content as: "
            "rule/fact, then **Why:** and **How to apply:** lines."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name (becomes the filename slug)",
                },
                "type": {
                    "type": "string",
                    "enum": ["user", "feedback", "project", "reference"],
                    "description": (
                        "user=preferences/role, feedback=guidance on how to work, "
                        "project=ongoing work/decisions, reference=external system pointers"
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Short one-line description (used for relevance decisions — be specific)",
                },
                "content": {
                    "type": "string",
                    "description": "Body text. For feedback/project: rule/fact + **Why:** + **How to apply:**",
                },
                "scope": {
                    "type": "string",
                    "enum": ["user", "project"],
                    "description": (
                        "'user' (default) = ~/.nano_claude/memory/ shared across projects; "
                        "'project' = .nano_claude/memory/ local to this project"
                    ),
                },
            },
            "required": ["name", "type", "description", "content"],
        },
    },
    func=_memory_save,
    read_only=False,
    concurrent_safe=False,
))

register_tool(ToolDef(
    name="MemoryDelete",
    schema={
        "name": "MemoryDelete",
        "description": "Delete a persistent memory entry by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the memory to delete"},
                "scope": {
                    "type": "string",
                    "enum": ["user", "project"],
                    "description": "Scope to delete from (default: 'user')",
                },
            },
            "required": ["name"],
        },
    },
    func=_memory_delete,
    read_only=False,
    concurrent_safe=False,
))

register_tool(ToolDef(
    name="MemorySearch",
    schema={
        "name": "MemorySearch",
        "description": (
            "Search persistent memories by keyword. Returns matching entries with "
            "content preview and staleness warning for old memories. "
            "Set use_ai=true to use AI-powered relevance ranking (costs a small API call)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 5)",
                },
                "use_ai": {
                    "type": "boolean",
                    "description": "Use AI relevance ranking (default: false = keyword only)",
                },
                "scope": {
                    "type": "string",
                    "enum": ["user", "project", "all"],
                    "description": "Which scope to search (default: 'all')",
                },
            },
            "required": ["query"],
        },
    },
    func=_memory_search,
    read_only=True,
    concurrent_safe=True,
))

register_tool(ToolDef(
    name="MemoryList",
    schema={
        "name": "MemoryList",
        "description": (
            "List all memory entries with type, scope, age, and description. "
            "Useful for reviewing what's been remembered before deciding to save or delete."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["user", "project", "all"],
                    "description": "Which scope to list (default: 'all')",
                },
            },
        },
    },
    func=_memory_list,
    read_only=True,
    concurrent_safe=True,
))
