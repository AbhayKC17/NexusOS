"""
nexus/graph_db.py — Persistent graph store for NexusOS.

Schema
──────
  nexus_nodes  id, type, label, path, summary, meta_json, pos_x, pos_y
  nexus_edges  id, src_id, tgt_id, label, rel_type

Node types
──────────
  APP | FUNCTION | FILE_EXCEL | FILE_PDF | FILE_TEXT |
  FILE_CODE | FILE_IMAGE | NOTE | API | DATA
"""
import json
import os
import sqlite3
import uuid as _uuid

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nexus.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_nexus_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS nexus_nodes (
                id       TEXT PRIMARY KEY,
                type     TEXT NOT NULL DEFAULT 'DEFAULT',
                label    TEXT NOT NULL,
                path     TEXT,
                summary  TEXT,
                meta     TEXT DEFAULT '{}',
                pos_x    REAL DEFAULT 0,
                pos_y    REAL DEFAULT 0,
                created  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS nexus_edges (
                id       TEXT PRIMARY KEY,
                src_id   TEXT NOT NULL,
                tgt_id   TEXT NOT NULL,
                label    TEXT DEFAULT '',
                rel_type TEXT DEFAULT 'REFERENCE',
                created  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (src_id) REFERENCES nexus_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (tgt_id) REFERENCES nexus_nodes(id) ON DELETE CASCADE
            );
        """)


# ── Nodes ─────────────────────────────────────────────────────────────────────

def add_node(type_: str, label: str, path: str = None, summary: str = "",
             meta: dict = None, pos_x: float = 0, pos_y: float = 0) -> str:
    nid = str(_uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO nexus_nodes (id,type,label,path,summary,meta,pos_x,pos_y) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (nid, type_, label, path, summary,
             json.dumps(meta or {}), pos_x, pos_y)
        )
    return nid


def update_node(nid: str, **kwargs):
    allowed = {"label", "summary", "path", "meta", "pos_x", "pos_y", "type"}
    fields  = {k: v for k, v in kwargs.items() if k in allowed}
    if "meta" in fields and isinstance(fields["meta"], dict):
        fields["meta"] = json.dumps(fields["meta"])
    if not fields:
        return
    sql = "UPDATE nexus_nodes SET " + ", ".join(f"{k}=?" for k in fields)
    sql += " WHERE id=?"
    with _conn() as c:
        c.execute(sql, list(fields.values()) + [nid])


def delete_node(nid: str):
    with _conn() as c:
        c.execute("DELETE FROM nexus_nodes WHERE id=?", (nid,))


def get_node(nid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM nexus_nodes WHERE id=?", (nid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["meta"] = json.loads(d.get("meta") or "{}")
    return d


def all_nodes() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM nexus_nodes ORDER BY created").fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["meta"] = json.loads(d.get("meta") or "{}")
        out.append(d)
    return out


# ── Edges ─────────────────────────────────────────────────────────────────────

def add_edge(src_id: str, tgt_id: str,
             label: str = "", rel_type: str = "REFERENCE") -> str:
    eid = str(_uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO nexus_edges (id,src_id,tgt_id,label,rel_type) VALUES (?,?,?,?,?)",
            (eid, src_id, tgt_id, label, rel_type)
        )
    return eid


def delete_edge(eid: str):
    with _conn() as c:
        c.execute("DELETE FROM nexus_edges WHERE id=?", (eid,))


def all_edges() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM nexus_edges").fetchall()
    return [dict(r) for r in rows]


def edges_for_node(nid: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM nexus_edges WHERE src_id=? OR tgt_id=?", (nid, nid)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Seeding default nodes ─────────────────────────────────────────────────────

def seed_default_graph():
    """Pre-populate the graph with JobTracker app nodes on first run."""
    if all_nodes():
        return  # Already seeded

    # Absolute path to the JobTracker app inside NexusOS/apps/job_tracker/
    _nexus_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _jt_root = os.path.join(_nexus_root, "apps", "job_tracker")

    # Core app + model
    jt = add_node("APP", "JobTracker",
                  path=_jt_root,
                  summary="AI Job Application Manager — send emails, track replies, build resumes.",
                  meta={"app_module": "shell.window"},
                  pos_x=-60, pos_y=0)
    ml = add_node("APP",       "Mistral 7B",        summary="Local LLM running via llama.cpp — powers all AI features in the graph.", pos_x=200,  pos_y=-160)
    db = add_node("DATA",      "Applications DB",  summary="SQLite database holding all company records, statuses, and raw enrichment data.", pos_x=-300, pos_y=0)

    # Functions (children of JobTracker)
    em = add_node("FUNCTION",  "Email Sender",     summary="Sends personalised cold emails via Apple Mail or Gmail OAuth. Attaches your resume.",  pos_x=-200, pos_y=160,  meta={"callable": "send_email"})
    rs = add_node("FUNCTION",  "Resume Builder",   summary="Takes a job description, calls Groq AI, and exports a tailored PDF resume.",           pos_x=60,   pos_y=200,  meta={"callable": "build_resume"})
    cp = add_node("FUNCTION",  "Campaign Sender",  summary="Bulk-sends emails to all pending applications with AI-personalised intros.",            pos_x=-300, pos_y=180,  meta={"callable": "run_campaign"})
    ai = add_node("FUNCTION",  "AI Assistant",     summary="Chat with Mistral 7B about job strategy, interview prep, and cold email writing.",      pos_x=240,  pos_y=60,   meta={"callable": "ask_ai"})
    sy = add_node("FUNCTION",  "Reply Sync",       summary="Scans inbox, matches emails to TKEY tracking keys, generates AI reply drafts.",         pos_x=-120, pos_y=-180, meta={"callable": "sync_replies"})

    # Edges
    for src, tgt, lbl in [
        (jt, db, "reads"),
        (jt, em, "contains"),
        (jt, rs, "contains"),
        (jt, cp, "contains"),
        (jt, ai, "contains"),
        (jt, sy, "contains"),
        (ml, ai, "powers"),
        (ml, em, "generates intro"),
        (ml, rs, "writes bullets"),
        (db, cp, "feeds"),
        (db, em, "provides contacts"),
    ]:
        add_edge(src, tgt, lbl, "USES")
