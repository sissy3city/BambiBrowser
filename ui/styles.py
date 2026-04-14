"""QSS styles for BambiBrowser UI."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #0b0b12;
    color: #f5f5ff;
    font-family: 'Segoe UI', sans-serif;
}

QGroupBox {
    border: 2px solid #333;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: bold;
    color: #ff6bd6;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 10px;
    background-color: #0b0b12;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    width: 8px;
    background: #151521;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3a3a5a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QLineEdit {
    padding: 10px;
    border: 2px solid #444;
    border-radius: 8px;
    background: #151521;
    color: #f5f5ff;
    font-size: 14px;
}
QLineEdit:focus {
    border-color: #ff6bd6;
}

QMessageBox {
    background: #0b0b12;
}
QMessageBox QLabel {
    color: #f5f5ff;
}
"""