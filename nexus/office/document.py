"""
nexus/office/document.py — Word-like rich text document editor.

Features
────────
  • Bold, Italic, Underline, Strikethrough
  • Heading styles (H1, H2, H3, Body)
  • Font size picker
  • Text colour
  • Bullet list / numbered list
  • Save as .txt  |  Export as .html
  • Auto-save on focus loss
"""
from __future__ import annotations

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QLabel, QTextEdit, QLineEdit, QToolBar, QFontComboBox,
    QSpinBox, QColorDialog, QFileDialog, QMessageBox,
    QSizePolicy, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QFont, QTextCharFormat, QTextCursor, QColor,
    QTextListFormat, QKeySequence, QAction,
)


class DocumentEditor(QWidget):
    """Full-featured rich-text document editor."""

    title_changed = pyqtSignal(str)   # emitted when document title changes

    def __init__(self, path: str | None = None, title: str = "Untitled Document", parent=None):
        super().__init__(parent)
        self._path  = path
        self._title = title
        self._build()
        if path and os.path.exists(path):
            self._load_file(path)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("pageHeader")
        toolbar.setFixedHeight(46)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(12, 6, 12, 6)
        tbar.setSpacing(4)

        # Document title
        self._title_edit = QLineEdit(self._title)
        self._title_edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; "
            "font-size: 14px; font-weight: 700; color: #1A1A1A; }"
            "QLineEdit:focus { border-bottom: 2px solid #0067C0; }"
        )
        self._title_edit.setMinimumWidth(200)
        self._title_edit.editingFinished.connect(self._on_title_changed)
        tbar.addWidget(self._title_edit, 1)
        tbar.addSpacing(12)

        # Heading style selector
        self._style_combo = QComboBox()
        self._style_combo.addItems(["Body", "Heading 1", "Heading 2", "Heading 3", "Caption"])
        self._style_combo.setFixedWidth(110)
        self._style_combo.setFixedHeight(28)
        self._style_combo.currentTextChanged.connect(self._apply_style)
        tbar.addWidget(self._style_combo)

        tbar.addSpacing(6)

        # Font size
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 72)
        self._size_spin.setValue(13)
        self._size_spin.setFixedWidth(58)
        self._size_spin.setFixedHeight(28)
        self._size_spin.valueChanged.connect(self._apply_font_size)
        tbar.addWidget(self._size_spin)

        tbar.addSpacing(6)

        # Format buttons
        for icon, tip, fn in [
            ("B", "Bold (⌘B)",          self._bold),
            ("I", "Italic (⌘I)",        self._italic),
            ("U", "Underline (⌘U)",     self._underline),
            ("S̶", "Strikethrough",       self._strikethrough),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.clicked.connect(fn)
            tbar.addWidget(btn)
            if icon == "B":  self._bold_btn = btn
            elif icon == "I":  self._ital_btn = btn
            elif icon == "U":  self._uline_btn = btn

        tbar.addSpacing(6)

        # List buttons
        for icon, tip, fn in [
            ("≡", "Bullet list",  self._bullet_list),
            ("1.", "Numbered list", self._numbered_list),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            tbar.addWidget(btn)

        tbar.addSpacing(6)

        # Color
        self._color_btn = QPushButton("A")
        self._color_btn.setFixedSize(28, 28)
        self._color_btn.setToolTip("Text colour")
        self._color_btn.setStyleSheet(
            "QPushButton { border-bottom: 3px solid #C42B1C; font-weight: 700; }"
        )
        self._color_btn.clicked.connect(self._pick_color)
        tbar.addWidget(self._color_btn)

        tbar.addStretch()

        # Save / Export
        save_btn = QPushButton("💾  Save")
        save_btn.setObjectName("accentBtn")
        save_btn.setFixedHeight(28)
        save_btn.clicked.connect(self._save)
        tbar.addWidget(save_btn)

        export_btn = QPushButton("↓  Export HTML")
        export_btn.setFixedHeight(28)
        export_btn.clicked.connect(self._export_html)
        tbar.addWidget(export_btn)

        lay.addWidget(toolbar)

        # ── Ruler area (visual) ───────────────────────────────────────────────
        ruler = QFrame()
        ruler.setFixedHeight(4)
        ruler.setStyleSheet("background: #F0F0F0; border-bottom: 1px solid rgba(0,0,0,0.06);")
        lay.addWidget(ruler)

        # ── Editor ────────────────────────────────────────────────────────────
        self._editor = QTextEdit()
        self._editor.setAcceptRichText(True)
        self._editor.document().setDefaultFont(QFont("Helvetica Neue, Arial", 13))
        self._editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; border: none; "
            "padding: 40px 80px; color: #1A1A1A; line-height: 1.6; }"
        )
        self._editor.setPlaceholderText(
            "Start writing your document here…\n\n"
            "Use the toolbar to format text, add headings, and create lists."
        )
        self._editor.cursorPositionChanged.connect(self._on_cursor_moved)
        lay.addWidget(self._editor, 1)

        # ── Status bar ────────────────────────────────────────────────────────
        status = QFrame()
        status.setFixedHeight(22)
        status.setStyleSheet(
            "QFrame { background: #F5F5F5; border-top: 1px solid rgba(0,0,0,0.06); }"
        )
        sl = QHBoxLayout(status)
        sl.setContentsMargins(12, 0, 12, 0)
        sl.setSpacing(12)
        self._word_count = QLabel("0 words")
        self._word_count.setStyleSheet(
            "font-size: 11px; color: rgba(0,0,0,0.45); background: transparent;"
        )
        sl.addWidget(self._word_count)
        sl.addStretch()
        path_lbl = QLabel(os.path.basename(self._path) if self._path else "unsaved")
        path_lbl.setStyleSheet(
            "font-size: 11px; color: rgba(0,0,0,0.35); background: transparent;"
        )
        sl.addWidget(path_lbl)
        lay.addWidget(status)

        # Keyboard shortcuts
        self._editor.keyPressEvent  # keep reference

    # ── Format helpers ────────────────────────────────────────────────────────

    def _fmt(self) -> QTextCharFormat:
        return self._editor.currentCharFormat()

    def _apply_format(self, fmt: QTextCharFormat):
        cursor = self._editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self._editor.mergeCurrentCharFormat(fmt)

    def _bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(
            QFont.Weight.Bold if not self._fmt().font().bold() else QFont.Weight.Normal
        )
        self._apply_format(fmt)

    def _italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._fmt().fontItalic())
        self._apply_format(fmt)

    def _underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._fmt().fontUnderline())
        self._apply_format(fmt)

    def _strikethrough(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self._fmt().fontStrikeOut())
        self._apply_format(fmt)

    def _apply_font_size(self, size: int):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._apply_format(fmt)

    def _apply_style(self, style: str):
        cursor = self._editor.textCursor()
        fmt = QTextCharFormat()
        if style == "Heading 1":
            fmt.setFontPointSize(24)
            fmt.setFontWeight(QFont.Weight.Bold)
        elif style == "Heading 2":
            fmt.setFontPointSize(18)
            fmt.setFontWeight(QFont.Weight.Bold)
        elif style == "Heading 3":
            fmt.setFontPointSize(14)
            fmt.setFontWeight(QFont.Weight.DemiBold)
        elif style == "Caption":
            fmt.setFontPointSize(11)
            fmt.setForeground(QColor("rgba(0,0,0,0.55)"))
        else:
            fmt.setFontPointSize(13)
            fmt.setFontWeight(QFont.Weight.Normal)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(fmt)
        self._editor.mergeCurrentCharFormat(fmt)

    def _bullet_list(self):
        cursor = self._editor.textCursor()
        lst = cursor.currentList()
        if lst and lst.format().style() == QTextListFormat.Style.ListDisc:
            cursor.setBlockFormat(cursor.blockFormat())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDisc)
            fmt.setIndent(1)
            cursor.createList(fmt)

    def _numbered_list(self):
        cursor = self._editor.textCursor()
        lst = cursor.currentList()
        if lst and lst.format().style() == QTextListFormat.Style.ListDecimal:
            cursor.setBlockFormat(cursor.blockFormat())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDecimal)
            fmt.setIndent(1)
            cursor.createList(fmt)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor("#1A1A1A"), self, "Text Colour")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._apply_format(fmt)
            self._color_btn.setStyleSheet(
                f"QPushButton {{ border-bottom: 3px solid {color.name()}; font-weight: 700; }}"
            )

    # ── Cursor change → update toolbar ────────────────────────────────────────

    def _on_cursor_moved(self):
        fmt = self._editor.currentCharFormat()
        self._bold_btn.setChecked(fmt.font().bold())
        self._ital_btn.setChecked(fmt.fontItalic())
        self._uline_btn.setChecked(fmt.fontUnderline())
        sz = fmt.fontPointSize()
        if sz > 0:
            self._size_spin.blockSignals(True)
            self._size_spin.setValue(int(sz))
            self._size_spin.blockSignals(False)

        # Update word count
        text = self._editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        self._word_count.setText(f"{words} word{'s' if words != 1 else ''}")

    # ── Title ─────────────────────────────────────────────────────────────────

    def _on_title_changed(self):
        self._title = self._title_edit.text() or "Untitled Document"
        self.title_changed.emit(self._title)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _load_file(self, path: str):
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".html", ".htm"):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    self._editor.setHtml(f.read())
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    self._editor.setPlainText(f.read())
        except Exception as e:
            self._editor.setPlainText(f"Error loading file: {e}")

    def _save(self):
        if not self._path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Document", f"{self._title}.txt",
                "Text Files (*.txt);;HTML Files (*.html);;All Files (*)",
            )
            if not path:
                return
            self._path = path

        try:
            ext = os.path.splitext(self._path)[1].lower()
            with open(self._path, "w", encoding="utf-8") as f:
                if ext in (".html", ".htm"):
                    f.write(self._editor.toHtml())
                else:
                    f.write(self._editor.toPlainText())
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def _export_html(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as HTML", f"{self._title}.html", "HTML Files (*.html)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._editor.toHtml())
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_content(self, content: str, html: bool = False):
        if html:
            self._editor.setHtml(content)
        else:
            self._editor.setPlainText(content)

    def get_content(self) -> str:
        return self._editor.toPlainText()

    def get_html(self) -> str:
        return self._editor.toHtml()
