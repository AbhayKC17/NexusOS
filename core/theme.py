# JobTracker — Fluent Windows Dark 2 Theme
# Inspired by WinUI 3 / Windows App SDK design language
# Accent: Indigo #6366F1  |  Base: #0D0D10  |  Font: Segoe UI Variable / SF Pro Display

# ── Design token constants (used programmatically by widgets) ──────────────────
ACCENT          = "#6366F1"
ACCENT_HOVER    = "#7578F3"
ACCENT_PRESSED  = "#5254CE"
ACCENT_TEXT     = "#A5B4FC"
ACCENT_SUBTLE   = "rgba(99,102,241,0.13)"
ACCENT_DIM      = "rgba(99,102,241,0.28)"

BASE            = "#0D0D10"
SURFACE         = "#13131A"
SURFACE_RAISED  = "#1C1C26"
SIDEBAR_BG      = "#08080D"

TEXT_PRIMARY    = "#EFEFEF"
TEXT_SECONDARY  = "rgba(239,239,239,0.55)"
TEXT_TERTIARY   = "rgba(239,239,239,0.32)"
TEXT_DISABLED   = "rgba(239,239,239,0.24)"

BORDER_SUBTLE   = "rgba(255,255,255,0.06)"
BORDER_NORMAL   = "rgba(255,255,255,0.09)"
BORDER_STRONG   = "rgba(255,255,255,0.14)"

SUCCESS  = "#6CCB5F"
WARNING  = "#FCE100"
ERROR    = "#FF99A4"
INFO     = "#60CDFF"


