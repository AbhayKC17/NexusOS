import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'tracker.db')

# Settings cache — avoids hitting SQLite for every get_setting() call
_settings_cache: dict | None = None


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -8000")   # 8 MB page cache
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS applications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid        TEXT    UNIQUE NOT NULL,
            company     TEXT,
            position    TEXT,
            contact_email TEXT,
            contact_name  TEXT,
            status      TEXT    DEFAULT 'pending',
            applied_date TEXT,
            email_subject TEXT,
            email_body    TEXT,
            sent_at       TEXT,
            source_file   TEXT,
            notes         TEXT,
            tkey          TEXT,
            created_at    TEXT   DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS inbox_index (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            message_uid     TEXT    UNIQUE,
            from_email      TEXT,
            subject         TEXT,
            body            TEXT,
            received_at     TEXT,
            tkey            TEXT,
            application_id  INTEGER,
            ai_reply_draft  TEXT,
            reply_status    TEXT    DEFAULT 'pending',
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS replies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER,
            uuid            TEXT,
            received_at     TEXT,
            from_email      TEXT,
            from_name       TEXT,
            subject         TEXT,
            body            TEXT,
            summary         TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (application_id) REFERENCES applications(id)
        );

        CREATE TABLE IF NOT EXISTS scheduled_emails (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER,
            scheduled_at    TEXT,
            status          TEXT DEFAULT 'pending',
            email_subject   TEXT,
            email_body      TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (application_id) REFERENCES applications(id)
        );

        CREATE TABLE IF NOT EXISTS templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            subject     TEXT,
            body        TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS campaign_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT,
            sender_mode         TEXT    DEFAULT 'apple_mail',
            apple_mail_account  TEXT    DEFAULT '',
            sleep_seconds       INTEGER DEFAULT 10,
            send_to_careers     INTEGER DEFAULT 1,
            dry_run             INTEGER DEFAULT 0,
            status              TEXT    DEFAULT 'pending',
            sent                INTEGER DEFAULT 0,
            failed              INTEGER DEFAULT 0,
            skipped             INTEGER DEFAULT 0,
            errors              TEXT    DEFAULT '[]',
            created_at          TEXT    DEFAULT (datetime('now')),
            started_at          TEXT,
            completed_at        TEXT
        );
    ''')

    # seed default templates
    existing = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    if existing == 0:
        conn.execute('''
            INSERT INTO templates (name, subject, body) VALUES (
                'Standard Job Application',
                'Application for {position} at {company}',
                'Dear {contact_name},\n\nI am writing to express my strong interest in the {position} role at {company}.\n\nBriefly, I bring:\n• [Key skill 1]\n• [Key skill 2]\n• [Key skill 3]\n\nI would love the opportunity to discuss how my background aligns with your team''s needs. I have attached my resume for your review.\n\nThank you for your time and consideration.\n\nBest regards,\n[Your Name]'
            )
        ''')
    conn.commit()

    # Migrations — safe to run on existing DBs
    for ddl in [
        "ALTER TABLE applications ADD COLUMN raw_data TEXT",
        "ALTER TABLE applications ADD COLUMN extra_columns TEXT",
        "ALTER TABLE applications ADD COLUMN tkey TEXT",
        "ALTER TABLE applications ADD COLUMN campaign_run_id INTEGER",
        "ALTER TABLE campaign_runs ADD COLUMN target_ids TEXT DEFAULT '[]'",
        """CREATE TABLE IF NOT EXISTS inbox_index (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            message_uid     TEXT    UNIQUE,
            from_email      TEXT,
            subject         TEXT,
            body            TEXT,
            received_at     TEXT,
            tkey            TEXT,
            application_id  INTEGER,
            ai_reply_draft  TEXT,
            reply_status    TEXT    DEFAULT 'pending',
            created_at      TEXT    DEFAULT (datetime('now'))
        )""",
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass

    conn.close()


def subject_to_tracking_key(subject: str) -> str:
    """Convert a subject line to a unique 14-digit numeric tracking key (SHA-256 based)."""
    import hashlib
    h = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return str(int(h, 16) % (10 ** 14)).zfill(14)


def get_setting(key, default=None):
    global _settings_cache
    if _settings_cache is None:
        # Load all settings at once into cache
        try:
            conn = get_db()
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            conn.close()
            _settings_cache = {r["key"]: r["value"] for r in rows}
        except Exception:
            _settings_cache = {}
    return _settings_cache.get(key, default)


def set_setting(key, value):
    global _settings_cache
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    # Invalidate cache so next get_setting() reflects the update
    if _settings_cache is not None:
        _settings_cache[key] = value
