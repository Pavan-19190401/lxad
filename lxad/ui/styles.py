"""
Ultra-Modern Jet-Black Linear/Vercel Aesthetic Theme for LXAD.
Inspired by sleek developer tools with matte jet-black surfaces,
subtle low-contrast borders, rounded card containers, and clean tab underlines.
"""

JET_BLACK_THEME_QSS = """
/* Global Window & Base Surfaces */
QMainWindow, QDialog, QWidget#centralWidget {
    background-color: #08090a;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: transparent;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

/* Linear-style Tab Bar */
QTabWidget::pane {
    border: none;
    background-color: #08090a;
    margin-top: 0px;
}

QTabBar {
    background-color: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

QTabBar::tab {
    background-color: transparent;
    color: #7d8590;
    border: none;
    padding: 10px 18px;
    margin-right: 8px;
    font-weight: 500;
    font-size: 13px;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:selected {
    color: #ffffff;
    font-weight: 600;
    border-bottom: 2px solid #ffffff;
}

QTabBar::tab:hover:!selected {
    color: #c9d1d9;
}

/* Rounded Matte Card Panels (as in user screenshot) */
QGroupBox {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    margin-top: 18px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    font-size: 13px;
    color: #f0f2f5;
    background-color: #101214;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    left: 14px;
    color: #e6edf3;
    background-color: #101214;
    border-radius: 4px;
}

/* Card Containers & Framed Panels */
QFrame.card-panel {
    background-color: #101214;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
}

QFrame.inner-card-item {
    background-color: #16181b;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 10px;
}

QFrame.inner-card-item:hover {
    background-color: #1b1e22;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

/* Action Buttons */
QPushButton {
    background-color: #16181b;
    color: #f0f2f5;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #212429;
    border-color: rgba(255, 255, 255, 0.2);
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #121417;
}

QPushButton.primary {
    background-color: #ffffff;
    color: #08090a;
    border: 1px solid #ffffff;
    font-weight: 600;
}

QPushButton.primary:hover {
    background-color: #e6edf3;
    border-color: #e6edf3;
}

QPushButton.danger {
    background-color: rgba(248, 81, 73, 0.15);
    color: #f85149;
    border: 1px solid rgba(248, 81, 73, 0.3);
}

QPushButton.danger:hover {
    background-color: rgba(248, 81, 73, 0.25);
    border-color: #f85149;
}

QPushButton.inject {
    background-color: #16181b;
    color: #c9d1d9;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

QPushButton.inject:hover {
    background-color: #22262c;
    border-color: rgba(255, 255, 255, 0.2);
    color: #ffffff;
}

/* Tables & Data Grids */
QTableWidget {
    background-color: #101214;
    border: 1px solid rgba(255, 255, 255, 0.08);
    gridline-color: rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    selection-background-color: #1c2128;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #101214;
    color: #7d8590;
    padding: 8px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QTableWidget QTableCornerButton::section {
    background-color: #101214;
    border: none;
}

/* ==========================================================
   AESTHETIC INPUT BOXES (Blender / Linear / Vercel Inset Style)
   ========================================================== */
QLineEdit {
    background-color: #0f1115;
    border: 1px solid #23272e;
    border-top: 1px solid #1e2227;
    border-radius: 6px;
    color: #f0f3f6;
    padding: 7px 12px;
    font-size: 12px;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}

QLineEdit:hover {
    background-color: #13161b;
    border-color: #383e4a;
}

QLineEdit:focus {
    background-color: #15181f;
    border: 1px solid #58a6ff;
    color: #ffffff;
}

/* Multi-line Editors */
QTextEdit, QPlainTextEdit {
    background-color: #0c0e12;
    border: 1px solid #21252d;
    border-radius: 6px;
    color: #e6edf3;
    padding: 10px 12px;
    font-size: 12px;
    line-height: 1.5;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}

QTextEdit:hover, QPlainTextEdit:hover {
    border-color: #333945;
}

QTextEdit:focus, QPlainTextEdit:focus {
    background-color: #101217;
    border: 1px solid #58a6ff;
}

/* Aesthetic SpinBoxes (Numeric & Decimal Inputs) */
QSpinBox, QDoubleSpinBox {
    background-color: #0f1115;
    border: 1px solid #23272e;
    border-radius: 6px;
    color: #f0f3f6;
    padding: 6px 26px 6px 10px;
    font-size: 12px;
    font-weight: 500;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}

QSpinBox:hover, QDoubleSpinBox:hover {
    background-color: #13161b;
    border-color: #383e4a;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    background-color: #15181f;
    border: 1px solid #58a6ff;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 14px;
    border-left: 1px solid #23272e;
    border-bottom: 1px solid #1e2228;
    border-top-right-radius: 5px;
    background-color: #171a21;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #262c37;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 14px;
    border-left: 1px solid #23272e;
    border-bottom-right-radius: 5px;
    background-color: #171a21;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #262c37;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid #8b949e;
}

QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {
    border-bottom-color: #ffffff;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #8b949e;
}

QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {
    border-top-color: #ffffff;
}

/* ==========================================================
   AESTHETIC DROPDOWNS & MENUS (Blender / Linear Pill Style)
   ========================================================== */
QComboBox {
    background-color: #121418;
    border: 1px solid #262b33;
    border-radius: 6px;
    color: #f0f3f6;
    padding: 6px 30px 6px 12px;
    font-size: 12px;
    font-weight: 500;
}

QComboBox:hover {
    background-color: #171a20;
    border-color: #3c434f;
    color: #ffffff;
}

QComboBox:focus {
    background-color: #181c22;
    border: 1px solid #58a6ff;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #242932;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: rgba(255, 255, 255, 0.02);
}

QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8b949e;
    margin-right: 2px;
}

QComboBox::down-arrow:hover {
    border-top-color: #58a6ff;
}

/* Floating Dropdown Popup List */
QComboBox QAbstractItemView {
    background-color: #14171d;
    border: 1px solid #2e3440;
    border-radius: 8px;
    color: #f0f3f6;
    padding: 4px;
    outline: none;
    selection-background-color: #242b38;
    selection-color: #58a6ff;
}

QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 5px 12px;
    border-radius: 5px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #1d222c;
    color: #ffffff;
}

QComboBox QAbstractItemView::item:selected {
    background-color: #242b38;
    color: #58a6ff;
    font-weight: 600;
}

/* Floating Action / Context Menus */
QMenu {
    background-color: #14171d;
    border: 1px solid #2e3440;
    border-radius: 8px;
    padding: 6px;
    color: #f0f3f6;
    font-size: 12px;
}

QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 5px;
    margin: 1px 0px;
}

QMenu::item:selected {
    background-color: #242b38;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: rgba(255, 255, 255, 0.07);
    margin: 4px 6px;
}


/* Checkboxes */
QCheckBox {
    color: #c9d1d9;
    spacing: 8px;
    font-size: 12px;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    background-color: #101214;
}

QCheckBox::indicator:checked {
    background-color: #ffffff;
    border-color: #ffffff;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: transparent;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #26292e;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3b3f46;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Progress bar */
QProgressBar {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    background-color: #0d0e11;
    text-align: center;
    color: #e6edf3;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #ffffff;
    border-radius: 3px;
}
"""

def get_severity_badge_style(severity: str) -> str:
    """Return inline badge style matching the modern dark aesthetic."""
    sev = severity.capitalize()
    if sev == "Critical":
        return "background-color: rgba(248, 81, 73, 0.2); color: #ff7b72; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; border: 1px solid rgba(248, 81, 73, 0.4);"
    elif sev == "High":
        return "background-color: rgba(210, 153, 34, 0.2); color: #d29922; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; border: 1px solid rgba(210, 153, 34, 0.4);"
    elif sev == "Medium":
        return "background-color: rgba(56, 139, 253, 0.2); color: #58a6ff; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; border: 1px solid rgba(56, 139, 253, 0.4);"
    else:
        return "background-color: rgba(46, 160, 67, 0.2); color: #3fb950; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; border: 1px solid rgba(46, 160, 67, 0.4);"
