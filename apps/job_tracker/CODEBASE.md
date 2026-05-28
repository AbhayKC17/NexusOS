# JobTracker — Complete Codebase Reference

> One file to understand the entire project.  
> Read this top-to-bottom once and you will never need to grep the codebase for context again.

---

## 1. What This App Does

JobTracker is a **macOS desktop app** (PyQt6) that automates the entire job-application workflow:

| Stage | Feature |
|-------|---------|
| Collect | Import companies from Excel / add manually |
| Draft | AI-generated personalized intro emails (Mistral 7B) |
| Send | Bulk Apple Mail sender with invisible tracking keys |
| Track | UUID + SHA-256 tracking key embedded in every sent email |
| Detect | IMAP / Apple Mail / Outlook monitors for replies |
| Reply | AI auto-draft replies (Mistral 7B) |
| Resume | JD → AI-tailored resume → direct PDF edit → export |

---

## 2. Architecture — Bird's-Eye View

```
desktop_app.py          ← entry point (QApplication + splash + init_db)
     │
     ├── database.py                ← SQLite3 I/O, settings KV, tracking-key util
     │
     ├── ui/
     │   ├── style.py               ← Single QSS stylesheet (Nova Dark theme)
     │   ├── main_window.py         ← QMainWindow + sidebar nav + page stack
     │   ├── workers.py             ← All QThread background workers (14 total)
     │   └── pages/
     │       ├── dashboard.py       ← Stats, AI search, quick actions
     │       ├── applications.py    ← Application CRUD table
     │       ├── spreadsheet.py     ← Editable Excel-like grid
     │       ├── campaign.py        ← Bulk email sender UI
     │       ├── mail.py            ← Built-in IMAP mail client
     │       ├── replies.py         ← AI draft cards + tracked reply cards
     │       ├── assistant.py       ← Chat with local Mistral 7B
     │       ├── resume_builder.py  ← JD → tailored resume → PDF export
     │       └── settings.py        ← All config, OAuth, LLM loader
     │
     └── modules/
         ├── llm_summarizer.py      ← LLM singleton wrapper (_get_llm / _llm)
         ├── llm_auto_reply.py      ← generate_reply_draft(), get_fallback_draft()
         ├── resume_generator.py    ← Mistral prompt, parse, PDF edit, DOCX edit
         ├── oauth_manager.py       ← Google + Microsoft OAuth2 browser flows
         ├── email_monitor.py       ← Reply-sync dispatcher (routes to backends)
         ├── apple_mail_reader.py   ← AppleScript INBOX reader backend
         ├── outlook_reader.py      ← MS Graph INBOX reader backend
         ├── mail_client.py         ← Generic IMAP fetch + SMTP send
         ├── email_sender.py        ← Tracked SMTP send (TRK-UUID in subject)
         ├── apple_mail_sender.py   ← AppleScript bulk sender + HTML builder
         ├── outlook_sender.py      ← Outlook / MS Graph sender
         ├── ms_graph.py            ← Microsoft Graph API client
         ├── excel_processor.py     ← Pandas import, raw_data JSON
         └── scheduler.py           ← APScheduler wrapper (background tasks)
```

---

## 3. Entry Point — `desktop_app.py`

**Purpose:** Bootstrap the Qt application.

**Startup sequence:**
1. `QApplication` created; `FLUENT_DARK` stylesheet applied globally
2. `init_db()` — creates SQLite tables, runs migrations, seeds default templates
3. Auto-detect Mistral model path → write to `settings` table if not already set
4. Splash screen shown (580×280 px, painted with QPainter)
5. `MainWindow` constructed and shown; splash closes after 1.6 s
6. 400 ms after window shows → `_auto_load_model()` loads Mistral in background

**Key constant:** `default_model = ".../mistral-7b-instruct-v0.2.Q4_K_M.gguf"` — hardcoded but overridable via Settings page.

---

## 4. Database — `database.py`

**Engine:** SQLite3, file at `JobTracker/data/tracker.db`

### Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `applications` | One row per job application | `uuid`, `company`, `position`, `contact_email`, `status`, `tkey`, `sent_at` |
| `inbox_index` | Indexed inbox messages | `message_uid`, `tkey`, `application_id`, `ai_reply_draft`, `reply_status` |
| `replies` | Legacy reply store | `application_id`, `uuid`, `body`, `summary` |
| `scheduled_emails` | Queued sends | `application_id`, `scheduled_at`, `status` |
| `templates` | Email templates | `name`, `subject`, `body` (supports `{company}`, `{position}`, `{contact_name}` placeholders) |
| `settings` | Key-value config store | `key`, `value` (TEXT) |

### Public API

```python
get_db()                              # → sqlite3.Connection (row_factory = Row)
init_db()                             # create schema + migrations + seed templates
get_setting(key, default=None)        # → str or default
set_setting(key, value)               # upsert into settings table
subject_to_tracking_key(subject: str) # → 14-digit numeric string (SHA-256)
```

### Migrations

Safe `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` run every startup inside a try/except — won't fail on existing DBs.

---

## 5. UI Layer

### 5.1 Theme — `ui/style.py`

Single QSS string `FLUENT_DARK` applied at app startup via `app.setStyleSheet()`.

**Color palette:**

| Token | Hex | Use |
|-------|-----|-----|
| Background | `#0D0D10` | Main window, all pages |
| Surface L1 | `#13131A` | Cards, tables |
| Surface L2 | `#1A1A24` | Elevated cards, inputs |
| Sidebar | `#090910` | Left nav panel |
| Accent | `#6366F1` | Buttons, active nav, focus rings |
| Accent hover | `#7578F3` | Button hover state |
| Text | `#EFEFEF` | Primary text |
| Text muted | `rgba(239,239,239,0.42)` | Labels, subtitles |
| Danger | `#FCA5A5` / `rgba(239,68,68,*)` | Delete buttons, errors |

**Named object IDs used for styling (set via `setObjectName()`):**

| ID | Widget type | Description |
|----|-------------|-------------|
| `sidebar` | QFrame | Left navigation panel |
| `appTitle` | QLabel | App name "✦ JobTracker" |
| `appSubtitle` | QLabel | Subtitle under app name |
| `navBtn` | QPushButton | Navigation buttons (has `active` property) |
| `pageHeader` | QWidget | Top header area of each page |
| `pageTitle` | QLabel | Page heading (20px bold) |
| `pageSubtitle` | QLabel | Page description (12px muted) |
| `card` | QFrame | Standard content card |
| `cardElevated` | QFrame | Highlighted/nested card |
| `statCard` | QFrame | Dashboard stat card |
| `statNumber` | QLabel | Large number in stat card (28px bold) |
| `statDesc` | QLabel | Label below stat number |
| `sectionHeader` | QLabel | ALL-CAPS section label |
| `sectionTitle` | QLabel | Alias of sectionHeader |
| `accentBtn` | QPushButton | Indigo primary action button |
| `dangerBtn` | QPushButton | Red destructive action button |
| `subtleBtn` | QPushButton | Ghost/text button |

**Status badge colours** (`STATUS_STYLE` dict — `{status: (text_color, bg_css)}`):

| Status | Color |
|--------|-------|
| `pending` | Amber `rgba(251,191,36,*)` |
| `sent` | Indigo `rgba(129,140,248,*)` |
| `replied` | Green `rgba(52,211,153,*)` |
| `rejected` | Red `rgba(252,165,165,*)` |
| `offer` | Purple `rgba(196,181,253,*)` |
| `interview` | Cyan `rgba(103,232,249,*)` |

---

### 5.2 Main Window — `ui/main_window.py`

**Class:** `MainWindow(QMainWindow)`

**Sidebar nav** — 9 items mapped to `QStackedWidget` index:

| Index | Label | Page class |
|-------|-------|------------|
| 0 | Overview | `DashboardPage` |
| 1 | Applications | `ApplicationsPage` |
| 2 | Data | `SpreadsheetPage` |
| 3 | Campaign | `CampaignPage` |
| 4 | Mail | `MailPage` |
| 5 | Replies | `RepliesPage` |
| 6 | AI Assistant | `AssistantPage` |
| 7 | Resume | `ResumePage` |
| 8 | Settings | `SettingsPage` |

