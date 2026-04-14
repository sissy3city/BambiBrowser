"""Settings panel with iOS-style toggle switches."""

import logging
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QSlider, QPushButton,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush

logger = logging.getLogger("BambiBrowser.UI.Settings")


class IOSToggleSwitch(QWidget):
    """iOS-style toggle switch."""
    
    toggled = pyqtSignal(bool)
    
    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._checked = False
        self._label = label
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor("#34c759") if self._checked else QColor("#8e8e93")
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        
        knob_color = QColor("#ffffff")
        painter.setBrush(QBrush(knob_color))
        
        knob_x = self.width() - 23 if self._checked else 3
        painter.drawEllipse(knob_x, 3, 20, 20)
    
    def mousePressEvent(self, event):
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)
    
    def setChecked(self, checked: bool):
        self._checked = checked
        self.update()
    
    def isChecked(self) -> bool:
        return self._checked
    
    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        self.update()


class ToggleRow(QWidget):
    """Row with label and iOS toggle."""
    
    toggled = pyqtSignal(bool)
    
    def __init__(self, label: str, description: str = "", parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)
        
        row_layout = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 13px; font-weight: bold; color: #f5f5ff;")
        row_layout.addWidget(self.label)
        
        row_layout.addStretch()
        
        self.toggle = IOSToggleSwitch()
        self.toggle.toggled.connect(self.toggled.emit)
        row_layout.addWidget(self.toggle)
        
        layout.addLayout(row_layout)
        
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("font-size: 11px; color: #888; padding-left: 2px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        
        self.setLayout(layout)
    
    def setChecked(self, checked: bool):
        self.toggle.setChecked(checked)
    
    def isChecked(self) -> bool:
        return self.toggle.isChecked()
    
    def setEnabled(self, enabled: bool):
        self.toggle.setEnabled(enabled)
        self.label.setEnabled(enabled)


class MonitorSelector(QWidget):
    """Monitor selection widget."""
    
    selection_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(20, 0, 0, 0)
        
        self.refresh_btn = QPushButton("↻ Refresh Monitors")
        self.refresh_btn.setProperty("class", "secondary")
        self.refresh_btn.setMaximumWidth(140)
        layout.addWidget(self.refresh_btn)
        
        self.checkbox_container = QWidget()
        self.checkbox_layout = QVBoxLayout()
        self.checkbox_layout.setSpacing(2)
        self.checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.checkbox_container.setLayout(self.checkbox_layout)
        
        scroll = QScrollArea()
        scroll.setWidget(self.checkbox_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #333;
                border-radius: 6px;
                background-color: #0b0b12;
            }
        """)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        
        self._checkboxes = []
        self._available_monitors = []
    
    def set_available_monitors(self, monitors: list):
        self._available_monitors = monitors
        self._rebuild_checkboxes()
    
    def _rebuild_checkboxes(self):
        for cb in self._checkboxes:
            cb.deleteLater()
        self._checkboxes.clear()
        
        for idx in self._available_monitors:
            cb = QCheckBox(f"Monitor {idx + 1}")
            cb.setStyleSheet("""
                QCheckBox {
                    color: #f5f5ff;
                    spacing: 6px;
                    padding: 2px;
                    font-size: 12px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border-radius: 4px;
                    border: 2px solid #555;
                    background: #151521;
                }
                QCheckBox::indicator:checked {
                    background: #ff6bd6;
                    border-color: #ff6bd6;
                }
            """)
            cb.setProperty("monitor_index", idx)
            cb.toggled.connect(self._on_selection_changed)
            self.checkbox_layout.addWidget(cb)
            self._checkboxes.append(cb)
    
    def _on_selection_changed(self):
        selected = [cb.property("monitor_index") for cb in self._checkboxes if cb.isChecked()]
        self.selection_changed.emit(selected)
    
    def get_selected_monitors(self) -> list:
        return [cb.property("monitor_index") for cb in self._checkboxes if cb.isChecked()]
    
    def set_selected_monitors(self, monitors: list):
        for cb in self._checkboxes:
            cb.setChecked(cb.property("monitor_index") in monitors)


class SettingsPanel(QWidget):
    """Settings panel with iOS toggles."""
    
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, player, hard_lock, parent=None):
        super().__init__(parent)
        self.player = player
        self.hard_lock = hard_lock
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Settings group
        settings_group = QGroupBox("⚙️ Playback Settings")
        settings_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #ff6bd6;
                border: 1px solid #333;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #0b0b12;
            }
        """)
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        
        # HardLock toggle
        self.hardlock_row = ToggleRow(
            "🔒 HardLock - NO ESCAPE",
            "Blocks ALL keyboard and mouse input system-wide. No way out until playback ends."
        )
        self.hardlock_row.toggled.connect(self._on_settings_changed)
        settings_layout.addWidget(self.hardlock_row)
        
        # HardLock warning if no admin
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if not is_admin:
                warning = QLabel("⚠️ Admin rights required for full HardLock")
                warning.setStyleSheet("font-size: 11px; color: #ff6b6b; padding-left: 8px;")
                settings_layout.addWidget(warning)
        except:
            pass
        
        # Click-through mode
        self.transparent_row = ToggleRow(
            "👻 Click-Through Mode",
            "Video becomes transparent and click-through"
        )
        self.transparent_row.toggled.connect(self._on_transparency_toggled)
        settings_layout.addWidget(self.transparent_row)
        
        # Opacity slider (shown only when click-through is on)
        opacity_layout = QHBoxLayout()
        opacity_layout.setContentsMargins(20, 0, 0, 0)
        opacity_layout.addWidget(QLabel("Opacity:"))
        
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(10, 100)
        self.transparency_slider.setValue(100)
        self.transparency_slider.valueChanged.connect(self._on_settings_changed)
        self.transparency_slider.setEnabled(False)
        opacity_layout.addWidget(self.transparency_slider)
        
        self.transparency_label = QLabel("100%")
        self.transparency_label.setStyleSheet("font-size: 11px; color: #888; min-width: 35px;")
        self.transparency_slider.valueChanged.connect(
            lambda v: self.transparency_label.setText(f"{v}%")
        )
        opacity_layout.addWidget(self.transparency_label)
        opacity_layout.addStretch()
        
        self.opacity_widget = QWidget()
        self.opacity_widget.setLayout(opacity_layout)
        self.opacity_widget.setVisible(False)
        settings_layout.addWidget(self.opacity_widget)
        
        # Multi-monitor toggle
        self.multimonitor_row = ToggleRow(
            "🖥️ Multi-Monitor",
            "Play video across multiple displays"
        )
        self.multimonitor_row.toggled.connect(self._on_multimonitor_toggled)
        settings_layout.addWidget(self.multimonitor_row)
        
        # Monitor selector
        self.monitor_selector = MonitorSelector()
        self.monitor_selector.selection_changed.connect(self._on_settings_changed)
        self.monitor_selector.refresh_btn.clicked.connect(self._refresh_monitors)
        self.monitor_selector.setVisible(False)
        settings_layout.addWidget(self.monitor_selector)
        
        # Volume slider
        volume_layout = QHBoxLayout()
        volume_label = QLabel("🔊 Volume")
        volume_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #f5f5ff;")
        volume_layout.addWidget(volume_label)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 256)
        self.volume_slider.setValue(256)
        self.volume_slider.valueChanged.connect(self._on_settings_changed)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #26263a;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ff6bd6;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #ff6bd6;
                border-radius: 2px;
            }
        """)
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("100%")
        self.volume_label.setStyleSheet("font-size: 11px; color: #888; min-width: 35px;")
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_label.setText(f"{int(v / 256 * 100)}%")
        )
        volume_layout.addWidget(self.volume_label)
        
        settings_layout.addLayout(volume_layout)
        
        # System status (compact)
        status_layout = QHBoxLayout()
        status_layout.setSpacing(15)
        
        # VLC status
        self.vlc_label = QLabel()
        self.vlc_label.setStyleSheet("font-size: 11px;")
        status_layout.addWidget(self.vlc_label)
        
        # Admin status
        self.admin_label = QLabel()
        self.admin_label.setStyleSheet("font-size: 11px;")
        status_layout.addWidget(self.admin_label)
        
        status_layout.addStretch()
        settings_layout.addLayout(status_layout)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        self.setLayout(main_layout)
    
    def _on_transparency_toggled(self, checked: bool):
        self.opacity_widget.setVisible(checked)
        self.transparency_slider.setEnabled(checked)
        if checked:
            self.hardlock_row.setChecked(False)
            self.hardlock_row.setEnabled(False)
        else:
            self.hardlock_row.setEnabled(True)
        self._on_settings_changed()
    
    def _on_multimonitor_toggled(self, checked: bool):
        self.monitor_selector.setVisible(checked)
        if checked:
            self._refresh_monitors()
        self._on_settings_changed()
    
    def _refresh_monitors(self):
        monitors = self.player.get_available_monitors()
        self.monitor_selector.set_available_monitors(monitors)
    
    def _on_settings_changed(self):
        self.settings_changed.emit(self.get_settings())
    
    def _load_settings(self):
        settings = self.player.settings
        self.hardlock_row.setChecked(settings.get("input_lock", True))
        self.transparent_row.setChecked(settings.get("click_through", False))
        self.transparency_slider.setValue(settings.get("opacity", 100))
        self.multimonitor_row.setChecked(settings.get("multi_monitor", False))
        self.monitor_selector.set_selected_monitors(settings.get("selected_monitors", []))
        self.volume_slider.setValue(settings.get("volume", 256))
        
        # Update status
        if self.player.vlc_available:
            self.vlc_label.setText("✅ VLC Ready")
            self.vlc_label.setStyleSheet("font-size: 11px; color: #7dff9a;")
        else:
            self.vlc_label.setText("❌ VLC Missing")
            self.vlc_label.setStyleSheet("font-size: 11px; color: #ff6b6b;")
        
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                self.admin_label.setText("🔐 Admin")
                self.admin_label.setStyleSheet("font-size: 11px; color: #7dff9a;")
            else:
                self.admin_label.setText("⚠️ No Admin")
                self.admin_label.setStyleSheet("font-size: 11px; color: #ffcc9b;")
        except:
            self.admin_label.setText("")
    
    def get_settings(self) -> Dict[str, Any]:
        return {
            "input_lock": self.hardlock_row.isChecked(),
            "click_through": self.transparent_row.isChecked(),
            "opacity": self.transparency_slider.value() if self.transparent_row.isChecked() else 100,
            "multi_monitor": self.multimonitor_row.isChecked(),
            "selected_monitors": self.monitor_selector.get_selected_monitors() 
                if self.multimonitor_row.isChecked() else [],
            "volume": self.volume_slider.value(),
        }