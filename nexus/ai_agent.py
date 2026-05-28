"""
nexus/ai_agent.py — Graph-traversing AI orchestrator.

Flow
────
  user query ─→ keyword-score all nodes
             ─→ build context string (summaries + edge relationships)
             ─→ call LLM (Mistral 7B / Groq) with context
             ─→ parse response for "call: fn_name" directives
             ─→ execute those functions via registry (max 2 auto-calls)
             ─→ emit formatted HTML-friendly result
"""
from __future__ import annotations

import json
import re

from PyQt6.QtCore import QThread, pyqtSignal

from nexus.graph_db import all_nodes, edges_for_node, get_node
from nexus.registry import all_functions, call as reg_call


# ── Node relevance scoring ────────────────────────────────────────────────────

_STOP = {
    "i", "a", "the", "to", "and", "or", "is", "it", "my", "for",
    "this", "that", "can", "do", "with", "of", "in", "on", "at",
    "want", "me", "please", "how", "what", "who", "hey",
}


def find_relevant_nodes(query: str, top_k: int = 6) -> list[dict]:
    terms = set(query.lower().split()) - _STOP
    if not terms:
        return all_nodes()[:top_k]

    scored: list[tuple[int, dict]] = []
    for node in all_nodes():
        text = " ".join([
            node.get("label", ""),
            node.get("summary", ""),
            node.get("type", ""),
            json.dumps(node.get("meta") or {}),
        ]).lower()
        score = sum(1 for t in terms if t in text)
        if score:
            scored.append((score, node))

    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:top_k]]


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(nodes: list[dict]) -> str:
    if not nodes:
        return "No relevant nodes found in the knowledge graph."

    lines = ["KNOWLEDGE GRAPH CONTEXT:", ""]
    for n in nodes:
        lines.append(f"[{n['type']}] {n['label']}")
        if n.get("summary"):
            lines.append(f"  Summary: {n['summary']}")
        meta = n.get("meta") or {}
        if meta.get("callable"):
            lines.append(f"  Callable key: {meta['callable']}")
        edges = edges_for_node(n["id"])
        conns = []
        for e in edges[:3]:
            other_id = e["tgt_id"] if e["src_id"] == n["id"] else e["src_id"]
            other = get_node(other_id)
            if other:
                direction = "→" if e["src_id"] == n["id"] else "←"
                lbl = e.get("label") or "linked to"
                conns.append(f"{direction} {other['label']} ({lbl})")
        if conns:
            lines.append(f"  Connections: {'; '.join(conns)}")
        lines.append("")

    fns = all_functions()
    if fns:
        lines.append("REGISTERED FUNCTIONS:")
        for f in fns:
            lines.append(f"  • {f['name']}: {f['description']}")
        lines.append("")

    return "\n".join(lines)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt: str) -> str:
    try:
        import modules.llm_summarizer as ls
        if hasattr(ls, "ask"):
            return ls.ask(prompt)
        llm = getattr(ls, "_llm", None)
        if llm:
            out = llm(prompt, max_tokens=512, temperature=0.7,
                      stop=["<|im_end|>", "</s>", "\n\n---"])
            return (out.get("choices") or [{}])[0].get("text", "").strip()
    except Exception as e:
        return f"[LLM unavailable: {e}]"
    return "[LLM not loaded — start model in Settings]"


# ── Background worker ─────────────────────────────────────────────────────────

class AgentWorker(QThread):
    """Runs the full NexusOS AI pipeline off the UI thread."""

    result = pyqtSignal(str, list)   # (formatted_text, relevant_node_ids)
    error  = pyqtSignal(str)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        try:
            query = self._query.strip()
            if not query:
                self.result.emit("Enter a command or question above.", [])
                return

            nodes = find_relevant_nodes(query)
            node_ids = [n["id"] for n in nodes]
            context = _build_context(nodes)

            prompt = (
                "You are NexusOS, an AI-native operating system with access to a "
                "knowledge graph of apps, files, and functions.\n\n"
                f"{context}\n"
                f"User request: {query}\n\n"
                "Describe what you would do to fulfill this request using the available "
                "knowledge graph nodes and functions. If you would call a registered "
                "function, mention it with 'call: function_name'."
            )

            response = _call_llm(prompt)

            # Parse + execute function calls (max 2 for safety)
            fn_matches = re.findall(r"call:\s*(\w+)", response, re.IGNORECASE)
            exec_results: list[str] = []
            for fn_name in fn_matches[:2]:
                try:
                    out = reg_call(fn_name)
                    exec_results.append(f"✓ {fn_name}() → {str(out)[:120]}")
                except KeyError:
                    exec_results.append(f"⚠ {fn_name} is not registered")
                except Exception as e:
                    exec_results.append(f"✕ {fn_name} error: {str(e)[:80]}")

            # Format output (uses simple markers that _AIBar._on_result renders)
            parts = [f"**Query:** {query}", ""]
            if nodes:
                badges = "  ".join(f"[{n['label']}]" for n in nodes)
                parts += [f"**Relevant nodes:** {badges}", ""]
            parts.append(response.strip())
            if exec_results:
                parts += ["", "**Execution:**"] + exec_results

            self.result.emit("\n".join(parts), node_ids)

        except Exception as e:
            self.error.emit(str(e))
