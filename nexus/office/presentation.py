"""
nexus/office/presentation.py — PowerPoint-like slide editor.

Features
────────
  • Slide list on the left (thumbnail labels)
  • Edit area on the right: title + content text
  • Add / delete / duplicate / reorder slides
  • Slide themes: White, Blue, Dark, Purple
  • Export to plain-text outline
  • Keyboard: Ctrl+N new slide, Del delete slide
"""
from __future__ import annotations

import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QPushButton, QLabel, QTextEdit, QLineEdit, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QComboBox,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QPen


# ── Slide thumbnail painter ───────────────────────────────────────────────────

def _make_thumbnail(title: str, content: str, theme: str = "white") -> QPixmap:
    W, H = 140, 90
    px = QPixmap(W, H)

    themes = {
        "white":  ("#FFFFFF", "#1A1A1A", "#0067C0"),
        "blue":   ("#0067C0", "#FFFFFF", "#FFEE00"),
        "dark":   ("#1A1A2E", "#EFEFEF", "#A5B4FC"),
        "purple": ("#4B0082", "#FFFFFF", "#FFD700"),
    }
    bg, fg, accent = themes.get(theme, themes["white"])

    px.fill(QColor(bg))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Accent bar at top
    p.fillRect(0, 0, W, 4, QColor(accent))

    # Title
    p.setPen(QColor(fg))
    p.setFont(QFont("Helvetica Neue", 8, QFont.Weight.Bold))
    p.drawText(8, 14, W - 16, 20, Qt.AlignmentFlag.AlignLeft, title[:40] or "Untitled")

    # Content preview
    p.setFont(QFont("Helvetica Neue", 6))
    p.setPen(QColor(fg + "CC" if len(fg) == 7 else fg))
    p.drawText(8, 32, W - 16, H - 40, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
               content[:120])

    p.end()
    return px


# ── Slide list item ───────────────────────────────────────────────────────────

class _SlideItem(QListWidgetItem):
    def __init__(self, slide: dict, idx: int, theme: str):
        super().__init__()
        self._slide = slide
        self._theme = theme
        self.refresh(idx)

    def refresh(self, idx: int):
        title   = self._slide.get("title", "")
        content = self._slide.get("content", "")
        px = _make_thumbnail(title, content, self._theme)
        self.setIcon(px)
        self.setText(f"  {idx + 1}.  {title[:25] or 'Untitled'}")
        self.setSizeHint(QPixmap(150, 100).size())


# ── Presentation editor ───────────────────────────────────────────────────────