FLUENT_DARK = f"""

/* ═══════════════════════════════════════════════════════════
   RESET & BASE
   ═══════════════════════════════════════════════════════════ */
* {{
    font-family: 'Segoe UI Variable', 'SF Pro Display', 'Helvetica Neue',
                 -apple-system, Arial;
    font-size: 13px;
    outline: none;
}}
QWidget {{
    background-color: {BASE};
    color: {TEXT_PRIMARY};
}}
QMainWindow, QDialog {{
    background: {BASE};
}}

/* ═══════════════════════════════════════════════════════════
   SIDEBAR — NavigationView-style left rail
   ═══════════════════════════════════════════════════════════ */
QFrame#sidebar {{
    background: {SIDEBAR_BG};
    border-right: 1px solid {BORDER_SUBTLE};
}}

/* App brand area */
QWidget#appBrand {{
    background: transparent;
    border-bottom: 1px solid {BORDER_SUBTLE};
}}
QLabel#appTitle {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 700;
    background: transparent;
    letter-spacing: 0.1px;
}}
QLabel#appSubtitle {{
    color: {TEXT_TERTIARY};
    font-size: 11px;
    background: transparent;
    letter-spacing: 0.1px;
}}

/* Navigation buttons */
QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    text-align: left;
    padding: 9px 14px 9px 18px;
    font-size: 13px;
    margin: 1px 8px;
}}
QPushButton#navBtn:hover {{
    background: rgba(255,255,255,0.055);
    color: rgba(239,239,239,0.9);
}}
QPushButton#navBtn:pressed {{
    background: rgba(255,255,255,0.03);
}}
QPushButton#navBtn[active="true"] {{
    background: {ACCENT_SUBTLE};
    color: {ACCENT_TEXT};
    font-weight: 600;
    border-left: 3px solid {ACCENT};
    padding-left: 15px;
    border-radius: 6px;
}}

/* Sidebar footer status labels */
QLabel#modelStatus {{
    font-size: 11px;
    background: transparent;
    padding: 5px 14px;
}}
QLabel#syncStatus {{
    color: {TEXT_TERTIARY};
    font-size: 11px;
    background: transparent;
    padding: 2px 14px 12px 14px;
}}
QFrame#sidebarDivider {{
    background: {BORDER_SUBTLE};
    max-height: 1px;
    border: none;
    margin: 4px 12px;
}}

/* ═══════════════════════════════════════════════════════════
   PAGE STRUCTURE
   ═══════════════════════════════════════════════════════════ */
QWidget#pageHeader {{
    background: {BASE};
    border-bottom: 1px solid {BORDER_SUBTLE};
}}
QLabel#pageTitle {{
    color: {TEXT_PRIMARY};
    font-size: 22px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.3px;
}}
QLabel#pageSubtitle {{
    color: {TEXT_TERTIARY};
    font-size: 12px;
    background: transparent;
}}

/* ═══════════════════════════════════════════════════════════
   CARDS — three depth levels
   ═══════════════════════════════════════════════════════════ */
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 10px;
}}
QFrame#cardRaised {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 10px;
}}
QFrame#cardElevated {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 10px;
}}
QFrame#statCard {{
    background: {SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 10px;
}}

/* Section headings */
QLabel#sectionHeader,
QLabel#sectionTitle {{
    color: {TEXT_TERTIARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.9px;
    background: transparent;
}}

/* Stat card values */
QLabel#statNumber {{
    color: {TEXT_PRIMARY};
    font-size: 28px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.6px;
}}
QLabel#statDesc {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    background: transparent;
}}
QLabel#statChange {{
    font-size: 11px;
    background: transparent;
}}

/* ═══════════════════════════════════════════════════════════
   TABLES
   ═══════════════════════════════════════════════════════════ */
QTableWidget {{
    background: {SURFACE};
    alternate-background-color: #15151C;
    border: none;
    gridline-color: rgba(255,255,255,0.04);
    selection-background-color: {ACCENT_SUBTLE};
}}
QTableWidget::item {{
    padding: 10px 14px;
    color: {TEXT_PRIMARY};
    border: none;
}}
QTableWidget::item:selected {{
    background: {ACCENT_SUBTLE};
    color: {TEXT_PRIMARY};
}}
QTableWidget::item:hover:!selected {{
    background: rgba(255,255,255,0.03);
}}
QHeaderView {{
    background: {SURFACE};
    border: none;
}}
QHeaderView::section {{
    background: #101018;
    color: {TEXT_TERTIARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    border-right: 1px solid rgba(255,255,255,0.04);
}}
QHeaderView::section:last {{ border-right: none; }}

/* ═══════════════════════════════════════════════════════════
   INPUTS
   ═══════════════════════════════════════════════════════════ */
QLineEdit, QPlainTextEdit {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 8px 12px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid rgba(99,102,241,0.75);
    background: #1F1F2A;
}}
QLineEdit::placeholder {{ color: {TEXT_TERTIARY}; }}

QTextEdit {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 8px 12px;
    selection-background-color: {ACCENT_DIM};
}}
QTextEdit:focus {{ border: 1px solid rgba(99,102,241,0.75); }}

QComboBox {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 7px 12px;
    min-height: 32px;
}}
QComboBox:focus {{ border: 1px solid rgba(99,102,241,0.75); }}
QComboBox::drop-down {{
    border: none;
    width: 28px;
    subcontrol-position: right center;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(239,239,239,0.45);
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    selection-background-color: rgba(99,102,241,0.22);
    selection-color: #FFFFFF;
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    color: {TEXT_PRIMARY};
    background: transparent;
    padding: 6px 12px;
    min-height: 30px;
}}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {{
    background: rgba(99,102,241,0.22);
    color: #FFFFFF;
}}

QSpinBox {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_NORMAL};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 7px 12px;
}}
QSpinBox:focus {{ border: 1px solid rgba(99,102,241,0.75); }}

/* ═══════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════ */
QPushButton {{
    background: rgba(255,255,255,0.055);
    border: 1px solid {BORDER_NORMAL};
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 8px 18px;
    font-size: 13px;
    min-height: 32px;
}}
QPushButton:hover {{
    background: rgba(255,255,255,0.09);
    border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{ background: rgba(255,255,255,0.03); }}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.02);
}}

QPushButton#accentBtn {{
    background: {ACCENT};
    border: none;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 7px;
}}
QPushButton#accentBtn:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#accentBtn:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#accentBtn:disabled {{
    background: {ACCENT_DIM};
    color: rgba(255,255,255,0.38);
}}

QPushButton#dangerBtn {{
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.28);
    color: #FCA5A5;
    border-radius: 7px;
}}
QPushButton#dangerBtn:hover {{ background: rgba(239,68,68,0.18); }}
QPushButton#dangerBtn:pressed {{ background: rgba(239,68,68,0.08); }}

QPushButton#subtleBtn {{
    background: transparent;
    border: none;
    color: {TEXT_SECONDARY};
    border-radius: 7px;
}}
QPushButton#subtleBtn:hover {{
    background: rgba(255,255,255,0.055);
    color: {TEXT_PRIMARY};
}}

/* ═══════════════════════════════════════════════════════════
   CHECKBOXES
   ═══════════════════════════════════════════════════════════ */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.22);
    background: {SURFACE_RAISED};
}}
QCheckBox::indicator:hover {{ border-color: rgba(99,102,241,0.65); }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked:hover {{ background: {ACCENT_HOVER}; }}

/* ═══════════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════════ */
QProgressBar {{
    background: rgba(255,255,255,0.06);
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: rgba(0,0,0,0);
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ═══════════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.10);
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.22); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255,255,255,0.10);
    border-radius: 3px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: rgba(255,255,255,0.22); }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ═══════════════════════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════════════════════ */
QStatusBar {{
    background: {SIDEBAR_BG};
    border-top: 1px solid {BORDER_SUBTLE};
    color: {TEXT_TERTIARY};
    font-size: 11px;
}}

/* ═══════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    background: {SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_TERTIARY};
    padding: 9px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 90px;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: rgba(239,239,239,0.72);
    background: rgba(255,255,255,0.03);
}}
QTabBar {{ background: {SURFACE}; }}

/* ═══════════════════════════════════════════════════════════
   GROUP BOX
   ═══════════════════════════════════════════════════════════ */
QGroupBox {{
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 14px;
    color: {TEXT_TERTIARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background: {BASE};
    color: {TEXT_TERTIARY};
    font-size: 11px;
    font-weight: 700;
}}

/* ═══════════════════════════════════════════════════════════
   SPLITTER
   ═══════════════════════════════════════════════════════════ */
QSplitter::handle {{
    background: {BORDER_SUBTLE};
    width: 1px;
    height: 1px;
}}

/* ═══════════════════════════════════════════════════════════
   DIALOGS
   ═══════════════════════════════════════════════════════════ */
QDialog {{
    background: #15151C;
    border-radius: 12px;
}}
QDialogButtonBox QPushButton {{ min-width: 80px; }}

/* ═══════════════════════════════════════════════════════════
   TABLE CHECKBOXES
   ═══════════════════════════════════════════════════════════ */
QTableWidget::indicator {{
    width: 16px; height: 16px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.22);
    background: {SURFACE_RAISED};
}}
QTableWidget::indicator:hover {{ border-color: rgba(99,102,241,0.65); }}
QTableWidget::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QTableWidget::indicator:checked:hover {{ background: {ACCENT_HOVER}; }}

/* ═══════════════════════════════════════════════════════════
   TOOLTIPS
   ═══════════════════════════════════════════════════════════ */
QToolTip {{
    background: #21212C;
    border: 1px solid {BORDER_STRONG};
    color: {TEXT_PRIMARY};
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════════════════════
   MISC
   ═══════════════════════════════════════════════════════════ */
QLabel {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame#hDivider {{
    background: {BORDER_SUBTLE};
    max-height: 1px;
    border: none;
}}
"""


