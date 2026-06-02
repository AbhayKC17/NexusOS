"""
nexus/registry.py  —  NexusOS Function Registry
================================================

Central callable registry used by:
  • The NexusOS graph AI agent (ai_agent.py)
  • The JobTracker AI assistant page
  • External agents / automation

Usage:
    from nexus.registry import register, call, get_manifest, call_tool

Key concepts:
  - register(name, fn, description, schema, category)  → add any Python callable
  - call(name, **kwargs)                               → execute by name
  - get_manifest()                                     → full tool list for AI
  - seed_jobtracker()                                  → loads all JobTracker tools
"""
from __future__ import annotations
from typing import Callable, Any

# Internal store:  name → {fn, description, schema, category, node_id}
_registry: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Core API
# ─────────────────────────────────────────────────────────────────────────────

def register(
    name:        str,
    fn:          Callable,
    description: str = "",
    schema:      dict | None = None,
    category:    str = "General",
    node_id:     str | None = None,
) -> None:
    """
    Register a callable under a name.

    Args:
        name:        Unique tool identifier (snake_case)
        fn:          Python callable to invoke
        description: Human + AI readable description of what the tool does
        schema:      Optional dict with 'parameters' and 'returns' keys (OpenAI-style)
        category:    Grouping label (Applications / Email / Campaign / …)
        node_id:     Optional NexusOS graph node ID this tool belongs to
    """
    _registry[name] = {
        "fn":          fn,
        "description": description,
        "schema":      schema or {},
        "category":    category,
        "node_id":     node_id,
    }


def get(name: str) -> dict | None:
    """Return the registry entry for a tool, or None."""
    return _registry.get(name)


def call(name: str, **kwargs) -> Any:
    """Execute a registered tool by name. Raises KeyError if not found."""
    entry = _registry.get(name)
    if not entry:
        available = ", ".join(sorted(_registry.keys()))
        raise KeyError(
            f"Tool '{name}' not in registry. "
            f"Available tools: {available[:200]}"
        )
    return entry["fn"](**kwargs)


def all_functions() -> list[dict]:
    """Return a summary list of all registered tools (no callables exposed)."""
    return [
        {
            "name":        k,
            "description": v["description"],
            "category":    v["category"],
            "node_id":     v["node_id"],
        }
        for k, v in _registry.items()
    ]


def get_manifest() -> dict:
    """
    Return the complete tool manifest for AI consumption.

    The manifest is organised by category and includes description,
    parameter names, and a usage example for each tool.

    Returns:
        dict with keys: system, total_tools, categories, tools_by_category, usage_hint
    """
    by_cat: dict[str, list] = {}
    for name, entry in _registry.items():
        cat = entry.get("category", "General")
        schema = entry.get("schema", {})
        params = list(schema.get("parameters", {}).keys())
        by_cat.setdefault(cat, []).append({
            "name":        name,
            "description": entry["description"],
            "params":      params,
            "example":     schema.get("example", f"{name}({', '.join(params[:2])})"),
        })

    return {
        "system":             "NexusOS + JobTracker",
        "total_tools":        len(_registry),
        "categories":         sorted(by_cat.keys()),
        "tools_by_category":  by_cat,
        "usage_hint": (
            "Discover tools: get_manifest()  "
            "Execute tool: call(name, **kwargs)  "
            "Full schema: get_tool_schema(name)"
        ),
    }


def get_tool_schema(name: str) -> dict | None:
    """Return the full schema dict for one tool, or None if not registered."""
    entry = _registry.get(name)
    if not entry:
        return None
    return {
        "name":        name,
        "description": entry["description"],
        "category":    entry["category"],
        **entry.get("schema", {}),
    }