**Key behaviours:**
- `_nav(idx)` — switches page; calls `page.refresh()` if the method exists
- `_auto_load_model()` — fires 400 ms after show; reads `llm_model_path` from settings, starts `LLMLoaderWorker`
- `_auto_sync()` — fires every 15 min via QTimer; starts `EmailSyncWorker`
- `_compose(app_id)` — opens `ComposeDialog` (inline class in same file)

**Sidebar footer indicators:**
- `modelDot` — "Loading…" (yellow) → "Mistral 7B ready" (green) → "Model failed" (red)
- `syncDot` — shows last sync result

---

### 5.3 Background Workers — `ui/workers.py`

All workers are `QThread` subclasses. Pattern:
- Emit `done` signal (never shadow `finished`) with result data
- Emit `error` signal with string message on failure
- Connect `finished` to `deleteLater()` via `_connect_cleanup()`
- Caller must hold a strong reference (`self._worker = ...`) until `finished`

| Worker | Signals | What it does |
|--------|---------|-------------|
| `LLMLoaderWorker` | `done(bool, str)` | Loads Mistral GGUF via llama-cpp-python |
| `LLMInferenceWorker` | `done(str)`, `error(str)` | Single LLM inference call |
| `EmailSyncWorker` | `done(int, list)` | Calls `sync_replies()` dispatcher |
| `BulkSendWorker` | `progress(int,str,str)`, `done(dict)` | Apple Mail bulk campaign |
| `MailFetchWorker` | `done(list)`, `error(str)` | IMAP folder fetch |
| `MailBodyWorker` | `done(dict)`, `error(str)` | IMAP single message body |
| `MailSendWorker` | `done()`, `error(str)` | SMTP send via mail_client |
| `MsGraphAuthWorker` | `done(str)`, `error(str)` | MS device-flow token acquire |
| `OAuthWorker` | `done(str)`, `error(str)` | Browser OAuth2 (Google or MS) |
| `DraftRegenWorker` | `done(int,str)`, `error(int,str)` | Regenerate AI reply draft |
| `ResumeWorker` | `done(dict)`, `error(str)` | LLM resume content generation |
| `ResumeExportWorker` | `done(str)`, `error(str)` | PDF or DOCX resume export |
| `ExcelImportWorker` | `done(dict)` | Excel → DB via excel_processor |
| `InboxIndexWorker` | `done(dict)` | Full inbox re-index |

---

### 5.4 Pages

#### `dashboard.py` — Overview
- Shows 6 stat cards: Total, Sent, Replied, Pending, Interview, Offer
- Graph RAG semantic search: embeds application text → cosine similarity → top-5 results
- AI Insights: Mistral 7B answers "what's working / what's not" based on data
- Quick-action buttons trigger navigation to other pages

#### `applications.py` — Application CRUD
- QTableWidget with columns: Company, Position, Contact Email, Status, Date
- Add / Edit / Delete actions
- Compose button → emits `compose_requested(app_id)` → MainWindow opens ComposeDialog
- Refresh reads all rows from `applications` table

#### `spreadsheet.py` — Editable Grid
- Full editable QTableWidget mirroring all `applications` columns
- Inline cell edit → immediate DB write on `cellChanged`
- Status dropdown per row; displays extra_columns JSON

#### `campaign.py` — Bulk Sender
- Checkbox-selects applications → starts `BulkSendWorker`
- Options: sleep between sends (default 10 s), dry-run, send-to-careers toggle
- Progress shown per application row
- LLM intro generation via `generate_personalized_intro()` from apple_mail_sender

#### `mail.py` — Built-in IMAP Client
- 3-panel layout: folder list | message list | message view / compose
- Fetch via `MailFetchWorker` → `MailBodyWorker` for body
- Compose panel: to/subject/body + tracking key toggle
- Tracking key = `subject_to_tracking_key(subject)` (from database.py)

#### `replies.py` — AI Drafts + Tracked Replies
- Two sections: `inbox_index` rows (AI draft cards) + `replies` rows (legacy)
- Draft cards show: sender, subject, AI draft, "Send Reply" / "Regenerate" buttons
- Regenerate → `DraftRegenWorker` → updates `ai_reply_draft` in DB

