# Backwards-compatibility shim — real definitions live in core/theme.py
from core.theme import FLUENT_DARK, STATUS_STYLE  # noqa: F401

_FLUENT_DARK_LEGACY = """

/* ════════════════════════════════════════════════════════
   RESET & BASE
   ════════════════════════════════════════════════════════ */
* {
    font-family: 'SF Pro Display', 'Helvetica Neue', -apple-system, Arial;
    font-size: 13px;
    outline: none;
}
QWidget {
    background-color: #0D0D10;
    color: #EFEFEF;
}
QMainWindow, QDialog {
    background: #0D0D10;
}

/* ════════════════════════════════════════════════════════
   SIDEBAR
   ════════════════════════════════════════════════════════ */
QFrame#sidebar {
    background: #090910;
    border-right: 1px solid rgba(255,255,255,0.06);
}
QLabel#appTitle {
    color: #EFEFEF;
    font-size: 14px;
    font-weight: 700;
    background: transparent;
    letter-spacing: 0.2px;
}
QLabel#appSubtitle {
    color: rgba(239,239,239,0.32);
    font-size: 11px;
    background: transparent;
    letter-spacing: 0.1px;
}

/* Nav buttons */
QPushButton#navBtn {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: rgba(239,239,239,0.52);
    text-align: left;
    padding: 9px 14px;
    font-size: 13px;
    margin: 0 8px;
}
QPushButton#navBtn:hover {
    background: rgba(255,255,255,0.05);
    color: rgba(239,239,239,0.9);
}
QPushButton#navBtn[active="true"] {
    background: rgba(99,102,241,0.13);
    color: #A5B4FC;
    font-weight: 600;
    border-left: 2px solid #6366F1;
    padding-left: 12px;
}

/* ════════════════════════════════════════════════════════
   PAGE HEADER
   ════════════════════════════════════════════════════════ */
QWidget#pageHeader {
    background: #0D0D10;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
QLabel#pageTitle {
    color: #EFEFEF;
    font-size: 20px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.3px;
}
QLabel#pageSubtitle {
    color: rgba(239,239,239,0.42);
    font-size: 12px;
    background: transparent;
}

/* ════════════════════════════════════════════════════════
   CARDS
   ════════════════════════════════════════════════════════ */
QFrame#card {
    background: #13131A;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
}
QFrame#cardElevated {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 10px;
}

/* Section headings */
QLabel#sectionHeader {
    color: rgba(239,239,239,0.38);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.9px;
    background: transparent;
}
QLabel#sectionTitle {
    color: rgba(239,239,239,0.38);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.9px;
    background: transparent;
}

/* ════════════════════════════════════════════════════════
   STAT CARDS
   ════════════════════════════════════════════════════════ */
QFrame#statCard {
    background: #13131A;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
}
QLabel#statNumber {
    color: #EFEFEF;
    font-size: 28px;
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.6px;
}
QLabel#statDesc {
    color: rgba(239,239,239,0.42);
    font-size: 12px;
    background: transparent;
}
QLabel#statChange {
    font-size: 11px;
    background: transparent;
}

/* ════════════════════════════════════════════════════════
   TABLES
   ════════════════════════════════════════════════════════ */
QTableWidget {
    background: #13131A;
    alternate-background-color: #16161E;
    border: none;
    gridline-color: rgba(255,255,255,0.04);
    selection-background-color: rgba(99,102,241,0.16);
}
QTableWidget::item {
    padding: 10px 14px;
    color: #EFEFEF;
    border: none;
}
QTableWidget::item:selected {
    background: rgba(99,102,241,0.16);
    color: #EFEFEF;
}
QTableWidget::item:hover:!selected {
    background: rgba(255,255,255,0.03);
}
QHeaderView {
    background: #13131A;
    border: none;
}
QHeaderView::section {
    background: #101016;
    color: rgba(239,239,239,0.38);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    border-right: 1px solid rgba(255,255,255,0.04);
}
QHeaderView::section:last { border-right: none; }

/* ════════════════════════════════════════════════════════
   INPUTS
   ════════════════════════════════════════════════════════ */
QLineEdit, QPlainTextEdit {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 7px;
    color: #EFEFEF;
    padding: 8px 12px;
    selection-background-color: rgba(99,102,241,0.35);
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid rgba(99,102,241,0.8);
    background: #1E1E2C;
}
QLineEdit::placeholder { color: rgba(239,239,239,0.26); }

QTextEdit {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 7px;
    color: #EFEFEF;
    padding: 8px 12px;
    selection-background-color: rgba(99,102,241,0.35);
}
QTextEdit:focus { border: 1px solid rgba(99,102,241,0.8); }

QComboBox {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 7px;
    color: #EFEFEF;
    padding: 7px 12px;
    min-height: 32px;
}
QComboBox:focus { border: 1px solid rgba(99,102,241,0.8); }
QComboBox::drop-down {
    border: none;
    width: 28px;
    subcontrol-position: right center;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(239,239,239,0.45);
    width: 0; height: 0;
}
QComboBox QAbstractItemView {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 7px;
    color: #EFEFEF;
    selection-background-color: rgba(99,102,241,0.22);
    outline: none;
}

QSpinBox {
    background: #1A1A24;
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 7px;
    color: #EFEFEF;
    padding: 7px 12px;
}
QSpinBox:focus { border: 1px solid rgba(99,102,241,0.8); }

/* ════════════════════════════════════════════════════════
   BUTTONS
   ════════════════════════════════════════════════════════ */
QPushButton {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 7px;
    color: #EFEFEF;
    padding: 8px 18px;
    font-size: 13px;
    min-height: 32px;
}
QPushButton:hover {
    background: rgba(255,255,255,0.09);
    border-color: rgba(255,255,255,0.14);
}
QPushButton:pressed { background: rgba(255,255,255,0.03); }
QPushButton:disabled {
    color: rgba(239,239,239,0.24);
    border-color: rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.02);
}

QPushButton#accentBtn {
    background: #6366F1;
    border: none;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton#accentBtn:hover { background: #7578F3; }
QPushButton#accentBtn:pressed { background: #5254CE; }
QPushButton#accentBtn:disabled {
    background: rgba(99,102,241,0.28);
    color: rgba(255,255,255,0.38);
}

QPushButton#dangerBtn {
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.28);
    color: #FCA5A5;
}
QPushButton#dangerBtn:hover { background: rgba(239,68,68,0.18); }
QPushButton#dangerBtn:pressed { background: rgba(239,68,68,0.08); }

QPushButton#subtleBtn {
    background: transparent;
    border: none;
    color: rgba(239,239,239,0.55);
}
QPushButton#subtleBtn:hover {
    background: rgba(255,255,255,0.05);
    color: #EFEFEF;
}

/* ════════════════════════════════════════════════════════
   CHECKBOXES
   ════════════════════════════════════════════════════════ */
QCheckBox {
    color: #EFEFEF;
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator {
    width: 17px; height: 17px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.22);
    background: #1A1A24;
}
QCheckBox::indicator:hover { border-color: rgba(99,102,241,0.65); }
QCheckBox::indicator:checked {
    background: #6366F1;
    border-color: #6366F1;
}
QCheckBox::indicator:checked:hover { background: #7578F3; }

/* ════════════════════════════════════════════════════════
   PROGRESS BAR
   ════════════════════════════════════════════════════════ */
QProgressBar {
    background: rgba(255,255,255,0.06);
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: rgba(0,0,0,0);
}
QProgressBar::chunk {
    background: #6366F1;
    border-radius: 3px;
}

/* ════════════════════════════════════════════════════════
   SCROLLBARS
   ════════════════════════════════════════════════════════ */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.10);
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.20); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
}
QScrollBar::handle:horizontal {
    background: rgba(255,255,255,0.10);
    border-radius: 3px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ════════════════════════════════════════════════════════
   STATUS BAR
   ════════════════════════════════════════════════════════ */
QStatusBar {
    background: #090910;
    border-top: 1px solid rgba(255,255,255,0.05);
    color: rgba(239,239,239,0.36);
    font-size: 11px;
}

/* ════════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════════ */
QTabWidget::pane {
    background: #13131A;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: rgba(239,239,239,0.42);
    padding: 9px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 90px;
    font-size: 13px;
}
QTabBar::tab:selected {
    color: #EFEFEF;
    border-bottom: 2px solid #6366F1;
}
QTabBar::tab:hover:!selected {
    color: rgba(239,239,239,0.72);
    background: rgba(255,255,255,0.03);
}
QTabBar { background: #13131A; }

/* ════════════════════════════════════════════════════════
   GROUP BOX
   ════════════════════════════════════════════════════════ */
QGroupBox {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 12px;
    color: rgba(239,239,239,0.38);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background: #0D0D10;
    color: rgba(239,239,239,0.38);
    font-size: 11px;
    font-weight: 700;
}

/* ════════════════════════════════════════════════════════
   SPLITTER
   ════════════════════════════════════════════════════════ */
QSplitter::handle {
    background: rgba(255,255,255,0.05);
    width: 1px;
    height: 1px;
}

/* ════════════════════════════════════════════════════════
   DIALOGS
   ════════════════════════════════════════════════════════ */
QDialog {
    background: #13131A;
    border-radius: 12px;
}
QDialogButtonBox QPushButton { min-width: 80px; }

/* ════════════════════════════════════════════════════════
   TABLE CHECKBOXES
   ════════════════════════════════════════════════════════ */
QTableWidget::indicator {
    width: 16px; height: 16px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.22);
    background: #1A1A24;
}
QTableWidget::indicator:hover { border-color: rgba(99,102,241,0.65); }
QTableWidget::indicator:checked {
    background: #6366F1;
    border-color: #6366F1;
}
QTableWidget::indicator:checked:hover { background: #7578F3; }

/* ════════════════════════════════════════════════════════
   TOOLTIPS
   ════════════════════════════════════════════════════════ */
QToolTip {
    background: #1E1E2C;
    border: 1px solid rgba(255,255,255,0.12);
    color: #EFEFEF;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
}

/* ════════════════════════════════════════════════════════
   MISC
   ════════════════════════════════════════════════════════ */
QLabel { background: transparent; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""


# STATUS_STYLE re-exported via the import at the top of this file.