def format_for_prompt() -> str:
    """
    Render the full registry as a compact text block for injecting into an LLM prompt.
    Groups tools by category; marks required params with *.
    """
    manifest = get_manifest()
    lines = [
        "=== AVAILABLE TOOLS ===",
        f"Total: {manifest['total_tools']} tools across "
        f"{len(manifest['categories'])} categories\n",
    ]
    for cat in manifest["categories"]:
        lines.append(f"\n── {cat.upper()} ──")
        for tool in manifest["tools_by_category"][cat]:
            entry  = _registry[tool["name"]]
            params = entry.get("schema", {}).get("parameters", {})
            sig    = ", ".join(
                f"{k}: {v.get('type','any')}{'*' if v.get('required') else '?'}"
                for k, v in params.items()
            )
            lines.append(f"  {tool['name']}({sig})")
            lines.append(f"    {tool['description'][:120]}")
    lines.append("\n(* = required, ? = optional)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  JobTracker seed  —  registers all 20+ tools from ai_tools.py
# ─────────────────────────────────────────────────────────────────────────────

def seed_jobtracker() -> None:
    """
    Register every JobTracker tool from ai_tools.py into this registry.
    Called once at app startup (main.py or desktop_app.py).

    Also registers a few NexusOS-native tools (graph query, ask_ai).
    """
    try:
        from apps.job_tracker.ai_tools import TOOL_SCHEMAS, call_tool as _call_tool

        for schema in TOOL_SCHEMAS:
            name = schema["name"]

            # Create a closure that captures the tool name correctly
            def _make_fn(n):
                def _fn(**kw):
                    return _call_tool(n, **kw)
                _fn.__name__ = n
                return _fn

            register(
                name        = name,
                fn          = _make_fn(name),
                description = schema["description"],
                schema      = schema,
                category    = schema.get("category", "General"),
            )

    except ImportError as e:
        # App may not be in sys.path during NexusOS graph load — safe to ignore
        _register_legacy_fallbacks()
        return

    # ── NexusOS-native tools ─────────────────────────────────────────────────

    try:
        def _get_manifest_tool():
            from apps.job_tracker.ai_tools import get_ai_manifest
            return get_ai_manifest()

        register(
            "list_all_tools",
            _get_manifest_tool,
            description=(
                "Return the complete catalog of all AI-callable tools with descriptions, "
                "parameter schemas, and examples. Call this first to discover capabilities."
            ),
            schema={
                "parameters": {},
                "returns": {"type": "dict", "description": "Full tool manifest by category"},
                "example": "list_all_tools()",
            },
            category="NexusOS",
        )
    except Exception:
        pass

    try:
        def _format_manifest_tool():
            from apps.job_tracker.ai_tools import format_manifest_for_prompt
            return format_manifest_for_prompt()

        register(
            "describe_my_capabilities",
            _format_manifest_tool,
            description=(
                "Return a human-readable summary of every tool I have access to. "
                "Use this when the user asks 'what can you do?' or 'what tools do you have?'."
            ),
            schema={
                "parameters": {},
                "returns": {"type": "str", "description": "Formatted tool catalog text"},
                "example": "describe_my_capabilities()",
            },
            category="NexusOS",
        )
    except Exception:
        pass


def _register_legacy_fallbacks() -> None:
    """Minimal legacy registrations for when the full ai_tools module isn't importable."""
    try:
        from modules.quick_mailer import quick_send_email
        register(
            "send_email", quick_send_email,
            description="Send a personalised email with resume attached.",
            category="Email",
        )
    except Exception:
        pass

    try:
        from modules.resume_builder import build_resume_pdf
        register(
            "build_resume", build_resume_pdf,
            description="Generate a tailored PDF resume from a job description.",
            category="Resume",
        )
    except Exception:
        pass

    try:
        import modules.llm_summarizer as _ls
        _ask = getattr(_ls, "ask", None) or (lambda q: _ls.summarize(q))
        register(
            "ask_ai", _ask,
            description="Ask the local Mistral 7B AI a question.",
            category="Intelligence",
        )
    except Exception:
        pass

    try:
        from modules.email_monitor import sync_inbox
        register(
            "sync_replies", sync_inbox,
            description="Scan inbox for replies and link them to applications.",
            category="Inbox",
        )
    except Exception:
        pass
