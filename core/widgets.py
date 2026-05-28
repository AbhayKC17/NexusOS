"""
Shared UI components — single source of truth.
Import these instead of defining helpers locally in each page.
"""
from PyQt6.QtWidgets import (
    QFrame, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt
from core.theme import STATUS_STYLE


# ── StatCard ──────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    """KPI card: accent dot · large number · label · optional sub-text."""

    def __init__(self, value, label: str, accent: str = "#6366F1",
                 sub: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(120)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent}; font-size: 9px; background: transparent;")
        lay.addWidget(dot)

        val = QLabel(str(value))
        val.setStyleSheet(
            f"color: {accent}; font-size: 26px; font-weight: 700; background: transparent;"
        )
        lay.addWidget(val)

        lbl = QLabel(label)
        lbl.setObjectName("statDesc")
        lay.addWidget(lbl)

        if sub:
            s = QLabel(sub)
            s.setStyleSheet(
                "color: rgba(255,255,255,0.3); font-size: 11px; background: transparent;"
            )
            lay.addWidget(s)


# ── StatusBadge ───────────────────────────────────────────────────────────────

class StatusBadge(QLabel):
    """Coloured status pill (pending / sent / replied / …)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        fg, bg = STATUS_STYLE.get(text, ("#EFEFEF", "rgba(255,255,255,0.10)"))
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 4px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)


# ── SectionHeader ─────────────────────────────────────────────────────────────

class SectionHeader(QWidget):
    """Row with a small-caps section label and an optional right-side widget."""

    def __init__(self, title: str, right_widget=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lbl = QLabel(title.upper())
        lbl.setObjectName("sectionTitle")
        lay.addWidget(lbl)
        lay.addStretch()

        if right_widget:
            lay.addWidget(right_widget)


# ── PageHeader ────────────────────────────────────────────────────────────────

class PageHeader(QWidget):
    """Standard page title + optional subtitle, with a right-side action slot."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 16)
        outer.setSpacing(0)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.titleLabel = QLabel(title)
        self.titleLabel.setObjectName("pageTitle")
        text_col.addWidget(self.titleLabel)

        if subtitle:
            self.subtitleLabel = QLabel(subtitle)
            self.subtitleLabel.setObjectName("pageSubtitle")
            text_col.addWidget(self.subtitleLabel)

        outer.addLayout(text_col)
        outer.addStretch()

        # Caller can insert buttons here
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        outer.addLayout(self._actions)

    def add_action(self, widget):
        """Append a widget (usually QPushButton) to the right side of the header."""
        self._actions.addWidget(widget)


# ── EmptyState ────────────────────────────────────────────────────────────────

class EmptyState(QLabel):
    """Centred placeholder label for empty lists / tables."""

    def __init__(self, message: str, parent=None):
        super().__init__(message, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            "color: rgba(255,255,255,0.30); font-size: 13px; background: transparent; padding: 32px;"
        )