#### `assistant.py` — AI Chat
- Simple chat UI: user message → `LLMInferenceWorker` → response displayed
- System context: includes application stats from DB

#### `resume_builder.py` — Resume Builder
**Layout:** Left (JD input + Generate) | Right (fields: salary, summary, 3×bullets, skills) | Bottom (company name + template select + export)

**Key behaviours:**
- `_auto_extract_company()` — debounced 600 ms after typing; calls `extract_company_from_jd()`
- `_generate()` → `ResumeWorker` → `generate_resume_content()` + `parse_llm_output()` → populates all right-panel fields
- `_export()` → `ResumeExportWorker` → `apply_to_pdf()` (PDF template) or `apply_to_docx()` + `export_pdf()` (DOCX)
- `_DEFAULT_PDF` = `Abhay_Resume.pdf` four directory levels up from this file
- `refresh()` — always switches `resume_path` setting to PDF if `_DEFAULT_PDF` exists

**Char counter:** Summary label turns green at 270–310 chars, yellow at 250–330.

#### `settings.py` — Configuration
- Tabs: Email Account | LLM | Campaign | Templates | About
- Google OAuth: `OAuthWorker(provider="google")` → `google_connect()`
- Microsoft OAuth: `OAuthWorker(provider="microsoft")` → `ms_connect()`
- LLM: manual path input OR auto-detect; "Load Now" → `LLMLoaderWorker`
- All values persisted to `settings` table via `set_setting()`

---

## 6. Modules (Business Logic)

### 6.1 LLM Integration

#### `modules/llm_summarizer.py`
Singleton wrapper around `llama_cpp.Llama`.

```python
_llm = None                  # module-level singleton, set by LLMLoaderWorker

def _get_llm():              # returns _llm or None
def _load_llm(path, n_ctx, n_gpu_layers)   # direct load (blocking)
```

**Loaded by:** `LLMLoaderWorker` in `ui/workers.py`  
**Used by:** `LLMInferenceWorker`, `resume_generator`, `llm_auto_reply`, `apple_mail_sender`

#### `modules/llm_auto_reply.py`
Generates AI reply drafts for inbox messages.

```python
generate_reply_draft(reply_body, original_subject, original_body, company_name, position)
    # → str draft, or None if LLM not loaded

get_fallback_draft(company_name, position)
    # → polished template string (no LLM required)
```

**Called by:** `DraftRegenWorker` in `ui/workers.py`

---

### 6.2 Resume Pipeline — `modules/resume_generator.py`

The heaviest module. Four separate concerns:

#### A. LLM Content Generation
```python
MASTER_PROMPT    # structured prompt with == SALARY == / == SUMMARY == / == EXPERIENCE == / == SKILLS ==

generate_resume_content(job_description: str) → str
    # Runs Mistral 7B with MASTER_PROMPT + JD. Returns raw text.
```

**Prompt rules:**
- Summary: 270–310 chars (ABSOLUTE HARD RULE), no cliché words, verb+number bursts; fits 3-line Cambria 10.0pt layout
- Bullets: HARD LIMIT ≤85 chars each; plain text lines (no numbers, no bullet symbols in prompt); PDF export inserts ● (ArialMT) at x=126.25 + text (Cambria) at x=139.75 matching original template
- Skills: comma lists by category from JD keywords only

#### B. Parsing
```python
parse_llm_output(text: str) → dict
    # Returns: {raw, salary, summary, bullets: {projects, ecolab, msc}, skills}
    # Handles both == SECTION == and old "Section: " formats as fallback
    # Truncates each bullet to 85 chars at parse time
```

Internal helpers:
- `_extract_bullet_groups_labeled(work_text)` → `[(header, [bullets]), ...]`
- Company router: "ecolab"/"associate planner" → ecolab; "mediterranean"/"msc" → msc; first other → projects

#### C. Company Name Extraction
```python
extract_company_from_jd(jd_text: str) → str
    # Heuristic: checks "About <Name>", "Company:", "join <Name>", "Name — Title", standalone short line
```

#### D. PDF Direct Editing (`apply_to_pdf`)

Layout constants for `Abhay_Resume.pdf` (measured via PyMuPDF rawdict):

