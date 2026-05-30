from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QSizePolicy, QComboBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from database import get_db, get_setting
from ui.workers import LLMInferenceWorker
import modules.llm_summarizer as ls


def _system():
    name     = get_setting("sender_name",  "Abhay Kumar Choudhary")
    role     = get_setting("sender_role",  "Product Manager")
    pitch    = get_setting("sender_pitch", "supply chain automation")
    linkedin = get_setting("sender_linkedin", "")
    return (
        f"You are a helpful job-search assistant for {name}, a {role} "
        f"specialising in {pitch}. LinkedIn: {linkedin}\n"
        "Write cold emails, suggest follow-ups, summarise replies, and give interview tips.\n"
        "Be direct, professional, and concise. No filler phrases."
    )


class Bubble(QFrame):
    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,4,0,4)

        role = QLabel("You" if is_user else "✦ Mistral")
        role.setStyleSheet(
            f"color: {'#60CDFF' if is_user else '#6CCB5F'}; "
            f"font-size: 11px; font-weight: 700; background: transparent;"
        )
        role.setAlignment(Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(role)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        if is_user:
            msg.setStyleSheet(
                "background: rgba(0,120,212,0.2); border: 1px solid rgba(0,120,212,0.3); "
                "border-radius: 10px 10px 2px 10px; padding: 10px 14px; color: #FFFFFF; font-size: 13px;"
            )
        else:
            msg.setStyleSheet(
                "background: #2C2C2C; border: 1px solid rgba(255,255,255,0.08); "
                "border-radius: 10px 10px 10px 2px; padding: 10px 14px; color: #FFFFFF; font-size: 13px;"
            )

        row = QHBoxLayout(); row.setContentsMargins(0,0,0,0)
        if is_user: row.addStretch()
        row.addWidget(msg, 4)
        if not is_user: row.addStretch()
        lay.addLayout(row)


class AssistantPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._worker  = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(28,24,28,24); root.setSpacing(14)

        # Title
        top = QHBoxLayout()
        t = QLabel("AI Assistant"); t.setObjectName("pageTitle")
        top.addWidget(t); top.addStretch()
        self.modelLbl = QLabel("● Model loading…")
        self.modelLbl.setStyleSheet("color: #FCE100; font-size: 12px; background: transparent;")
        top.addWidget(self.modelLbl)
        root.addLayout(top)

        sub = QLabel("Chat with Mistral 7B — write cold emails, follow-ups, interview prep")
        sub.setObjectName("pageSubtitle")
        root.addWidget(sub)

        # Quick prompts
        qrow = QHBoxLayout(); qrow.setSpacing(8)
        for label, prompt in [
            ("✉  Cold Email",     "Write a personalised cold email for a {position} role at {company}."),
            ("🔄  Follow-up",     "Write a polite 2-week follow-up email for a job I applied to."),
            ("📋  Pipeline",      "Summarise my job application pipeline status in a brief paragraph."),
            ("🎯  Interview Prep","Give me 5 key talking points to prepare for a Product Manager interview."),
        ]:
            b = QPushButton(label); b.setObjectName("subtleBtn"); b.setFixedHeight(30)
            b.clicked.connect(lambda _, p=prompt: self._quick(p))
            qrow.addWidget(b)
        qrow.addStretch()
        root.addLayout(qrow)

        # Context picker
        ctx = QHBoxLayout(); ctx.setSpacing(10)
        ctx.addWidget(QLabel("Context:"))
        self.picker = QComboBox(); self.picker.addItem("No specific company", None); self.picker.setMinimumWidth(220)
        ctx.addWidget(self.picker)
        ctx.addStretch()
        clr = QPushButton("Clear Chat"); clr.setObjectName("subtleBtn"); clr.clicked.connect(self._clear)
        ctx.addWidget(clr)
        root.addLayout(ctx)

        # Chat area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; background: #1C1C1C; }"
        )
        self.chatWidget = QWidget()
        self.chatLayout = QVBoxLayout(self.chatWidget)
        self.chatLayout.setContentsMargins(12,12,12,12); self.chatLayout.setSpacing(8)
        self.chatLayout.addStretch()
        self.scroll.setWidget(self.chatWidget)
        root.addWidget(self.scroll, 1)

        # Welcome message
        self._add_bubble(
            "Hi! I'm your AI assistant powered by Mistral 7B running locally on your machine. "
            "Ask me to write a cold email, prepare for an interview, or summarise your pipeline — I'm here to help.",
            is_user=False
        )

        # Input row
        irow = QHBoxLayout(); irow.setSpacing(8)
        self.inputField = QLineEdit()
        self.inputField.setPlaceholderText("Ask anything… e.g. 'Write a cold email to Google for a PM role'")
        self.inputField.returnPressed.connect(self._send)
        self.inputField.setFixedHeight(40)
        irow.addWidget(self.inputField)
        self.sendBtn = QPushButton("Send")
        self.sendBtn.setObjectName("accentBtn"); self.sendBtn.setFixedSize(80, 40)
        self.sendBtn.clicked.connect(self._send)
        irow.addWidget(self.sendBtn)
        root.addLayout(irow)

    def refresh(self):
        if ls._get_llm() is not None:
            self.modelLbl.setText("● Mistral 7B ready")
            self.modelLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        else:
            self.modelLbl.setText("● Model loading…")
            self.modelLbl.setStyleSheet("color: #FCE100; font-size: 12px; background: transparent;")

        conn = get_db()
        apps = conn.execute("SELECT id, company, position FROM applications ORDER BY company LIMIT 200").fetchall()
        conn.close()
        self.picker.clear()
        self.picker.addItem("No specific company", None)
        for aid, co, pos in apps:
            self.picker.addItem(f"{co or '?'} — {pos or '?'}", aid)

    def _quick(self, tmpl):
        app_id = self.picker.currentData()
        co, pos = "", ""
        if app_id:
            conn = get_db()
            row = conn.execute("SELECT company, position FROM applications WHERE id=?", (app_id,)).fetchone()
            conn.close()
            if row: co, pos = row
        filled = tmpl.replace("{company}", co or "the company").replace("{position}", pos or "the role")
        self.inputField.setText(filled)
        self._send()

    def _send(self):
        text = self.inputField.text().strip()
        if not text or self._worker: return

        if ls._get_llm() is None:
            QMessageBox.warning(self, "No Model", "Model is still loading — wait a moment, or load it in Settings."); return

        self.inputField.clear()
        self._add_bubble(text, is_user=True)
        self._history.append(("user", text))

        # Build prompt — no leading <s>, llama_cpp adds BOS
        sys_prompt = _system()
        app_id = self.picker.currentData()
        ctx = ""
        if app_id:
            conn = get_db()
            row = conn.execute("SELECT company,position,notes,status FROM applications WHERE id=?", (app_id,)).fetchone()
            conn.close()
            if row:
                ctx = f"\n[Context: {row[0]} — {row[1]}, Status: {row[3]}, Notes: {row[2] or 'none'}]"

        hist = ""
        for role, msg in self._history[-6:]:
            hist += f"{'User' if role=='user' else 'Assistant'}: {msg}\n"

        prompt = f"[INST] {sys_prompt}{ctx}\n\n{hist}Assistant: [/INST]"

        self._typing = QLabel("✦  Mistral is thinking…")
        self._typing.setStyleSheet("color: rgba(0,0,0,0.42); font-size: 13px; background: transparent; padding: 4px 0;")
        self.chatLayout.insertWidget(self.chatLayout.count()-1, self._typing)
        self._scroll_down()

        self.sendBtn.setEnabled(False); self.sendBtn.setText("…")

        self._worker = LLMInferenceWorker(prompt, max_tokens=600, temperature=0.7)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()

    def _on_done(self, text):
        self.sendBtn.setEnabled(True); self.sendBtn.setText("Send")
        if hasattr(self, "_typing"): self._typing.deleteLater()
        self._history.append(("assistant", text))
        self._add_bubble(text, is_user=False)

    def _on_error(self, err):
        self.sendBtn.setEnabled(True); self.sendBtn.setText("Send")
        if hasattr(self, "_typing"): self._typing.deleteLater()
        self._add_bubble(f"Error: {err}", is_user=False)

    def _add_bubble(self, text, is_user):
        b = Bubble(text, is_user)
        self.chatLayout.insertWidget(self.chatLayout.count()-1, b)
        self._scroll_down()

    def _scroll_down(self):
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def _clear(self):
        self._history.clear()
        while self.chatLayout.count() > 1:
            item = self.chatLayout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