class PresentationEditor(QWidget):
    title_changed = pyqtSignal(str)

    def __init__(self, path: str | None = None, title: str = "Presentation", parent=None):
        super().__init__(parent)
        self._path   = path
        self._title  = title
        self._slides: list[dict] = []
        self._current = -1
        self._theme  = "white"
        self._build()
        if path and os.path.exists(path):
            self._load_file(path)
        else:
            self._add_slide(initial=True)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("pageHeader")
        toolbar.setFixedHeight(44)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(12, 6, 12, 6)
        tbar.setSpacing(6)

        title_edit = QLineEdit(self._title)
        title_edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; "
            "font-size: 13px; font-weight: 700; color: #1A1A1A; }"
        )
        title_edit.setMaximumWidth(200)
        title_edit.editingFinished.connect(
            lambda: self.title_changed.emit(title_edit.text())
        )
        tbar.addWidget(title_edit)
        tbar.addSpacing(8)

        for label, tip, fn in [
            ("+ Slide", "Add new slide",         self._add_slide),
            ("⧉ Dup",   "Duplicate slide",        self._dup_slide),
            ("− Slide", "Delete current slide",   self._del_slide),
            ("↑ Up",    "Move slide up",           self._move_up),
            ("↓ Down",  "Move slide down",         self._move_down),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tbar.addWidget(b)

        tbar.addSpacing(8)
        theme_lbl = QLabel("Theme:")
        theme_lbl.setStyleSheet("color: rgba(0,0,0,0.5); background: transparent; font-size: 12px;")
        tbar.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["White", "Blue", "Dark", "Purple"])
        self._theme_combo.setFixedHeight(28)
        self._theme_combo.currentTextChanged.connect(self._change_theme)
        tbar.addWidget(self._theme_combo)

        tbar.addStretch()

        save_btn = QPushButton("💾  Save")
        save_btn.setObjectName("accentBtn")
        save_btn.setFixedHeight(28)
        save_btn.clicked.connect(self._save)
        tbar.addWidget(save_btn)

        export_btn = QPushButton("↓  Export")
        export_btn.setFixedHeight(28)
        export_btn.clicked.connect(self._export_txt)
        tbar.addWidget(export_btn)

        root.addWidget(toolbar)

        # ── Body splitter ─────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left — slide list
        self._slide_list = QListWidget()
        self._slide_list.setIconSize(QPixmap(140, 90).size())
        self._slide_list.setSpacing(4)
        self._slide_list.setFixedWidth(168)
        self._slide_list.setStyleSheet(
            "QListWidget { background: #F5F5F5; border: none; border-right: 1px solid rgba(0,0,0,0.08); }"
            "QListWidget::item { padding: 4px; border-radius: 4px; }"
            "QListWidget::item:selected { background: rgba(0,103,192,0.15); }"
        )
        self._slide_list.currentRowChanged.connect(self._on_slide_selected)
        splitter.addWidget(self._slide_list)

        # Right — slide editor
        right = QFrame()
        right.setStyleSheet(f"QFrame {{ background: #E8E8E8; }}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(40, 40, 40, 40)
        rl.setSpacing(16)

        # Slide number badge
        self._slide_num = QLabel("Slide 1 of 1")
        self._slide_num.setStyleSheet(
            "font-size: 11px; color: rgba(0,0,0,0.45); background: transparent; text-align: center;"
        )
        self._slide_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self._slide_num)

        # Slide canvas
        self._canvas = QFrame()
        self._canvas.setMinimumSize(500, 320)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._canvas.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 6px; "
            "border: 1px solid rgba(0,0,0,0.10); }"
        )
        canvas_lay = QVBoxLayout(self._canvas)
        canvas_lay.setContentsMargins(48, 36, 48, 36)
        canvas_lay.setSpacing(16)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Click to add title…")
        self._title_edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; "
            "font-size: 28px; font-weight: 700; color: #1A1A1A; }"
            "QLineEdit:focus { border-bottom: 2px solid #0067C0; }"
        )
        self._title_edit.editingFinished.connect(self._save_current)
        canvas_lay.addWidget(self._title_edit)

        self._content_edit = QTextEdit()
        self._content_edit.setPlaceholderText(
            "Click to add content…\n\n"
            "• Bullet point\n• Another point\n\nUse  + Slide  to add a new slide."
        )
        self._content_edit.setStyleSheet(
            "QTextEdit { background: transparent; border: none; "
            "font-size: 16px; color: #2A2A2A; line-height: 1.6; }"
        )
        self._content_edit.textChanged.connect(self._save_current)
        canvas_lay.addWidget(self._content_edit, 1)

        rl.addWidget(self._canvas, 1)

        # Slide notes
        notes_lbl = QLabel("SPEAKER NOTES")
        notes_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; letter-spacing: 1px; "
            "color: rgba(0,0,0,0.38); background: transparent;"
        )
        rl.addWidget(notes_lbl)

        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.setPlaceholderText("Add speaker notes here…")
        self._notes_edit.setStyleSheet(
            "QTextEdit { background: #FFFFFF; border: 1px solid rgba(0,0,0,0.10); "
            "border-radius: 6px; font-size: 12px; padding: 8px; color: #1A1A1A; }"
        )
        self._notes_edit.textChanged.connect(self._save_current)
        rl.addWidget(self._notes_edit)

        splitter.addWidget(right)
        splitter.setSizes([168, 600])
        root.addWidget(splitter, 1)

    # ── Slide management ──────────────────────────────────────────────────────

    def _add_slide(self, initial: bool = False):
        slide = {"title": "" if initial else "New Slide", "content": "", "notes": ""}
        idx = self._current + 1 if self._current >= 0 else len(self._slides)
        self._slides.insert(idx, slide)
        self._rebuild_list()
        self._select_slide(idx)

    def _dup_slide(self):
        if self._current < 0:
            return
        import copy
        new_slide = copy.deepcopy(self._slides[self._current])
        new_slide["title"] += " (Copy)"
        self._slides.insert(self._current + 1, new_slide)
        self._rebuild_list()
        self._select_slide(self._current + 1)

    def _del_slide(self):
        if self._current < 0 or len(self._slides) <= 1:
            return
        self._slides.pop(self._current)
        new_idx = min(self._current, len(self._slides) - 1)
        self._rebuild_list()
        self._select_slide(new_idx)

    def _move_up(self):
        if self._current <= 0:
            return
        self._slides[self._current], self._slides[self._current - 1] = \
            self._slides[self._current - 1], self._slides[self._current]
        self._rebuild_list()
        self._select_slide(self._current - 1)

    def _move_down(self):
        if self._current < 0 or self._current >= len(self._slides) - 1:
            return
        self._slides[self._current], self._slides[self._current + 1] = \
            self._slides[self._current + 1], self._slides[self._current]
        self._rebuild_list()
        self._select_slide(self._current + 1)

    def _change_theme(self, theme_name: str):
        self._theme = theme_name.lower()
        themes = {
            "white":  ("#FFFFFF", "#1A1A1A"),
            "blue":   ("#0067C0", "#FFFFFF"),
            "dark":   ("#1A1A2E", "#EFEFEF"),
            "purple": ("#4B0082", "#FFFFFF"),
        }
        bg, fg = themes.get(self._theme, ("#FFFFFF", "#1A1A1A"))
        self._canvas.setStyleSheet(
            f"QFrame {{ background: {bg}; border-radius: 6px; "
            "border: 1px solid rgba(0,0,0,0.10); }}"
        )
        self._title_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"font-size: 28px; font-weight: 700; color: {fg}; }}"
            f"QLineEdit:focus {{ border-bottom: 2px solid {'#FFEE00' if bg != '#FFFFFF' else '#0067C0'}; }}"
        )
        self._content_edit.setStyleSheet(
            f"QTextEdit {{ background: transparent; border: none; "
            f"font-size: 16px; color: {fg}; line-height: 1.6; }}"
        )
        self._rebuild_list()

    # ── List rebuilding ───────────────────────────────────────────────────────

    def _rebuild_list(self):
        self._slide_list.blockSignals(True)
        self._slide_list.clear()
        for i, slide in enumerate(self._slides):
            item = _SlideItem(slide, i, self._theme)
            self._slide_list.addItem(item)
        self._slide_list.blockSignals(False)
        self._slide_num.setText(f"Slide {self._current + 1} of {len(self._slides)}")

    def _select_slide(self, idx: int):
        self._current = idx
        self._slide_list.blockSignals(True)
        self._slide_list.setCurrentRow(idx)
        self._slide_list.blockSignals(False)
        self._load_slide(idx)

    def _on_slide_selected(self, row: int):
        if row < 0:
            return
        self._save_current()
        self._current = row
        self._load_slide(row)

    def _load_slide(self, idx: int):
        if idx < 0 or idx >= len(self._slides):
            return
        slide = self._slides[idx]
        self._title_edit.blockSignals(True)
        self._content_edit.blockSignals(True)
        self._notes_edit.blockSignals(True)
        self._title_edit.setText(slide.get("title", ""))
        self._content_edit.setPlainText(slide.get("content", ""))
        self._notes_edit.setPlainText(slide.get("notes", ""))
        self._title_edit.blockSignals(False)
        self._content_edit.blockSignals(False)
        self._notes_edit.blockSignals(False)
        self._slide_num.setText(f"Slide {idx + 1} of {len(self._slides)}")

    def _save_current(self):
        if self._current < 0 or self._current >= len(self._slides):
            return
        self._slides[self._current]["title"]   = self._title_edit.text()
        self._slides[self._current]["content"] = self._content_edit.toPlainText()
        self._slides[self._current]["notes"]   = self._notes_edit.toPlainText()
        # Refresh thumbnail
        item = self._slide_list.item(self._current)
        if item and isinstance(item, _SlideItem):
            item._slide = self._slides[self._current]
            item.refresh(self._current)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._slides = data.get("slides", [])
            self._theme  = data.get("theme", "white")
            combo_text   = self._theme.capitalize()
            idx = self._theme_combo.findText(combo_text)
            if idx >= 0:
                self._theme_combo.setCurrentIndex(idx)
            self._rebuild_list()
            if self._slides:
                self._select_slide(0)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", str(e))

    def _save(self):
        if not self._path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Presentation", f"{self._title}.nexusppt",
                "NexusPPT (*.nexusppt);;JSON (*.json);;All Files (*)",
            )
            if not path:
                return
            self._path = path

        self._save_current()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {"title": self._title, "theme": self._theme, "slides": self._slides},
                    f, indent=2, ensure_ascii=False,
                )
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def _export_txt(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as Text", f"{self._title}.txt", "Text Files (*.txt)"
        )
        if not path:
            return
        self._save_current()
        lines = [self._title, "=" * len(self._title), ""]
        for i, slide in enumerate(self._slides):
            lines.append(f"Slide {i + 1}: {slide.get('title', 'Untitled')}")
            lines.append("-" * 40)
            lines.append(slide.get("content", ""))
            if slide.get("notes"):
                lines.append(f"\n[Notes] {slide['notes']}")
            lines.append("")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))