```
_CAMBRIA = "/F9"    # Cambria regular — summary text + bullet text (identical to original)
_ARIAL   = "/F11"   # ArialMT         — ● bullet glyph only
_BULLET_MAX_CHARS = 85

_PDF_SUMMARY (hardcoded in apply_to_pdf):
  erase rect = (119.0, 91.0, 596.0, 144.0)   — y2=144 stops before blue separator at y=146
  tbox       = (126.25, 96.0, 594.0, 144.0)   — x0=126.25 aligns with bullet-dot column
                                                  (3pt right of name x=123.25); y0=96 → first
                                                  baseline at y≈104
  fontsize=10.0pt, lineheight=1.477           — 14.77/10.0 preserves original absolute spacing
                                                  3 lines fit; 4th clips at y=144

_PDF_BULLETS:
  projects  baselines=[202.91,220.50,238.09,255.67]  erase=(121,192,596,259)
  ecolab    baselines=[319.05,336.64,354.22,371.81]  erase=(121,309,596,375)
  msc       baselines=[431.06,448.64,466.23]           erase=(121,421,596,470)
  ● (ArialMT /F11) x=126.25,  text (Cambria /F9) x=139.75
```

**PDF edit steps:**
1. `add_redact_annot()` marks erase regions (white fill) for each changed section
2. `apply_redactions()` physically strips old text from content stream
3. `insert_textbox(Cambria 10.5pt)` inserts summary — same font/size/position as original template
4. `insert_text(ArialMT)` inserts ● at x=126.25; `insert_text(Cambria)` inserts plain text at x=139.75

#### E. DOCX Editing (`apply_to_docx`)
Uses `python-docx` + lxml XML manipulation.

```
Table structure (doc.tables[0]):
  R1: job title row "Digital Supply Chain Consultant | Infyair"  ← has "|", skipped
  R2: sub-header "Independent Projects - Digital Supply Chain"   ← matched as "projects"
  R3: 4 bullet paragraphs (C1+C2, merged cell deduped)
  R4: job title row "Associate Planner | Ecolab"                 ← skipped
  R5: sub-header "ECOLAB - Chemical Manufacturing"               ← matched as "ecolab"
  R6: 4 bullet paragraphs
  R7: job title row "Executive Assistant | MSC"                   ← skipped
  R8: sub-header "MSC - Mediterranean Shipping Company"          ← matched as "msc"
  R9: 3 bullet paragraphs
```

Key DOCX helpers:
- `_replace_para_text(para, text)` — rewrites paragraph via XML, preserves `rPr` formatting
- `_replace_table_bullets(table, bullets_dict)` — finds sub-header rows (no "|"), replaces next row's bullets
- `_remove_inter_table_blanks(doc, t1, t2)` — removes empty `<w:p>` between two tables

---

### 6.3 Email Sending

#### `modules/apple_mail_sender.py`
Primary sending mechanism (macOS only).

```python
send_via_apple_mail(to_emails, subject, body, resume_path, tracking_key)
    # HTML body written to temp file → AppleScript reads file → Mail.app sends

generate_personalized_intro(company_name, short_desc, ...)
    # Uses Mistral 7B to write 1-sentence personalized opening

build_email_body(company_name, intro)
    # Assembles full email from profile settings + intro

run_bulk_campaign(application_ids, sleep_seconds, dry_run, send_to_careers, sender_mode, progress_callback)
    # Main bulk-send loop: fetches app data → builds email → sends → updates DB status
```

Tracking key embedded as invisible `<span>` in HTML (`TKEY:{key}`) — 1px opacity, undetectable to reader, detectable by AI/regex.

#### `modules/email_sender.py`
SMTP tracked send (alternative to Apple Mail).

```python
send_tracked_email(application_id, subject, body_plain, body_html, attachments)
    # Embeds TRK-{uuid} in subject line + invisible div in HTML body
    # Updates application status → 'sent' after successful send
```

#### `modules/outlook_sender.py`
Outlook / MS Graph send (used when sender_mode = "outlook").

---

### 6.4 Email Receiving / Sync

#### `modules/email_monitor.py` — Dispatcher

