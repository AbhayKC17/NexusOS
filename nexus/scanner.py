"""
nexus/scanner.py — Filesystem → graph node scanner.

Called on NexusOS startup to index a directory into the knowledge graph.
Already-indexed paths are skipped so re-runs are idempotent.
"""
from __future__ import annotations

import os

from nexus.graph_db import all_nodes, add_node


# ── Extension → node type ─────────────────────────────────────────────────────

_EXT_TYPE: dict[str, str] = {
    ".xlsx": "FILE_EXCEL", ".xls": "FILE_EXCEL", ".csv": "FILE_EXCEL",
    ".pdf":  "FILE_PDF",
    ".txt":  "FILE_TEXT",  ".md":  "FILE_TEXT",  ".rst": "FILE_TEXT",
    ".py":   "FILE_CODE",  ".js":  "FILE_CODE",  ".ts":  "FILE_CODE",
    ".cpp":  "FILE_CODE",  ".c":   "FILE_CODE",  ".go":  "FILE_CODE",
    ".java": "FILE_CODE",  ".rb":  "FILE_CODE",  ".sh":  "FILE_CODE",
    ".png":  "FILE_IMAGE", ".jpg": "FILE_IMAGE",  ".jpeg":"FILE_IMAGE",
    ".gif":  "FILE_IMAGE", ".bmp": "FILE_IMAGE",  ".webp":"FILE_IMAGE",
    ".svg":  "FILE_IMAGE",
}

# Folders that look like Python/JS apps
_APP_ENTRY_FILES = {"main.py", "app.py", "desktop_app.py", "index.js", "package.json"}

# Folders we always skip (noisy / system)
_SKIP_NAMES = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".DS_Store", ".Trash", "Trash",
}


# ── Public API ────────────────────────────────────────────────────────────────

def scan_desktop(root: str) -> int:
    """
    Walk *root* (one level deep) and add files + folders as graph nodes.
    Returns the number of new nodes added.
    """
    if not os.path.isdir(root):
        return 0

    # Build a set of paths already in the graph
    existing: set[str] = {
        n["path"] for n in all_nodes() if n.get("path")
    }

    added = 0
    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return 0

    for name in entries:
        if name.startswith(".") or name in _SKIP_NAMES:
            continue

        full_path = os.path.join(root, name)

        # Skip things we've already indexed
        if full_path in existing:
            continue

        if os.path.isdir(full_path):
            ntype, summary = _classify_dir(name, full_path)
        else:
            result = _classify_file(name, full_path)
            if result is None:
                continue
            ntype, summary = result

        add_node(ntype, name, path=full_path, summary=summary)
        added += 1

    return added


# ── Classifiers ───────────────────────────────────────────────────────────────

def _classify_dir(name: str, path: str) -> tuple[str, str]:
    # Detect Python / JS apps
    try:
        contents = set(os.listdir(path))
    except PermissionError:
        return "DATA", f"Folder: {name}"

    if contents & _APP_ENTRY_FILES:
        return "APP", f"App: {name}"

    # Folders full of images → image collection
    exts = {os.path.splitext(f)[1].lower() for f in contents}
    img_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    if len(exts & img_exts) >= 2:
        return "DATA", f"Image folder: {name}"

    return "DATA", f"Folder: {name}"


def _classify_file(name: str, path: str) -> tuple[str, str] | None:
    ext = os.path.splitext(name)[1].lower()
    ntype = _EXT_TYPE.get(ext)
    if not ntype:
        return None   # Unknown type — skip
    return ntype, f"{ntype.replace('FILE_', '').capitalize()}: {name}"