STATUS_STYLE = {
    "pending":   ("rgba(251,191,36,0.90)",  "rgba(251,191,36,0.10)"),
    "sent":      ("rgba(129,140,248,0.95)", "rgba(99,102,241,0.14)"),
    "replied":   ("rgba(52,211,153,0.95)",  "rgba(16,185,129,0.13)"),
    "rejected":  ("rgba(252,165,165,0.95)", "rgba(239,68,68,0.12)"),
    "offer":     ("rgba(196,181,253,0.95)", "rgba(139,92,246,0.14)"),
    "interview": ("rgba(103,232,249,0.95)", "rgba(6,182,212,0.13)"),
}


# ── Light-mode design tokens ──────────────────────────────────────────────────
ACCENT_L         = "#0067C0"
ACCENT_HOVER_L   = "#0078D4"
ACCENT_PRESSED_L = "#005A9E"
ACCENT_SUBTLE_L  = "rgba(0,103,192,0.10)"

BASE_L           = "#F3F3F3"
SURFACE_L        = "#FFFFFF"
SURFACE_RAISED_L = "#FAFAFA"
SIDEBAR_BG_L     = "#F0F0F0"

TEXT_PRIMARY_L   = "#1A1A1A"
TEXT_SECONDARY_L = "rgba(0,0,0,0.55)"
TEXT_TERTIARY_L  = "rgba(0,0,0,0.38)"
TEXT_DISABLED_L  = "rgba(0,0,0,0.26)"