```python
sync_replies() → {"new_replies": int, "errors": list}
    # Routes to the correct backend based on settings:
    #   google_connected  → sync_replies_gmail()
    #   ms_connected      → sync_replies_outlook()
    #   apple_mail        → sync_replies_apple_mail()
    #   fallback          → sync_replies_imap()

index_all_inbox() → {"indexed": int, "tkey_matches": int, "errors": list}
    # Scans all inbox messages, writes to inbox_index table
```

#### `modules/apple_mail_reader.py`
AppleScript-based reader — scans Apple Mail inbox, matches tracking keys.

#### `modules/outlook_reader.py`
MS Graph API reader — fetches messages from Outlook/Exchange mailbox.

#### `modules/mail_client.py`
Generic IMAP/SMTP client.

```python
fetch_messages(folder, limit) → list[dict]    # IMAP message list
fetch_body(uid, folder) → dict                # single message full body
send_email(to_emails, subject, body, attachment_path, tracking_key)  # SMTP send
```

Uses settings: `imap_host`, `imap_port`, `imap_user`, `imap_pass`, `smtp_host`, `smtp_port`, etc.

---

### 6.5 OAuth — `modules/oauth_manager.py`

Browser-based OAuth2 Authorization Code flow (not device code).

```
Flow:
  1. Build auth URL (Google/Microsoft login page)
  2. Open in default browser via webbrowser.open()
  3. Local HTTP server on port 8741 catches /callback redirect
  4. Extract code from URL params
  5. Exchange code for access + refresh tokens
  6. Store tokens to data/oauth_{provider}.json
```

**Google (bundled credentials):**
```python
google_connect()        # full browser flow → returns email
get_google_token()      # valid token; auto-refreshes if expired
is_google_connected()   # bool
google_disconnect()     # deletes oauth_google.json
```

**Microsoft:**
```python
ms_connect(client_id)   # full browser flow → returns email
get_ms_token()          # valid token; auto-refreshes
is_ms_connected()       # bool
ms_disconnect()         # deletes oauth_microsoft.json
```

Token files: `JobTracker/data/oauth_google.json`, `oauth_microsoft.json`  
Token schema: `{access_token, refresh_token, expires_at, email}`

---

### 6.6 Microsoft Graph — `modules/ms_graph.py`

REST calls against `https://graph.microsoft.com/v1.0/`.

```python
complete_device_flow(flow)     # completes MSAL device code flow (legacy path)
get_messages(folder, limit)    # list inbox/folder messages
get_message_body(message_id)   # full message with body
send_message(to, subject, body, attachment_path)   # send via Graph API
```

Uses `get_ms_token()` from oauth_manager for every request.

---

### 6.7 Excel Import — `modules/excel_processor.py`

```python
process_excel(filepath, filename) → {"imported": int, "duplicates_skipped": int, ...}
    # Reads Excel/CSV with pandas
    # Maps columns: company, position, contact_email, contact_name, notes
    # Skips rows where uuid already exists in DB
    # Stores unmapped columns as raw_data JSON
```

---

## 7. Data Flow Diagrams

### 7.1 Application Status Lifecycle

```
[Imported from Excel / Added manually]
        ↓
     pending
        ↓ (BulkSendWorker / ComposeDialog)
      sent  ←─── tracking key (tkey) embedded in email subject
        ↓ (EmailSyncWorker detects reply)
    replied
        ↓ (human decision)
   interview | rejected | offer
```

### 7.2 Bulk Email Send Flow

```
CampaignPage._send()
  └── BulkSendWorker.run()
        └── run_bulk_campaign(app_ids, ...)           [apple_mail_sender.py]
              for each app:
                1. get_db() → fetch application row
                2. generate_personalized_intro()       [Mistral 7B]
                3. build_email_body()                  [profile settings]
                4. tkey = _subject_to_key(subject)     [database.py]
                5. send_via_apple_mail(...)            [AppleScript]
                6. UPDATE applications SET status='sent', tkey=?
                7. progress_callback(app_id, company, status)
              → done.emit({"sent": N, "errors": [...]})
```

### 7.3 Reply Detection Flow

