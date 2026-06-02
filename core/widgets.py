"""
Shared UI components — single source of truth for NexusOS + JobTracker.
All widgets match the Fluent Light design language.
"""
from PyQt6.QtWidgets import (
    QFrame, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy, QStackedWidget, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtProperty,
    QSequentialAnimationGroup, QPauseAnimation, QPoint,
)
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont

from core.theme import (
    STATUS_STYLE,
    ACCENT_L, ACCENT_SUBTLE_L, TEXT_TERTIARY_L, TEXT_SECONDARY_L,
    TEXT_PRIMARY_L, SURFACE_L, BORDER_SUBTLE_L, SHADOW_CARD,
)


# ── Shadow helper ─────────────────────────────────────────────────────────────

def _apply_shadow(widget, blur=16, offset=(0, 2), alpha=18):
    """Attach a subtle drop shadow (QGraphicsDropShadowEffect) to widget."""
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setColor(QColor(0, 0, 0, alpha))
    fx.setOffset(*offset)
    widget.setGraphicsEffect(fx)
    return fx


# ── ShadowCard ────────────────────────────────────────────────────────────────

class ShadowCard(QFrame):
    """
    A white card with a soft drop shadow — the Fluent Light card primitive.
    Use objectName="card" / "cardRaised" / "statCard" to vary the QSS border/bg.
    """

    def __init__(self, shadow_level: str = "card", radius: int = 10, parent=None):
        super().__init__(parent)
        self.setObjectName(shadow_level)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cfg = {
            "card":     SHADOW_CARD,
            "raised":   {"blur": 22, "offset": (0, 3), "alpha": 22},
            "elevated": {"blur": 32, "offset": (0, 5), "alpha": 28},
        }.get(shadow_level, SHADOW_CARD)
        _apply_shadow(self, **cfg)


# ── StatCard ──────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    """
    KPI card: coloured accent bar on top · large number · label · optional sub.
    Features a subtle drop shadow for depth.
    """

    def __init__(self, value, label: str, accent: str = ACCENT_L,
                 sub: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(120)
        _apply_shadow(self, blur=12, offset=(0, 1), alpha=14)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Coloured accent strip at top
        strip = QFrame()
        strip.setFixedHeight(3)
        strip.setStyleSheet(
            f"background: {accent}; border-radius: 0px; "
            f"border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        layout.addWidget(strip)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 14, 18, 16)
        bl.setSpacing(3)

        val_lbl = QLabel(str(value))
        val_lbl.setStyleSheet(
            f"color: {accent}; font-size: 28px; font-weight: 700; "
            f"background: transparent; letter-spacing: -0.8px;"
        )
        bl.addWidget(val_lbl)

        name_lbl = QLabel(label)
        name_lbl.setObjectName("statDesc")
        bl.addWidget(name_lbl)

        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet(
                f"color: {TEXT_TERTIARY_L}; font-size: 11px; background: transparent;"
            )
            bl.addWidget(sub_lbl)

        layout.addWidget(body)


# ── StatusBadge ───────────────────────────────────────────────────────────────

class StatusBadge(QLabel):
    """Pill-shaped coloured status tag (pending / sent / replied / …)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text.capitalize(), parent)
        fg, bg = STATUS_STYLE.get(text, (TEXT_SECONDARY_L, ACCENT_SUBTLE_L))
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 10px; "
            f"padding: 2px 10px; font-size: 11px; font-weight: 600;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)


# ── SectionHeader ─────────────────────────────────────────────────────────────

class SectionHeader(QWidget):
    """Small-caps section label with optional right-side widget."""

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
    """Standard page title + optional subtitle, with right-side action slot."""

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

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        outer.addLayout(self._actions)

    def add_action(self, widget):
        self._actions.addWidget(widget)


# ── EmptyState ────────────────────────────────────────────────────────────────

class EmptyState(QWidget):
    """Centred empty-state block with icon and message."""

    def __init__(self, message: str, icon: str = "○", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 40, 32, 40)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ico = QLabel(icon)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet(
            f"color: {TEXT_TERTIARY_L}; font-size: 28px; background: transparent;"
        )
        lay.addWidget(ico)

        msg = QLabel(message)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {TEXT_TERTIARY_L}; font-size: 13px; background: transparent;"
        )
        lay.addWidget(msg)


# ── ChipLabel ─────────────────────────────────────────────────────────────────

class ChipLabel(QLabel):
    """Inline tag chip — used for countries, categories, and tags."""

    def __init__(self, text: str, color: str = ACCENT_L,
                 bg: str = None, parent=None):
        super().__init__(text, parent)
        bg = bg or f"rgba(0,103,192,0.08)"
        self.setStyleSheet(
            f"color: {color}; background: {bg}; border-radius: 10px; "
            f"padding: 3px 10px; font-size: 11px; font-weight: 600;"
        )


# ── FadeStackedWidget ─────────────────────────────────────────────────────────

class FadeStackedWidget(QStackedWidget):
    """
    QStackedWidget with a smooth 150ms fade between pages.
    Drop-in replacement for QStackedWidget.
    """

    def __init__(self, duration: int = 160, parent=None):
        super().__init__(parent)
        self._duration = duration
        self._next_idx = 0

        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self._opacity_fx.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_fx)

        self._fade_out = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_out.setDuration(self._duration // 2)
        self._fade_out.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self._on_fade_out_done)

        self._fade_in = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_in.setDuration(self._duration // 2)
        self._fade_in.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

    def setCurrentIndex(self, idx: int):
        if idx == self.currentIndex():
            return
        self._next_idx = idx
        self._fade_out.stop()
        self._fade_in.stop()
        self._fade_out.start()

    def _on_fade_out_done(self):
        super().setCurrentIndex(self._next_idx)
        self._fade_in.start()

    # Allow direct page switch without animation (e.g. on startup)
    def setCurrentIndexInstant(self, idx: int):
        super().setCurrentIndex(idx)
        self._opacity_fx.setOpacity(1.0)


# ── AnimatedProgressBar ───────────────────────────────────────────────────────

class AnimatedProgressBar(QWidget):
    """Thin horizontal progress bar that animates to a target value."""

    def __init__(self, height: int = 4, color: str = ACCENT_L, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._color = color
        self._value = 0.0

    @pyqtProperty(float)
    def fill(self):
        return self._value

    @fill.setter
    def fill(self, v: float):
        self._value = max(0.0, min(1.0, v))
        self.update()

    def set_value(self, fraction: float, animate: bool = True):
        if not animate:
            self._value = fraction
            self.update()
            return
        anim = QPropertyAnimation(self, b"fill")
        anim.setDuration(500)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self._value)
        anim.setEndValue(max(0.0, min(1.0, fraction)))
        anim.start()
        self._anim = anim  # keep reference

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        # Track
        p.setBrush(QBrush(QColor(0, 0, 0, 18)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 2, 2)
        # Fill
        if self._value > 0:
            fill_w = max(8, int(r.width() * self._value))
            fill_r = r.adjusted(0, 0, fill_w - r.width(), 0)
            p.setBrush(QBrush(QColor(self._color)))
            p.drawRoundedRect(fill_r, 2, 2)
        p.end()


# ── SkeletonLoader ────────────────────────────────────────────────────────────

class SkeletonLine(QWidget):
    """Animated shimmer placeholder for loading states."""

    def __init__(self, width_hint: int = 200, height: int = 14, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMaximumWidth(width_hint)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "background: rgba(0,0,0,0.07); border-radius: 4px;"
        )