BORDER_SUBTLE_L  = "rgba(0,0,0,0.07)"
BORDER_NORMAL_L  = "rgba(0,0,0,0.12)"
BORDER_STRONG_L  = "rgba(0,0,0,0.18)"

SUCCESS_L  = "#107C10"
WARNING_L  = "#9D5D00"
ERROR_L    = "#C42B1C"
INFO_L     = "#0067C0"


FLUENT_LIGHT = f"""

/* ═══════════════════════════════════════════════════════════
   RESET & BASE
   ═══════════════════════════════════════════════════════════ */
* {{
    font-family: 'Segoe UI Variable', 'SF Pro Display', 'Helvetica Neue',
                 -apple-system, Arial;
    font-size: 13px;
    outline: none;
}}
QWidget {{
    background-color: {BASE_L};
    color: {TEXT_PRIMARY_L};
}}
QMainWindow, QDialog {{
    background: {BASE_L};
}}

/* ═══════════════════════════════════════════════════════════
   SIDEBAR
   ═══════════════════════════════════════════════════════════ */
QFrame#sidebar {{
    background: {SIDEBAR_BG_L};
    border-right: 1px solid {BORDER_SUBTLE_L};
}}
QWidget#appBrand {{
    background: transparent;
    border-bottom: 1px solid {BORDER_SUBTLE_L};
}}
QLabel#appTitle {{
    color: {TEXT_PRIMARY_L};
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}}
QLabel#appSubtitle {{
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    background: transparent;
}}

/* Navigation buttons */
QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_SECONDARY_L};
    text-align: left;
    padding: 9px 14px 9px 18px;
    font-size: 13px;
    margin: 1px 8px;
}}
QPushButton#navBtn:hover {{
    background: rgba(0,0,0,0.04);
    color: {TEXT_PRIMARY_L};
}}
QPushButton#navBtn:pressed {{
    background: rgba(0,0,0,0.07);
}}
QPushButton#navBtn[active="true"] {{
    background: {ACCENT_SUBTLE_L};
    color: {ACCENT_L};
    font-weight: 600;
    border-left: 3px solid {ACCENT_L};
    padding-left: 15px;
    border-radius: 6px;
}}

QLabel#modelStatus {{
    font-size: 11px;
    background: transparent;
    padding: 5px 14px;
}}
QLabel#syncStatus {{
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    background: transparent;
    padding: 2px 14px 12px 14px;
}}
QFrame#sidebarDivider {{
    background: {BORDER_SUBTLE_L};
    max-height: 1px;
    border: none;
    margin: 4px 12px;
}}

/* ═══════════════════════════════════════════════════════════
   PAGE STRUCTURE
   ═══════════════════════════════════════════════════════════ */
QWidget#pageHeader {{
    background: {SURFACE_L};
    border-bottom: 1px solid {BORDER_SUBTLE_L};
}}
QLabel#pageTitle {{
    color: {TEXT_PRIMARY_L};
    font-size: 22px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.3px;
}}
QLabel#pageSubtitle {{
    color: {TEXT_TERTIARY_L};
    font-size: 12px;
    background: transparent;
}}

/* ═══════════════════════════════════════════════════════════
   CARDS
   ═══════════════════════════════════════════════════════════ */
QFrame#card, QFrame#statCard {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_SUBTLE_L};
    border-radius: 10px;
}}
QFrame#cardRaised, QFrame#cardElevated {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 10px;
}}
QLabel#sectionHeader, QLabel#sectionTitle {{
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.9px;
    background: transparent;
}}
QLabel#statNumber {{
    color: {TEXT_PRIMARY_L};
    font-size: 28px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.6px;
}}
QLabel#statDesc {{
    color: {TEXT_SECONDARY_L};
    font-size: 12px;
    background: transparent;
}}
QLabel#statChange {{ font-size: 11px; background: transparent; }}

/* ═══════════════════════════════════════════════════════════
   TABLES
   ═══════════════════════════════════════════════════════════ */
QTableWidget {{
    background: {SURFACE_L};
    alternate-background-color: #F8F8F8;
    border: none;
    gridline-color: rgba(0,0,0,0.05);
    selection-background-color: {ACCENT_SUBTLE_L};
}}
QTableWidget::item {{
    padding: 10px 14px;
    color: {TEXT_PRIMARY_L};
    border: none;
}}
QTableWidget::item:selected {{
    background: {ACCENT_SUBTLE_L};
    color: {TEXT_PRIMARY_L};
}}
QTableWidget::item:hover:!selected {{ background: rgba(0,0,0,0.025); }}
QHeaderView {{ background: {SURFACE_L}; border: none; }}
QHeaderView::section {{
    background: #F5F5F5;
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE_L};
    border-right: 1px solid rgba(0,0,0,0.04);
}}
QHeaderView::section:last {{ border-right: none; }}

/* ═══════════════════════════════════════════════════════════
   INPUTS
   ═══════════════════════════════════════════════════════════ */
QLineEdit, QPlainTextEdit {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    padding: 8px 12px;
    selection-background-color: rgba(0,103,192,0.20);
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT_L};
    background: {SURFACE_L};
}}
QLineEdit::placeholder {{ color: {TEXT_TERTIARY_L}; }}
QTextEdit {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    padding: 8px 12px;
    selection-background-color: rgba(0,103,192,0.20);
}}
QTextEdit:focus {{ border: 1px solid {ACCENT_L}; }}
QComboBox {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    padding: 7px 12px;
    min-height: 32px;
}}
QComboBox:focus {{ border: 1px solid {ACCENT_L}; }}
QComboBox::drop-down {{ border: none; width: 28px; subcontrol-position: right center; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(0,0,0,0.42);
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_STRONG_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    selection-background-color: {ACCENT_SUBTLE_L};
    selection-color: {ACCENT_L};
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    color: {TEXT_PRIMARY_L};
    background: transparent;
    padding: 6px 12px;
    min-height: 30px;
}}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {{
    background: {ACCENT_SUBTLE_L};
    color: {ACCENT_L};
}}
QSpinBox {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    padding: 7px 12px;
}}
QSpinBox:focus {{ border: 1px solid {ACCENT_L}; }}

/* ═══════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════ */
QPushButton {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_NORMAL_L};
    border-radius: 7px;
    color: {TEXT_PRIMARY_L};
    padding: 8px 18px;
    font-size: 13px;
    min-height: 32px;
}}
QPushButton:hover {{
    background: #F0F0F0;
    border-color: {BORDER_STRONG_L};
}}
QPushButton:pressed {{ background: #E8E8E8; }}
QPushButton:disabled {{
    color: {TEXT_DISABLED_L};
    border-color: rgba(0,0,0,0.06);
    background: #F5F5F5;
}}
QPushButton#accentBtn {{
    background: {ACCENT_L};
    border: none;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 7px;
}}
QPushButton#accentBtn:hover {{ background: {ACCENT_HOVER_L}; }}
QPushButton#accentBtn:pressed {{ background: {ACCENT_PRESSED_L}; }}
QPushButton#accentBtn:disabled {{
    background: rgba(0,103,192,0.28);
    color: rgba(255,255,255,0.48);
}}
QPushButton#dangerBtn {{
    background: rgba(196,43,28,0.06);
    border: 1px solid rgba(196,43,28,0.22);
    color: {ERROR_L};
    border-radius: 7px;
}}
QPushButton#dangerBtn:hover {{ background: rgba(196,43,28,0.12); }}
QPushButton#dangerBtn:pressed {{ background: rgba(196,43,28,0.06); }}
QPushButton#subtleBtn {{
    background: transparent;
    border: none;
    color: {TEXT_SECONDARY_L};
    border-radius: 7px;
}}
QPushButton#subtleBtn:hover {{
    background: rgba(0,0,0,0.05);
    color: {TEXT_PRIMARY_L};
}}

/* ═══════════════════════════════════════════════════════════
   CHECKBOXES
   ═══════════════════════════════════════════════════════════ */
QCheckBox {{
    color: {TEXT_PRIMARY_L};
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG_L};
    background: {SURFACE_L};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_L}; }}
QCheckBox::indicator:checked {{ background: {ACCENT_L}; border-color: {ACCENT_L}; }}
QCheckBox::indicator:checked:hover {{ background: {ACCENT_HOVER_L}; }}

/* ═══════════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════════ */
QProgressBar {{
    background: rgba(0,0,0,0.08);
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT_L}; border-radius: 3px; }}

/* ═══════════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════════ */
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: rgba(0,0,0,0.14);
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(0,0,0,0.26); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 6px; }}
QScrollBar::handle:horizontal {{ background: rgba(0,0,0,0.14); border-radius: 3px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: rgba(0,0,0,0.26); }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ═══════════════════════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════════════════════ */
QStatusBar {{
    background: {SIDEBAR_BG_L};
    border-top: 1px solid {BORDER_SUBTLE_L};
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
}}

/* ═══════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_SUBTLE_L};
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_TERTIARY_L};
    padding: 9px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 90px;
    font-size: 13px;
}}
QTabBar::tab:selected {{ color: {ACCENT_L}; border-bottom: 2px solid {ACCENT_L}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT_SECONDARY_L}; background: rgba(0,0,0,0.03); }}
QTabBar {{ background: {SURFACE_L}; }}

/* ═══════════════════════════════════════════════════════════
   GROUP BOX
   ═══════════════════════════════════════════════════════════ */
QGroupBox {{
    border: 1px solid {BORDER_SUBTLE_L};
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 14px;
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background: {BASE_L};
    color: {TEXT_TERTIARY_L};
    font-size: 11px;
    font-weight: 700;
}}

/* ═══════════════════════════════════════════════════════════
   SPLITTER / DIALOGS / MISC
   ═══════════════════════════════════════════════════════════ */
QSplitter::handle {{ background: {BORDER_SUBTLE_L}; width: 1px; height: 1px; }}
QDialog {{ background: {SURFACE_L}; border-radius: 12px; }}
QDialogButtonBox QPushButton {{ min-width: 80px; }}
QTableWidget::indicator {{
    width: 16px; height: 16px;
    border-radius: 3px;
    border: 1px solid {BORDER_STRONG_L};
    background: {SURFACE_L};
}}
QTableWidget::indicator:hover {{ border-color: {ACCENT_L}; }}
QTableWidget::indicator:checked {{ background: {ACCENT_L}; border-color: {ACCENT_L}; }}
QTableWidget::indicator:checked:hover {{ background: {ACCENT_HOVER_L}; }}
QToolTip {{
    background: {SURFACE_L};
    border: 1px solid {BORDER_STRONG_L};
    color: {TEXT_PRIMARY_L};
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
}}
QLabel {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame#hDivider {{ background: {BORDER_SUBTLE_L}; max-height: 1px; border: none; }}
"""