```
QTimer (15 min) → EmailSyncWorker.run()
  └── sync_replies()                                   [email_monitor.py]
        ├── if google:  sync_replies_gmail()
        ├── if outlook: sync_replies_outlook()         [outlook_reader.py]
        ├── if apple:   sync_replies_apple_mail()      [apple_mail_reader.py]
        └── fallback:   sync_replies_imap()            [mail_client.py + IMAP]

Each backend:
  1. Fetch recent messages
  2. For each message: look for TKEY:{14-digit-key} in body/subject
  3. Match tkey → applications.tkey → get application_id
  4. INSERT INTO inbox_index (message_uid, tkey, application_id, ...)
  5. Generate ai_reply_draft via generate_reply_draft()  [llm_auto_reply.py]
  6. UPDATE applications SET status='replied'
  → return {"new_replies": N, "errors": [...]}
```

### 7.4 Resume Generation Flow

```
ResumePage._generate()
  └── ResumeWorker.run()
        1. generate_resume_content(jd)                 [resume_generator.py]
             → llm(MASTER_PROMPT + JD) → raw text (Mistral 7B)
        2. parse_llm_output(raw) → dict
             {salary, summary, bullets:{projects,ecolab,msc}, skills}
        → done.emit(data)

ResumePage._on_generated(data)
  → populates all right-panel QTextEdit fields
  → _auto_extract_company() → extract_company_from_jd()

ResumePage._export()
  └── ResumeExportWorker.run()
        if template is .pdf:
          apply_to_pdf(data, template, out)             [resume_generator.py]
            1. add_redact_annot() × N regions
            2. apply_redactions()       ← physically removes old text
            3. insert_textbox(summary)  ← flowing paragraph, lineheight=1.41
            4. insert_text("N. bullet") ← per baseline coordinate
            → save PDF
        else (.docx):
          apply_to_docx(data, template, out)
          export_pdf(out, desktop)                      ← Word/LibreOffice
```

---

## 8. Settings Keys Reference

All stored in `settings` table (key TEXT, value TEXT):

| Key | Default | Used by |
|-----|---------|---------|
| `llm_model_path` | `…/mistral-7b-instruct-v0.2.Q4_K_M.gguf` | LLMLoaderWorker |
| `llm_context` | `4096` | LLMLoaderWorker (n_ctx) |
| `llm_gpu_layers` | `35` | LLMLoaderWorker (n_gpu_layers) |
| `resume_path` | auto-detected PDF | ResumeExportWorker |
| `sender_name` | `"Abhay Kumar Choudhary"` | apple_mail_sender |
| `sender_role` | `"Product Manager - Digital Supply Chain"` | apple_mail_sender |
| `sender_pitch` | short pitch text | apple_mail_sender |
| `sender_linkedin` | LinkedIn URL | apple_mail_sender |
| `smtp_host` | — | mail_client, email_sender |
| `smtp_port` | `587` | mail_client |
| `smtp_user` | — | mail_client |
| `smtp_pass` | — | mail_client |
| `smtp_tls` | `"true"` | email_sender |
| `from_name` | — | email_sender |
| `imap_host` | — | mail_client |
| `imap_port` | `993` | mail_client |
| `imap_user` | — | mail_client |
| `imap_pass` | — | mail_client |
| `google_client_id` | bundled ID | oauth_manager |
| `google_client_secret` | bundled secret | oauth_manager |
| `ms_graph_client_id` | — | oauth_manager, ms_graph |

---

## 9. Key Patterns

### QThread Worker Pattern
```python
class FooWorker(QThread):
    done  = pyqtSignal(...)
    error = pyqtSignal(str)

    def __init__(self, ...):
        super().__init__()
        _connect_cleanup(self)   # finished → deleteLater

    def run(self):
        try:
            result = do_something()
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))

# Caller must hold reference:
self._worker = FooWorker(...)
self._worker.done.connect(self._on_done)
self._worker.error.connect(self._on_error)
self._worker.finished.connect(lambda: setattr(self, '_worker', None))
self._worker.start()
```

### Page Refresh Pattern
Every page that needs live data implements `refresh()`. MainWindow calls `page.refresh()` on every nav switch. Workers that modify data call `page.refresh()` on their `done` signal when the relevant page is active.

### Tracking Key System
Two tracking mechanisms coexist:

