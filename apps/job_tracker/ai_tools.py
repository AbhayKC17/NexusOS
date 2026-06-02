"""
ai_tools.py  —  JobTracker AI Tool Catalog
==========================================

Every callable function is registered here with a full machine-readable schema:
  name, category, description, parameters (name/type/required/description), returns, example.

The AI assistant can call  `get_ai_manifest()`  to discover all capabilities,
then execute any tool via  `call_tool(name, **kwargs)`.

Categories:
  Applications  — CRUD for job applications
  Email         — Compose, send, track emails
  Campaign      — Bulk outreach campaigns
  Inbox         — Sync and read received emails
  Resume        — AI resume generation
  Intelligence  — AI analysis, search, drafting
  Data          — Import/export, statistics
"""

from __future__ import annotations
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
#  Tool schema definitions
# ─────────────────────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [

    # ── Applications ─────────────────────────────────────────────────────────

    {
        "name": "add_application",
        "category": "Applications",
        "description": (
            "Add a new company / job application to the tracker. "
            "Returns the new application's UUID."
        ),
        "parameters": {
            "company":       {"type": "str",  "required": True,  "description": "Company name"},
            "position":      {"type": "str",  "required": False, "description": "Job title / role"},
            "contact_email": {"type": "str",  "required": False, "description": "Recruiter or HR email"},
            "contact_name":  {"type": "str",  "required": False, "description": "Recruiter name"},
            "notes":         {"type": "str",  "required": False, "description": "Any extra context about the company"},
            "city":          {"type": "str",  "required": False, "description": "Company city"},
            "country":       {"type": "str",  "required": False, "description": "Company country"},
        },
        "returns": {"type": "dict", "description": "{'id': str, 'company': str, 'status': 'pending'}"},
        "example": 'add_application(company="Acme Corp", position="PM", contact_email="hr@acme.com")',
    },

    {
        "name": "get_application",
        "category": "Applications",
        "description": "Retrieve full details of one application by its UUID.",
        "parameters": {
            "app_id": {"type": "str", "required": True, "description": "Application UUID"},
        },
        "returns": {"type": "dict", "description": "Full application record"},
        "example": 'get_application(app_id="abc-123")',
    },

    {
        "name": "list_applications",
        "category": "Applications",
        "description": "List applications, optionally filtered by status or search query.",
        "parameters": {
            "status": {
                "type": "str",  "required": False,
                "description": "Filter by status: pending | sent | replied | interview | offer | rejected",
            },
            "query": {
                "type": "str",  "required": False,
                "description": "Text search across company, position, city, notes",
            },
            "limit": {
                "type": "int",  "required": False,
                "description": "Max results (default 50)",
            },
        },
        "returns": {"type": "list[dict]", "description": "List of application records"},
        "example": 'list_applications(status="pending", limit=20)',
    },

    {
        "name": "update_application_status",
        "category": "Applications",
        "description": "Change the status of an application.",
        "parameters": {
            "app_id": {
                "type": "str",  "required": True,
                "description": "Application UUID",
            },
            "status": {
                "type": "str",  "required": True,
                "description": "New status: pending | sent | replied | interview | offer | rejected",
            },
        },
        "returns": {"type": "bool", "description": "True on success"},
        "example": 'update_application_status(app_id="abc-123", status="interview")',
    },

    {
        "name": "update_application_notes",
        "category": "Applications",
        "description": "Update or append notes on an application.",
        "parameters": {
            "app_id": {"type": "str",  "required": True,  "description": "Application UUID"},
            "notes":  {"type": "str",  "required": True,  "description": "New notes text"},
        },
        "returns": {"type": "bool", "description": "True on success"},
        "example": 'update_application_notes(app_id="abc-123", notes="Met CTO at conference")',
    },

    {
        "name": "delete_application",
        "category": "Applications",
        "description": "Permanently delete an application record.",
        "parameters": {
            "app_id": {"type": "str", "required": True, "description": "Application UUID"},
        },
        "returns": {"type": "bool", "description": "True on success"},
        "example": 'delete_application(app_id="abc-123")',
    },

    {
        "name": "search_applications",
        "category": "Applications",
        "description": "Full-text search across all application fields.",
        "parameters": {
            "query": {"type": "str",  "required": True,  "description": "Search text"},
            "limit": {"type": "int",  "required": False, "description": "Max results (default 30)"},
        },
        "returns": {"type": "list[dict]", "description": "Matching application records"},
        "example": 'search_applications(query="fintech Berlin")',
    },

    {
        "name": "get_dashboard_stats",
        "category": "Applications",
        "description": "Return aggregate KPIs: total, pending, sent, replied, interviews, reply rate, etc.",
        "parameters": {},
        "returns": {
            "type": "dict",
            "description": (
                "{'total': int, 'pending': int, 'sent': int, 'replied': int, "
                "'interview': int, 'offer': int, 'reply_rate': str, 'countries': int}"
            ),
        },
        "example": "get_dashboard_stats()",
    },

    # ── Email ─────────────────────────────────────────────────────────────────

    {
        "name": "send_email",
        "category": "Email",
        "description": (
            "Send a personalised cold-outreach email to one application. "
            "Attaches resume if configured. Uses Apple Mail, Outlook, or SMTP based on settings."
        ),
        "parameters": {
            "app_id":   {"type": "str",  "required": True,  "description": "Application UUID"},
            "subject":  {"type": "str",  "required": False, "description": "Email subject (auto-generated if omitted)"},
            "body":     {"type": "str",  "required": False, "description": "Email body (auto-generated if omitted)"},
            "dry_run":  {"type": "bool", "required": False, "description": "If True, preview without sending (default False)"},
        },
        "returns": {
            "type": "dict",
            "description": "{'sent': bool, 'uuid': str, 'tkey': str, 'error': str|None}",
        },
        "example": 'send_email(app_id="abc-123")',
    },

    {
        "name": "generate_email_draft",
        "category": "Email",
        "description": (
            "Generate a personalised outreach email (subject + body) using AI "
            "for a given application. Does NOT send it — returns text for review."
        ),
        "parameters": {
            "app_id":       {"type": "str",  "required": True,  "description": "Application UUID"},
            "instructions": {"type": "str",  "required": False, "description": "Extra tone/style instructions"},
        },
        "returns": {
            "type": "dict",
            "description": "{'subject': str, 'body': str}",
        },
        "example": 'generate_email_draft(app_id="abc-123", instructions="emphasise ML experience")',
    },

    {
        "name": "generate_reply_draft",
        "category": "Email",
        "description": "Generate a professional reply to a received email using Groq AI.",
        "parameters": {
            "email_body":  {"type": "str",  "required": True,  "description": "The received email text"},
            "company":     {"type": "str",  "required": False, "description": "Company name for context"},
            "tone":        {"type": "str",  "required": False, "description": "professional | enthusiastic | brief (default professional)"},
        },
        "returns": {"type": "str", "description": "Draft reply text"},
        "example": 'generate_reply_draft(email_body="Thanks for applying...", company="Acme")',
    },

    {
        "name": "schedule_email",
        "category": "Email",
        "description": "Schedule an email to be sent at a future datetime.",
        "parameters": {
            "app_id":       {"type": "str",  "required": True,  "description": "Application UUID"},
            "scheduled_at": {"type": "str",  "required": True,  "description": "ISO datetime string, e.g. 2026-06-05T09:00:00"},
            "subject":      {"type": "str",  "required": False, "description": "Email subject"},
            "body":         {"type": "str",  "required": False, "description": "Email body"},
        },
        "returns": {"type": "dict", "description": "{'id': int, 'scheduled_at': str}"},
        "example": 'schedule_email(app_id="abc-123", scheduled_at="2026-06-05T09:00:00")',
    },

    # ── Campaign ──────────────────────────────────────────────────────────────

    {
        "name": "run_campaign",
        "category": "Campaign",
        "description": (
            "Run a bulk email campaign: iterate over pending (or specified) applications, "
            "generate personalised emails with AI, and send them in sequence."
        ),
        "parameters": {
            "app_ids":      {"type": "list[str]", "required": False, "description": "Specific UUIDs to email; if omitted, all 'pending' applications"},
            "sender_mode":  {"type": "str",  "required": False, "description": "apple_mail | outlook | smtp (default apple_mail)"},
            "sleep_seconds":{"type": "int",  "required": False, "description": "Delay between sends (default 8)"},
            "dry_run":      {"type": "bool", "required": False, "description": "Preview only, no actual sending (default False)"},
            "send_to_careers":{"type": "bool","required": False,"description": "Also email careers@company when no contact (default False)"},
        },
        "returns": {
            "type": "dict",
            "description": "{'sent': int, 'failed': int, 'skipped': int, 'errors': list}",
        },
        "example": 'run_campaign(sleep_seconds=10, dry_run=True)',
    },

    {
        "name": "list_campaign_runs",
        "category": "Campaign",
        "description": "Return a history of all past campaign runs with stats.",
        "parameters": {
            "limit": {"type": "int",  "required": False, "description": "Max rows (default 20)"},
        },
        "returns": {"type": "list[dict]", "description": "Campaign run records"},
        "example": "list_campaign_runs()",
    },

    # ── Inbox ─────────────────────────────────────────────────────────────────

    {
        "name": "sync_replies",
        "category": "Inbox",
        "description": (
            "Scan the configured inbox (IMAP / Apple Mail / Outlook) for replies, "
            "match them to tracked applications via TKEY, summarise, and classify sentiment."
        ),
        "parameters": {
            "max_emails": {"type": "int",  "required": False, "description": "Max emails to process (default 50)"},
        },
        "returns": {
            "type": "dict",
            "description": "{'new_replies': int, 'classified': int, 'errors': list}",
        },
        "example": "sync_replies()",
    },

    {
        "name": "list_replies",
        "category": "Inbox",
        "description": "Return recent replies with AI summaries and sentiment.",
        "parameters": {
            "limit": {"type": "int",  "required": False, "description": "Max results (default 20)"},
            "app_id":{"type": "str",  "required": False, "description": "Filter to one application"},
        },
        "returns": {"type": "list[dict]", "description": "Reply records with summary and sentiment"},
        "example": "list_replies(limit=10)",
    },

    {
        "name": "get_inbox_emails",
        "category": "Inbox",
        "description": "Fetch raw emails from the inbox (no DB write).",
        "parameters": {
            "max_emails": {"type": "int",  "required": False, "description": "Max to fetch (default 20)"},
            "folder":     {"type": "str",  "required": False, "description": "IMAP folder (default INBOX)"},
        },
        "returns": {"type": "list[dict]", "description": "Email objects: subject, from, date, body snippet"},
        "example": "get_inbox_emails(max_emails=10)",
    },

    # ── Resume ────────────────────────────────────────────────────────────────

    {
        "name": "build_resume",
        "category": "Resume",
        "description": (
            "Generate a tailored resume from a job description using Groq / Mistral. "
            "Produces a DOCX + optional PDF. Returns file path."
        ),
        "parameters": {
            "job_description": {"type": "str",  "required": True,  "description": "Full JD text to tailor the resume for"},
            "output_path":     {"type": "str",  "required": False, "description": "Where to save the file (defaults to Desktop)"},
            "export_pdf":      {"type": "bool", "required": False, "description": "Also export a PDF version (default True)"},
        },
        "returns": {"type": "dict", "description": "{'docx_path': str, 'pdf_path': str|None, 'salary_suggestion': str}"},
        "example": 'build_resume(job_description="Senior PM at Fintech startup...")',
    },

    {
        "name": "get_resume_preview",
        "category": "Resume",
        "description": "Return the current resume content as structured text.",
        "parameters": {},
        "returns": {"type": "str", "description": "Resume text content"},
        "example": "get_resume_preview()",
    },

    # ── Intelligence ──────────────────────────────────────────────────────────

    {
        "name": "ask_ai",
        "category": "Intelligence",
        "description": (
            "Ask the local Mistral 7B model anything — job strategy, email advice, "
            "interview prep, company analysis. Falls back to Groq if local model unavailable."
        ),
        "parameters": {
            "question": {"type": "str",  "required": True,  "description": "Your question or prompt"},
            "context":  {"type": "str",  "required": False, "description": "Optional extra context to include"},
        },
        "returns": {"type": "str", "description": "AI-generated answer"},
        "example": 'ask_ai(question="How should I prepare for a PM interview at a Series B startup?")',
    },

    {
        "name": "analyze_applications",
        "category": "Intelligence",
        "description": (
            "Ask the AI to analyse the application dataset and return insights: "
            "top categories, geographic spread, funding levels, strategy recommendations."
        ),
        "parameters": {
            "focus": {"type": "str",  "required": False, "description": "A specific angle to analyse, e.g. 'why reply rate is low'"},
        },
        "returns": {"type": "str", "description": "Analysis text from AI"},
        "example": 'analyze_applications(focus="which companies are most likely to respond")',
    },

    {
        "name": "summarize_company",
        "category": "Intelligence",
        "description": "Generate a brief 2-3 sentence summary of a company from its application record.",
        "parameters": {
            "app_id": {"type": "str",  "required": True,  "description": "Application UUID"},
        },
        "returns": {"type": "str", "description": "Company summary"},
        "example": 'summarize_company(app_id="abc-123")',
    },

    {
        "name": "extract_contacts_from_text",
        "category": "Intelligence",
        "description": "Extract company names and email contacts from raw text (e.g. pasted from LinkedIn or a website).",
        "parameters": {
            "text": {"type": "str",  "required": True,  "description": "Raw text containing contact info"},
        },
        "returns": {"type": "list[dict]", "description": "[{'company': str, 'email': str, 'name': str}]"},
        "example": 'extract_contacts_from_text(text="John Smith (john@acme.com) is the Head of People at Acme Corp.")',
    },

    # ── Data ──────────────────────────────────────────────────────────────────

    {
        "name": "import_from_excel",
        "category": "Data",
        "description": "Import companies/contacts from a CSV or Excel file into the applications table.",
        "parameters": {
            "file_path":        {"type": "str",  "required": True,  "description": "Absolute path to the CSV or XLSX file"},
            "skip_duplicates":  {"type": "bool", "required": False, "description": "Skip rows where company already exists (default True)"},
        },
        "returns": {
            "type": "dict",
            "description": "{'imported': int, 'skipped': int, 'errors': list}",
        },
        "example": 'import_from_excel(file_path="/Users/me/Desktop/companies.xlsx")',
    },

    {
        "name": "export_to_csv",
        "category": "Data",
        "description": "Export all applications (or a filtered subset) to a CSV file.",
        "parameters": {
            "output_path": {"type": "str",  "required": False, "description": "Output file path (defaults to Desktop/export.csv)"},
            "status":      {"type": "str",  "required": False, "description": "Filter by status"},
        },
        "returns": {"type": "str", "description": "Path to the written CSV file"},
        "example": 'export_to_csv(status="replied")',
    },

    {
        "name": "list_templates",
        "category": "Data",
        "description": "List all saved email templates.",
        "parameters": {},
        "returns": {"type": "list[dict]", "description": "[{'id': int, 'name': str, 'subject': str}]"},
        "example": "list_templates()",
    },

    {
        "name": "save_template",
        "category": "Data",
        "description": "Save or update an email template.",
        "parameters": {
            "name":    {"type": "str",  "required": True,  "description": "Template name"},
            "subject": {"type": "str",  "required": True,  "description": "Subject line (supports {company}, {position}, {contact_name})"},
            "body":    {"type": "str",  "required": True,  "description": "Body text (supports same variables)"},
        },
        "returns": {"type": "bool", "description": "True on success"},
        "example": 'save_template(name="Cold PM", subject="PM role at {company}", body="Hi {contact_name}...")',
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  Manifest helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_ai_manifest() -> dict:
    """
    Return the full tool catalog as a machine-readable manifest.
    AI agents call this first to discover all available capabilities.
    """
    by_category: dict[str, list] = {}
    for schema in TOOL_SCHEMAS:
        cat = schema["category"]
        by_category.setdefault(cat, []).append({
            "name":        schema["name"],
            "description": schema["description"],
            "params":      list(schema["parameters"].keys()),
            "example":     schema.get("example", ""),
        })

    return {
        "system": "JobTracker AI Tools",
        "version": "2.0",
        "total_tools": len(TOOL_SCHEMAS),
        "categories": list(by_category.keys()),
        "tools_by_category": by_category,
        "usage": (
            "Call get_ai_manifest() to see this list. "
            "Call call_tool(name, **kwargs) to execute any tool. "
            "Call get_tool_schema(name) to see full parameter details for a tool."
        ),
    }


def get_tool_schema(name: str) -> dict | None:
    """Return the full schema for one named tool."""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema
    return None


def list_tool_names() -> list[str]:
    """Return just the names of all registered tools."""
    return [s["name"] for s in TOOL_SCHEMAS]


def format_manifest_for_prompt() -> str:
    """
    Format the tool catalog as a readable block for injection into an AI prompt.
    Used by the AI assistant page and the NexusOS graph agent.
    """
    lines = [
        "=== JOBTRACKER AI TOOLS ===",
        f"You have access to {len(TOOL_SCHEMAS)} tools across "
        f"{len({s['category'] for s in TOOL_SCHEMAS})} categories.\n",
    ]
    current_cat = ""
    for s in TOOL_SCHEMAS:
        if s["category"] != current_cat:
            current_cat = s["category"]
            lines.append(f"\n── {current_cat.upper()} ──")
        params = ", ".join(
            f"{k}: {v['type']}{'*' if v.get('required') else '?'}"
            for k, v in s["parameters"].items()
        )
        lines.append(f"  {s['name']}({params})")
        lines.append(f"    → {s['description'][:100]}")
    lines.append("\n(* = required,  ? = optional)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool executor  (thin routing layer — actual logic stays in modules/)
# ─────────────────────────────────────────────────────────────────────────────

def call_tool(name: str, **kwargs) -> Any:
    """
    Execute a tool by name.  Routes to the appropriate module function.
    Returns a Python dict/list/str depending on the tool.
    Raises KeyError if tool not found, ValueError on bad params.
    """
    if name not in list_tool_names():
        raise KeyError(
            f"Unknown tool '{name}'. "
            f"Call get_ai_manifest() to see available tools."
        )

    # ── Applications ─────────────────────────────────────────────────────────
    if name == "add_application":
        from database import get_db
        import uuid as _uuid
        conn = get_db()
        new_id = str(_uuid.uuid4())
        conn.execute(
            "INSERT INTO applications (id, company, position, contact_email, contact_name, notes, status) "
            "VALUES (?,?,?,?,?,?,'pending')",
            (new_id,
             kwargs.get("company", ""),
             kwargs.get("position", ""),
             kwargs.get("contact_email", ""),
             kwargs.get("contact_name", ""),
             kwargs.get("notes", "")),
        )
        conn.commit()
        conn.close()
        return {"id": new_id, "company": kwargs.get("company"), "status": "pending"}

    if name == "get_application":
        from database import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (kwargs["app_id"],)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    if name == "list_applications":
        from database import get_db
        conn = get_db()
        clauses, params = [], []
        if kwargs.get("status"):
            clauses.append("status=?")
            params.append(kwargs["status"])
        if kwargs.get("query"):
            q = f"%{kwargs['query']}%"
            clauses.append(
                "(company LIKE ? OR position LIKE ? OR notes LIKE ? OR contact_email LIKE ?)"
            )
            params.extend([q, q, q, q])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        limit = kwargs.get("limit", 50)
        rows  = conn.execute(
            f"SELECT * FROM applications {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    if name == "update_application_status":
        from database import get_db
        conn = get_db()
        conn.execute(
            "UPDATE applications SET status=? WHERE id=?",
            (kwargs["status"], kwargs["app_id"]),
        )
        conn.commit()
        conn.close()
        return True

    if name == "update_application_notes":
        from database import get_db
        conn = get_db()
        conn.execute(
            "UPDATE applications SET notes=? WHERE id=?",
            (kwargs["notes"], kwargs["app_id"]),
        )
        conn.commit()
        conn.close()
        return True

    if name == "delete_application":
        from database import get_db
        conn = get_db()
        conn.execute("DELETE FROM applications WHERE id=?", (kwargs["app_id"],))
        conn.commit()
        conn.close()
        return True

    if name == "search_applications":
        return call_tool(
            "list_applications",
            query=kwargs["query"],
            limit=kwargs.get("limit", 30),
        )

    if name == "get_dashboard_stats":
        from database import get_db
        conn = get_db()
        total     = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0]
        sent      = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('sent','replied','interview','offer','rejected')").fetchone()[0]
        replied   = conn.execute("SELECT COUNT(*) FROM applications WHERE status='replied'").fetchone()[0]
        interview = conn.execute("SELECT COUNT(*) FROM applications WHERE status='interview'").fetchone()[0]
        offer     = conn.execute("SELECT COUNT(*) FROM applications WHERE status='offer'").fetchone()[0]
        conn.close()
        rate = f"{round(replied / sent * 100, 1)}%" if sent else "0%"
        return {
            "total": total, "pending": pending, "sent": sent,
            "replied": replied, "interview": interview, "offer": offer,
            "reply_rate": rate,
        }

    # ── Email ─────────────────────────────────────────────────────────────────
    if name == "send_email":
        from modules.quick_mailer import quick_send_email
        return quick_send_email(
            app_id=kwargs["app_id"],
            subject=kwargs.get("subject"),
            body=kwargs.get("body"),
            dry_run=kwargs.get("dry_run", False),
        )

    if name == "generate_email_draft":
        from modules.groq_client import draft_single_email
        from database import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (kwargs["app_id"],)
        ).fetchone()
        conn.close()
        if not row:
            raise ValueError(f"Application {kwargs['app_id']} not found")
        app = dict(row)
        result = draft_single_email(
            company=app.get("company", ""),
            position=app.get("position", ""),
            notes=app.get("notes", "") + (" " + kwargs.get("instructions", "")),
        )
        return result

    if name == "generate_reply_draft":
        from modules.groq_client import generate_reply_draft
        return generate_reply_draft(
            email_body=kwargs["email_body"],
            company=kwargs.get("company", ""),
            tone=kwargs.get("tone", "professional"),
        )

    if name == "schedule_email":
        from modules.scheduler import schedule_email as _sched
        return _sched(
            app_id=kwargs["app_id"],
            scheduled_at=kwargs["scheduled_at"],
            subject=kwargs.get("subject"),
            body=kwargs.get("body"),
        )

    # ── Campaign ──────────────────────────────────────────────────────────────
    if name == "run_campaign":
        from modules.apple_mail_sender import run_bulk_campaign
        app_ids = kwargs.get("app_ids")
        if not app_ids:
            from database import get_db
            conn = get_db()
            rows = conn.execute(
                "SELECT id FROM applications WHERE status='pending'"
            ).fetchall()
            conn.close()
            app_ids = [r[0] for r in rows]
        return run_bulk_campaign(
            app_ids=app_ids,
            sleep_seconds=kwargs.get("sleep_seconds", 8),
            dry_run=kwargs.get("dry_run", False),
            send_to_careers=kwargs.get("send_to_careers", False),
        )

    if name == "list_campaign_runs":
        from database import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM campaign_runs ORDER BY id DESC LIMIT ?",
            (kwargs.get("limit", 20),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Inbox ─────────────────────────────────────────────────────────────────
    if name == "sync_replies":
        from modules.email_monitor import sync_inbox
        return sync_inbox(max_emails=kwargs.get("max_emails", 50))

    if name == "list_replies":
        from database import get_db
        conn = get_db()
        clauses, params = [], []
        if kwargs.get("app_id"):
            clauses.append("application_id=?")
            params.append(kwargs["app_id"])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        limit = kwargs.get("limit", 20)
        rows  = conn.execute(
            f"SELECT r.*, a.company, a.position FROM replies r "
            f"LEFT JOIN applications a ON r.application_id=a.id "
            f"{where} ORDER BY r.received_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    if name == "get_inbox_emails":
        from modules.mail_client import fetch_emails
        return fetch_emails(
            max_emails=kwargs.get("max_emails", 20),
            folder=kwargs.get("folder", "INBOX"),
        )

    # ── Resume ────────────────────────────────────────────────────────────────
    if name == "build_resume":
        from resume_builder.generator import build_resume_pdf
        return build_resume_pdf(
            job_description=kwargs["job_description"],
            output_path=kwargs.get("output_path"),
            export_pdf=kwargs.get("export_pdf", True),
        )

    if name == "get_resume_preview":
        from modules.llm_summarizer import _get_llm
        path = None
        try:
            from database import get_setting
            path = get_setting("resume_path", "")
        except Exception:
            pass
        if path:
            try:
                from docx import Document
                doc = Document(path)
                return "\n".join(p.text for p in doc.paragraphs)
            except Exception as e:
                return f"(could not read resume: {e})"
        return "(no resume configured — set path in Settings)"

    # ── Intelligence ──────────────────────────────────────────────────────────
    if name == "ask_ai":
        from modules.llm_summarizer import ask as _ask_llm
        ctx = kwargs.get("context", "")
        q   = kwargs["question"]
        return _ask_llm(f"{ctx}\n\n{q}" if ctx else q)

    if name == "analyze_applications":
        import json
        from database import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT company, status, raw_data FROM applications ORDER BY id LIMIT 120"
        ).fetchall()
        conn.close()
        lines = []
        for co, st, raw in rows:
            parts = [f"Company: {co}"]
            if raw:
                try:
                    d = json.loads(raw)
                    for k in ("city", "country", "categories", "total_funding_usd"):
                        if d.get(k):
                            parts.append(f"{k}: {d[k]}")
                except Exception:
                    pass
            parts.append(f"status: {st}")
            lines.append(" | ".join(parts))
        focus = kwargs.get("focus", "")
        question = f"Analyse this job application dataset{' focusing on: ' + focus if focus else ''}.\n\n" + "\n".join(lines[:80])
        return call_tool("ask_ai", question=question)

    if name == "summarize_company":
        from database import get_db
        import json
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (kwargs["app_id"],)
        ).fetchone()
        conn.close()
        if not row:
            return "Application not found."
        app = dict(row)
        ctx = f"Company: {app.get('company')}, Position: {app.get('position')}, "
        if app.get("raw_data"):
            try:
                d = json.loads(app["raw_data"])
                ctx += f"City: {d.get('city','')}, Categories: {d.get('categories','')[:60]}, "
                ctx += f"Funding: {d.get('total_funding_usd','')}, About: {d.get('short_description','')[:120]}"
            except Exception:
                pass
        return call_tool("ask_ai", question=f"Write a 2-sentence summary of this company: {ctx}")

    if name == "extract_contacts_from_text":
        from modules.groq_client import extract_contacts
        return extract_contacts(kwargs["text"])

    # ── Data ──────────────────────────────────────────────────────────────────
    if name == "import_from_excel":
        from modules.excel_processor import import_excel
        return import_excel(
            file_path=kwargs["file_path"],
            skip_duplicates=kwargs.get("skip_duplicates", True),
        )

    if name == "export_to_csv":
        import csv, os
        from database import get_db
        out = kwargs.get("output_path") or os.path.expanduser("~/Desktop/applications_export.csv")
        conn = get_db()
        clauses, params = [], []
        if kwargs.get("status"):
            clauses.append("status=?")
            params.append(kwargs["status"])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(f"SELECT * FROM applications {where}").fetchall()
        conn.close()
        if rows:
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows([dict(r) for r in rows])
        return out

    if name == "list_templates":
        from database import get_db
        conn = get_db()
        rows = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    if name == "save_template":
        from database import get_db
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM templates WHERE name=?", (kwargs["name"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE templates SET subject=?, body=? WHERE name=?",
                (kwargs["subject"], kwargs["body"], kwargs["name"]),
            )
        else:
            conn.execute(
                "INSERT INTO templates (name, subject, body) VALUES (?,?,?)",
                (kwargs["name"], kwargs["subject"], kwargs["body"]),
            )
        conn.commit()
        conn.close()
        return True

    raise RuntimeError(f"Tool '{name}' has a schema but no executor — this is a bug.")
