"""
nexus/page.py — NexusOS main page.

Layout
──────
  QVBoxLayout
  ├── Toolbar  (52 px)
  ├── QSplitter (horizontal, stretch=1)
  │    ├── GraphCanvas   — 58% width
  │    └── _RightPanel   — 42% width  (QTabWidget)
  │         ├── [0] NodeInspector    — always present, not closable
  │         └── [N] dynamic viewers  — ExcelViewer / TextViewer / etc.
  └── _AIBar  — collapsible command input + HTML output (44 px → 260 px)
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSplitter,
    QPushButton, QLabel, QLineEdit, QTextEdit, QTabWidget,
    QSizePolicy, QMenu, QFileDialog, QDialog, QDialogButtonBox,
    QComboBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from nexus.graph_db import (
    init_nexus_db, seed_default_graph, all_nodes, all_edges,
    add_node, update_node,
)
from nexus.canvas import GraphCanvas
from nexus.viewers import NodeInspector, ExcelViewer, TextViewer, ImageViewer, NoteEditor, AppViewer
from nexus.registry import seed_jobtracker
from nexus.ai_agent import AgentWorker


# ── Add-node dialog ───────────────────────────────────────────────────────────

class _AddNodeDialog(QDialog):

    def __init__(self, parent=None, node_type: str = "NOTE"):
        super().__init__(parent)
        self.setWindowTitle("Add Node — NexusOS")
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: #13131A; }")

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        # Type row
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "NOTE", "APP", "FUNCTION", "API", "DATA",
            "FILE_EXCEL", "FILE_PDF", "FILE_TEXT", "FILE_CODE", "FILE_IMAGE",
        ])
        idx = self.type_combo.findText(node_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        type_row.addWidget(self.type_combo, 1)
        lay.addLayout(type_row)

        # Label
        lay.addWidget(QLabel("Label:"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Node name…")
        lay.addWidget(self.label_edit)

        # Summary
        lay.addWidget(QLabel("Summary:"))
        self.summary_edit = QTextEdit()
        self.summary_edit.setPlaceholderText("Short description…")
        self.summary_edit.setMaximumHeight(80)
        lay.addWidget(self.summary_edit)

        # File path (visible only for FILE_* types)
        self._path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("File path…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        self._path_row.addWidget(self.path_edit, 1)
        self._path_row.addWidget(browse_btn)
        lay.addLayout(self._path_row)

        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._on_type_changed(node_type)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_type_changed(self, t: str):
        show = t.startswith("FILE_")
        for i in range(self._path_row.count()):
            w = self._path_row.itemAt(i).widget()
            if w:
                w.setVisible(show)

    def _browse(self):
        t = self.type_combo.currentText()
        filters = {
            "FILE_EXCEL": "Excel files (*.xlsx *.xls);;All (*)",
            "FILE_PDF":   "PDF files (*.pdf);;All (*)",
            "FILE_TEXT":  "Text files (*.txt *.md *.rst);;All (*)",
            "FILE_CODE":  "Code (*.py *.js *.ts *.cpp *.java *.go);;All (*)",
            "FILE_IMAGE": "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All (*)",
        }.get(t, "All files (*)")
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", filters)
        if path:
            self.path_edit.setText(path)
            if not self.label_edit.text():
                self.label_edit.setText(os.path.basename(path))

    def get_data(self) -> dict:
        return {
            "type":    self.type_combo.currentText(),
            "label":   self.label_edit.text().strip() or "Untitled",
            "summary": self.summary_edit.toPlainText().strip(),
            "path":    self.path_edit.text().strip() or None,
        }


# ── Right panel — Inspector + dynamic viewer tabs ─────────────────────────────

class _RightPanel(QTabWidget):

    app_opened = pyqtSignal()   # emitted when an APP viewer tab is opened

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._close_tab)
        self.setStyleSheet(
            "QTabBar::tab { min-width: 80px; padding: 7px 14px; }"
            "QTabWidget::pane { border-top: 1px solid rgba(0,0,0,0.06); }"
        )

        self._inspector = NodeInspector()
        self.addTab(self._inspector, "Inspector")
        # Make the Inspector tab non-closable
        self.tabBar().setTabButton(0, self.tabBar().ButtonPosition.RightSide, None)

        self._open_viewers: dict[str, int] = {}   # node_id → tab index

    @property
    def inspector(self) -> NodeInspector:
        return self._inspector

    def open_viewer(self, node: dict):
        """Open the appropriate viewer in a new tab (or focus existing one)."""
        nid = node["id"]
        if nid in self._open_viewers:
            self.setCurrentIndex(self._open_viewers[nid])
            return

        ntype = node.get("type", "")
        path  = node.get("path") or ""

        if ntype == "APP":
            widget = AppViewer(node)
            self.app_opened.emit()
        elif ntype == "NOTE":
            widget = NoteEditor(node)
        elif ntype == "FILE_EXCEL" and path:
            widget = ExcelViewer(path)
        elif ntype in ("FILE_TEXT", "FILE_CODE") and path:
            widget = TextViewer(path)
        elif ntype == "FILE_IMAGE" and path:
            widget = ImageViewer(path)
        elif path and os.path.exists(path):
            widget = TextViewer(path)
        else:
            self.setCurrentIndex(0)
            return

        label = (node.get("label") or "Node")[:16]
        idx = self.addTab(widget, label)
        self._open_viewers[nid] = idx
        self.setCurrentIndex(idx)

    def _close_tab(self, idx: int):
        if idx == 0:
            return
        self._open_viewers = {
            nid: (i if i < idx else i - 1)
            for nid, i in self._open_viewers.items()
            if i != idx
        }
        self.removeTab(idx)


# ── AI command bar ────────────────────────────────────────────────────────────

class _AIBar(QFrame):
    """Collapsible AI command input + HTML result pane."""

    highlight_nodes = pyqtSignal(list)   # list[str] — node IDs to highlight

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMaximumHeight(44)
        self._expanded = False
        self._worker: AgentWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Input row ────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setFixedHeight(44)
        input_lay = QHBoxLayout(input_frame)
        input_lay.setContentsMargins(12, 6, 12, 6)
        input_lay.setSpacing(8)

        icon = QLabel("⎈")
        icon.setStyleSheet("color: #6366F1; font-size: 16px; background: transparent;")
        input_lay.addWidget(icon)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Ask NexusOS anything… e.g. 'email this startup and attach a tailored resume'"
        )
        self._input.returnPressed.connect(self._run)
        input_lay.addWidget(self._input, 1)

        self._run_btn = QPushButton("Run  ⏎")
        self._run_btn.setObjectName("accentBtn")
        self._run_btn.setFixedHeight(30)
        self._run_btn.clicked.connect(self._run)
        input_lay.addWidget(self._run_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        input_lay.addWidget(clear_btn)

        self._expand_btn = QPushButton("▾")
        self._expand_btn.setObjectName("subtleBtn")
        self._expand_btn.setFixedSize(28, 30)
        self._expand_btn.clicked.connect(self._toggle_expand)
        input_lay.addWidget(self._expand_btn)

        outer.addWidget(input_frame)

        # ── Output pane (hidden by default) ───────────────────────────────────
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(200)
        self._output.setPlaceholderText("AI response will appear here…")
        self._output.setStyleSheet(
            "QTextEdit { background: #0D0D12; border: none; padding: 8px; }"
        )
        self._output.hide()
        outer.addWidget(self._output)

    # ── Expand / collapse ─────────────────────────────────────────────────────

    def _toggle_expand(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._output.show()
            self.setMaximumHeight(260)
            self._expand_btn.setText("▴")
        else:
            self._output.hide()
            self.setMaximumHeight(44)
            self._expand_btn.setText("▾")

    # ── Run ───────────────────────────────────────────────────────────────────

    def _run(self):
        query = self._input.text().strip()
        if not query or self._worker:
            return
        if not self._expanded:
            self._toggle_expand()

        self._output.setHtml(
            "<p style='color:rgba(239,239,239,0.38); font-family:Menlo,monospace; "
            f"font-size:11px'>Thinking about: {query}…</p>"
        )
        self._run_btn.setEnabled(False)

        self._worker = AgentWorker(query, self)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.finished.connect(lambda: self._run_btn.setEnabled(True))
        self._worker.start()

    def _on_result(self, text: str, node_ids: list):
        html_lines: list[str] = []
        for line in text.split("\n"):
            if line.startswith("**") and line.endswith("**"):
                html_lines.append(
                    f"<b style='color:#A5B4FC'>{line[2:-2]}</b>"
                )
            elif "**" in line:
                escaped = line.replace("**", "<b>", 1).replace("**", "</b>", 1)
                html_lines.append(f"<span style='color:#EFEFEF'>{escaped}</span>")
            elif line.startswith("✓"):
                html_lines.append(f"<span style='color:#6CCB5F'>{line}</span>")
            elif line.startswith(("✕", "⚠")):
                html_lines.append(f"<span style='color:#FF99A4'>{line}</span>")
            elif line.startswith("[") and "]" in line:
                html_lines.append(f"<span style='color:#818CF8'>{line}</span>")
            elif line:
                html_lines.append(f"<span style='color:#DDDDE8'>{line}</span>")
            else:
                html_lines.append("<br>")

        self._output.setHtml(
            "<html><body style='"
            "background:#0D0D12; padding:10px; "
            "font-family:Menlo,SF Mono,Consolas,monospace; font-size:11px; "
            "line-height:1.55;'>"
            + "<br>".join(html_lines)
            + "</body></html>"
        )
        if node_ids:
            self.highlight_nodes.emit(node_ids)

    def _on_error(self, msg: str):
        self._output.setHtml(
            f"<p style='color:#FF99A4; font-family:monospace'>Error: {msg}</p>"
        )
        self._run_btn.setEnabled(True)

    def _clear(self):
        self._input.clear()
        self._output.clear()


# ── NexusPage ─────────────────────────────────────────────────────────────────

class NexusPage(QWidget):
    """Main NexusOS page — the AI-native knowledge graph operating system."""

    def __init__(self, parent=None):
        super().__init__(parent)

        init_nexus_db()
        seed_default_graph()
        seed_jobtracker()

        self._build()
        QTimer.singleShot(200, self.refresh)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("pageHeader")
        toolbar.setFixedHeight(52)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(16, 8, 16, 8)
        tbar.setSpacing(8)

        title_lbl = QLabel("⬡  NexusOS")
        title_lbl.setStyleSheet(
            "color: #EFEFEF; font-size: 16px; font-weight: 700; "
            "background: transparent; letter-spacing: -0.2px;"
        )
        tbar.addWidget(title_lbl)
        tbar.addSpacing(16)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter nodes…")
        self._search.setMaximumWidth(220)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._on_search)
        tbar.addWidget(self._search)

        tbar.addStretch()

        add_btn = QPushButton("+ Add  ▾")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._show_add_menu)
        tbar.addWidget(add_btn)

        self._conn_btn = QPushButton("⇔ Connect")
        self._conn_btn.setFixedHeight(32)
        self._conn_btn.setCheckable(True)
        self._conn_btn.toggled.connect(self._on_connect_toggle)
        tbar.addWidget(self._conn_btn)

        fit_btn = QPushButton("⊞ Fit")
        fit_btn.setFixedHeight(32)
        fit_btn.clicked.connect(lambda: self._canvas.fit())
        tbar.addWidget(fit_btn)

        layout_btn = QPushButton("↺ Layout")
        layout_btn.setFixedHeight(32)
        layout_btn.clicked.connect(self._rerun_layout)
        tbar.addWidget(layout_btn)

        root.addWidget(toolbar)

        # ── Body splitter ─────────────────────────────────────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: rgba(255,255,255,0.06); }"
        )

        # Left — graph canvas
        self._canvas = GraphCanvas()
        self._canvas.node_clicked.connect(self._on_node_click)
        self._canvas.node_double_clicked.connect(self._on_node_dbl)
        self._canvas.node_moved.connect(self._on_node_moved)
        self._canvas.background_clicked.connect(self._on_bg_click)
        self._splitter.addWidget(self._canvas)

        # Right — inspector + viewer tabs
        self._panel = _RightPanel()
        self._panel.inspector.open_file_requested.connect(self._panel.open_viewer)
        self._panel.app_opened.connect(self._on_app_opened)
        self._splitter.addWidget(self._panel)

        self._splitter.setSizes([480, 520])
        root.addWidget(self._splitter, 1)

        # ── AI command bar ────────────────────────────────────────────────────
        self._ai_bar = _AIBar()
        self._ai_bar.highlight_nodes.connect(self._highlight_nodes)
        root.addWidget(self._ai_bar)

    # ── Data ─────────────────────────────────────────────────────────────────

    def refresh(self):
        self._canvas.load_graph(all_nodes(), all_edges())
        QTimer.singleShot(600, self._canvas.fit)

    # ── Canvas events ─────────────────────────────────────────────────────────

    def _on_node_click(self, data: dict):
        # If Connect toolbar button is active and no source selected yet,
        # this click sets the source node (canvas handles the second click itself).
        if self._conn_btn.isChecked() and self._canvas._connect_from is None:
            self._canvas._connect_from = data["id"]
            return
        self._panel.inspector.load_node(data)
        self._panel.setCurrentIndex(0)

    def _on_node_dbl(self, data: dict):
        # All node types — including APP — open as tabs in the right panel
        self._panel.open_viewer(data)

    def _on_app_opened(self):
        """Widen the right panel so the embedded app has more room."""
        total = self._splitter.width()
        self._splitter.setSizes([int(total * 0.28), int(total * 0.72)])

    def _on_node_moved(self, nid: str, x: float, y: float):
        update_node(nid, pos_x=x, pos_y=y)

    def _on_bg_click(self):
        self._canvas.deselect()
        self._panel.inspector.clear()
        self._canvas._connect_from = None
        if self._conn_btn.isChecked():
            self._conn_btn.setChecked(False)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _show_add_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1A1A28; border: 1px solid rgba(255,255,255,0.12); "
            "color: #EFEFEF; border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 7px 18px; border-radius: 5px; }"
            "QMenu::item:selected { background: rgba(99,102,241,0.25); }"
        )
        for label, ntype in [
            ("✎  New Note",         "NOTE"),
            ("⊞  Import File…",     "FILE_EXCEL"),
            ("@  Add API",          "API"),
            ("ƒ  Add Function",     "FUNCTION"),
            ("⊡  Add App",          "APP"),
            ("⊡  Add Data Source",  "DATA"),
        ]:
            act = menu.addAction(label)
            act.triggered.connect(lambda _, t=ntype: self._add_node_dialog(t))

        btn = self.sender()
        if btn:
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _add_node_dialog(self, node_type: str = "NOTE"):
        dlg = _AddNodeDialog(self, node_type)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            nid = add_node(
                type_=d["type"], label=d["label"],
                summary=d["summary"], path=d["path"],
            )
            node_data = {
                "id": nid, "type": d["type"], "label": d["label"],
                "summary": d["summary"], "path": d["path"],
                "meta": {}, "pos_x": 0, "pos_y": 0,
            }
            self._canvas.add_node(node_data)

    def _on_connect_toggle(self, active: bool):
        self._conn_btn.setStyleSheet(
            "background: rgba(99,102,241,0.20); "
            "border: 1px solid #6366F1; color: #A5B4FC;"
            if active else ""
        )

    def _rerun_layout(self):
        self._canvas._iter = 0
        self._canvas._restart_layout()

    # ── Search / highlight ────────────────────────────────────────────────────

    def _on_search(self, text: str):
        q = text.strip().lower()
        for node in self._canvas._nodes.values():
            if not q:
                node.setOpacity(1.0)
            else:
                label   = (node.data.get("label", "") or "").lower()
                summary = (node.data.get("summary", "") or "").lower()
                node.setOpacity(1.0 if (q in label or q in summary) else 0.18)

    def _highlight_nodes(self, node_ids: list):
        id_set = set(node_ids)
        for nid, node in self._canvas._nodes.items():
            node.setOpacity(1.0 if nid in id_set else 0.22)
        # Fade back to normal after 4 seconds
        QTimer.singleShot(4000, self._reset_opacity)

    def _reset_opacity(self):
        for node in self._canvas._nodes.values():
            node.setOpacity(1.0)