| Mechanism | Format | Used for |
|-----------|--------|---------|
| TRK-UUID | `[TRK-{uuid}]` in subject | SMTP tracked send (email_sender.py) |
| TKEY | 14-digit SHA-256 number | Apple Mail / IMAP scan (apple_mail_sender.py) |

Both written to `applications.tkey` and matched in `inbox_index`.  
`subject_to_tracking_key(subject)` (database.py) is the canonical implementation, aliased as `_subject_to_key` / `_subject_to_tkey` in sender/mail modules.

---

## 10. File-Level Quick Reference

| File | Lines | Export | Purpose |
|------|-------|--------|---------|
| `desktop_app.py` | 74 | `main()` | App entry point |
| `database.py` | 148 | `get_db, init_db, get_setting, set_setting, subject_to_tracking_key` | All DB I/O |
| `ui/style.py` | ~270 | `FLUENT_DARK, STATUS_STYLE` | Global QSS theme |
| `ui/main_window.py` | 291 | `MainWindow` | Window shell + nav |
| `ui/workers.py` | 352 | 14 worker classes | Background threads |
| `ui/pages/dashboard.py` | 560 | `DashboardPage` | Stats + AI search |
| `ui/pages/applications.py` | 273 | `ApplicationsPage` | App CRUD |
| `ui/pages/spreadsheet.py` | 409 | `SpreadsheetPage` | Editable grid |
| `ui/pages/campaign.py` | 400 | `CampaignPage` | Bulk sender |
| `ui/pages/mail.py` | 448 | `MailPage` | IMAP client |
| `ui/pages/replies.py` | 524 | `RepliesPage` | AI drafts |
| `ui/pages/assistant.py` | 233 | `AssistantPage` | Chat |
| `ui/pages/resume_builder.py` | 389 | `ResumePage` | Resume export |
| `ui/pages/settings.py` | 634 | `SettingsPage` | Config |
| `modules/llm_summarizer.py` | 67 | `_get_llm, _llm` | LLM singleton |
| `modules/llm_auto_reply.py` | 76 | `generate_reply_draft, get_fallback_draft` | AI drafts |
| `modules/resume_generator.py` | ~600 | `generate_resume_content, parse_llm_output, apply_to_pdf, apply_to_docx, export_pdf, extract_company_from_jd` | Full resume pipeline |
| `modules/oauth_manager.py` | 420 | `google_connect, ms_connect, get_google_token, get_ms_token, is_*_connected` | OAuth2 |
| `modules/email_monitor.py` | 187 | `sync_replies, index_all_inbox` | Reply-sync dispatcher |
| `modules/apple_mail_sender.py` | ~295 | `run_bulk_campaign, send_via_apple_mail, generate_personalized_intro, build_email_body` | Primary sender |
| `modules/apple_mail_reader.py` | 296 | `sync_replies_apple_mail` | Apple Mail reader |
| `modules/outlook_reader.py` | 409 | `sync_replies_outlook` | Outlook reader |
| `modules/mail_client.py` | 386 | `fetch_messages, fetch_body, send_email` | IMAP/SMTP generic |
| `modules/email_sender.py` | ~99 | `send_tracked_email` | SMTP tracked send |
| `modules/ms_graph.py` | 227 | `get_messages, send_message, complete_device_flow` | Graph API |
| `modules/excel_processor.py` | 127 | `process_excel` | Excel import |
| `modules/outlook_sender.py` | 88 | `send_via_outlook` | Outlook send |
| `modules/scheduler.py` | 83 | `start_scheduler, schedule_email` | APScheduler |

---

## 11. External Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6` | UI framework |
| `llama-cpp-python` | Local Mistral 7B inference |
| `PyMuPDF` (`fitz`) | Direct PDF editing |
| `python-docx` + `lxml` | DOCX editing |
| `docx2pdf` | DOCX → PDF via Word on macOS |
| `pandas` | Excel import |
| `requests` | OAuth2 token exchange |
| `msal` | Microsoft auth (device flow legacy) |
| `APScheduler` | Background job scheduling |

---

*Last updated: 2026-05-24 | Summary: Cambria 10.0pt, x=126.25, 290–310 chars; ● via ArialMT*
