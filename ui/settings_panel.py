"""Unified settings panel with OTP lock and Bambi Gag."""

import logging
import json
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QSlider, QPushButton,
    QScrollArea, QComboBox, QTabWidget, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QFileDialog, QTextEdit, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush

from core.settings_manager import SettingsManager, PlaybackSettings, SafetySettings, TextReplacerSettings
from ui.otp_dialog import OTPDialog

logger = logging.getLogger("BambiBrowser.UI.Settings")


class IOSToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_color = QColor("#34c759") if self._checked else QColor("#8e8e93")
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        painter.setBrush(QBrush(QColor("#ffffff")))
        knob_x = self.width() - 23 if self._checked else 3
        painter.drawEllipse(knob_x, 3, 20, 20)
    def mousePressEvent(self, event):
        if self.isEnabled():
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)
    def setChecked(self, checked: bool):
        self._checked = checked
        self.update()
    def isChecked(self) -> bool:
        return self._checked


class ToggleRow(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self, label: str, description: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)
        row = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 13px; font-weight: bold; color: #f5f5ff;")
        row.addWidget(self.label)
        row.addStretch()
        self.toggle = IOSToggleSwitch()
        self.toggle.toggled.connect(self.toggled)
        row.addWidget(self.toggle)
        layout.addLayout(row)
        if description:
            desc = QLabel(description)
            desc.setStyleSheet("font-size: 11px; color: #888; padding-left: 2px;")
            desc.setWordWrap(True)
            layout.addWidget(desc)
        self.setLayout(layout)
    def setChecked(self, checked: bool):
        self.toggle.setChecked(checked)
    def isChecked(self) -> bool:
        return self.toggle.isChecked()
    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.toggle.setEnabled(enabled)
        self.label.setEnabled(enabled)


class SliderWithAction(QWidget):
    value_changed = pyqtSignal(int)
    action_changed = pyqtSignal(str)
    def __init__(self, label: str, min_val: int, max_val: int, default: int,
                 actions: List[str], tolerance: int = 2, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.tolerance = tolerance
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)
        title = QLabel(label)
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #f5f5ff;")
        layout.addWidget(title)
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #26263a; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ff6bd6; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #ff6bd6; border-radius: 2px; }
        """)
        slider_layout.addWidget(self.slider, 1)
        self.value_label = QLabel(str(default))
        self.value_label.setStyleSheet("font-size: 12px; color: #7dff9a; min-width: 40px;")
        slider_layout.addWidget(self.value_label)
        layout.addLayout(slider_layout)
        self.range_label = QLabel()
        self.range_label.setStyleSheet("font-size: 11px; color: #888; padding-left: 4px;")
        layout.addWidget(self.range_label)
        self._update_range_display(default)
        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("Action:"))
        self.action_combo = QComboBox()
        self.action_combo.addItems(actions)
        self.action_combo.currentTextChanged.connect(self.action_changed)
        self.action_combo.setStyleSheet("QComboBox { background: #26263a; color: #f5f5ff; border: 1px solid #333; border-radius: 4px; padding: 4px; }")
        action_layout.addWidget(self.action_combo)
        action_layout.addStretch()
        layout.addLayout(action_layout)
        self.setLayout(layout)
    def _on_slider_changed(self, value):
        self.value_label.setText(str(value))
        self._update_range_display(value)
        self.value_changed.emit(value)
    def _update_range_display(self, value):
        min_range = max(self.min_val, value - self.tolerance)
        max_range = min(self.max_val, value + self.tolerance)
        self.range_label.setText(f"Acceptable range: {min_range} - {max_range} (±{self.tolerance})")
    def value(self) -> int:
        return self.slider.value()
    def setValue(self, value: int):
        self.slider.setValue(value)
    def action(self) -> str:
        return self.action_combo.currentText()
    def setAction(self, action: str):
        idx = self.action_combo.findText(action)
        if idx >= 0:
            self.action_combo.setCurrentIndex(idx)
    def setMinimum(self, min_val: int):
        current = self.slider.value()
        self.min_val = min_val
        self.slider.setMinimum(min_val)
        if current < min_val:
            self.slider.setValue(min_val)
        self._update_range_display(self.slider.value())
    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.action_combo.setEnabled(enabled)


class UnifiedSettingsPanel(QWidget):
    settings_changed = pyqtSignal()
    def __init__(self, settings_manager: SettingsManager, gag_manager=None, parent=None):
        super().__init__(parent)
        self._manager = settings_manager
        self.gag_manager = gag_manager
        self._user_editing = False
        self._setup_ui()
        self._load_from_manager()
        self._connect_signals()
        self._update_lock_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.lock_status = QLabel()
        self.lock_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lock_status.setStyleSheet("font-size: 13px; padding: 10px; background: #151521; border-radius: 8px; font-weight: bold;")
        main_layout.addWidget(self.lock_status)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; border-radius: 8px; background: #0b0b12; }
            QTabBar::tab { background: #151521; color: #888; padding: 10px 20px; margin-right: 2px; }
            QTabBar::tab:selected { background: #1a1a2a; color: #ff6bd6; font-weight: bold; }
        """)
        self.tabs.addTab(self._create_playback_tab(), "🎬 Bambi Player")
        self.tabs.addTab(self._create_text_replacer_tab(), "📖 Bambi Dictionary")
        self.tabs.addTab(self._create_gag_tab(), "🔇 Bambi Gag")
        main_layout.addWidget(self.tabs)

        self.lock_btn = QPushButton()
        self.lock_btn.setStyleSheet("QPushButton { font-size: 15px; font-weight: bold; padding: 14px; border-radius: 10px; }")
        self.lock_btn.clicked.connect(self._on_lock_btn_clicked)
        main_layout.addWidget(self.lock_btn)
        self.setLayout(main_layout)

    def _create_playback_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Playback settings ---
        self.hardlock_row = ToggleRow("🔒 HardLock - NO ESCAPE", "Blocks ALL keyboard and mouse input system-wide during playback")
        self.hardlock_row.toggled.connect(self._on_setting_changed)
        layout.addWidget(self.hardlock_row)

        self.clickthrough_row = ToggleRow("👻 Click-Through Mode", "Video becomes transparent and click-through")
        self.clickthrough_row.toggled.connect(self._on_clickthrough_toggled)
        layout.addWidget(self.clickthrough_row)

        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout()
        opacity_layout.setContentsMargins(20, 0, 0, 0)
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_setting_changed)
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_layout.addWidget(self.opacity_label)
        opacity_layout.addStretch()
        opacity_widget.setLayout(opacity_layout)
        self.opacity_widget = opacity_widget
        self.opacity_widget.setVisible(False)
        layout.addWidget(self.opacity_widget)

        self.multimonitor_row = ToggleRow("🖥️ Multi-Monitor", "Play across multiple displays")
        self.multimonitor_row.toggled.connect(self._on_setting_changed)
        layout.addWidget(self.multimonitor_row)

        self.mute_audio_row = ToggleRow(
            "🔇 Mute Other Audio",
            "Mutes all other applications (browser, games, etc.) during playback.")
        self.mute_audio_row.toggled.connect(self._on_setting_changed)
        layout.addWidget(self.mute_audio_row)

        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("🔊 Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 256)
        self.volume_slider.setValue(256)
        self.volume_slider.valueChanged.connect(self._on_setting_changed)
        volume_layout.addWidget(self.volume_slider)
        self.volume_label = QLabel("100%")
        self.volume_slider.valueChanged.connect(lambda v: self.volume_label.setText(f"{int(v/256*100)}%"))
        volume_layout.addWidget(self.volume_label)
        layout.addLayout(volume_layout)

        # --- Safety Limits ---
        safety_group = QGroupBox("⏱️ Safety Limits")
        safety_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #ff6bd6;
                border: 2px solid #333;
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
        safety_layout = QVBoxLayout()
        safety_layout.setSpacing(12)
        safety_layout.setContentsMargins(16, 16, 16, 16)

        # Max video length
        video_toggle_layout = QHBoxLayout()
        video_toggle_layout.addWidget(QLabel("📹 Max Single File Length"))
        video_toggle_layout.addStretch()
        self.video_limit_toggle = IOSToggleSwitch()
        self.video_limit_toggle.toggled.connect(self._on_video_limit_toggled)
        video_toggle_layout.addWidget(self.video_limit_toggle)
        safety_layout.addLayout(video_toggle_layout)

        self.video_slider = SliderWithAction("Max Single File Length (minutes)", 5, 120, 10, tolerance=2,
            actions=["Block & Show Warning", "Stop Playback", "Auto-Skip Video", "Warn & Allow"])
        self.video_slider.value_changed.connect(self._on_video_limit_value_changed)
        self.video_slider.action_changed.connect(self._on_setting_changed)
        self.video_slider.setVisible(False)
        safety_layout.addWidget(self.video_slider)

        # Max queue duration
        queue_toggle_layout = QHBoxLayout()
        queue_toggle_layout.addWidget(QLabel("📋 Max Queue Duration"))
        queue_toggle_layout.addStretch()
        self.queue_limit_toggle = IOSToggleSwitch()
        self.queue_limit_toggle.toggled.connect(self._on_queue_limit_toggled)
        queue_toggle_layout.addWidget(self.queue_limit_toggle)
        safety_layout.addLayout(queue_toggle_layout)

        self.queue_slider = SliderWithAction("Maximum queue duration (minutes)", 30, 600, 60, tolerance=10,
            actions=["Reject New Videos", "Stop Playback", "Clear Queue", "Warn Only"])
        self.queue_slider.value_changed.connect(self._on_setting_changed)
        self.queue_slider.action_changed.connect(self._on_setting_changed)
        self.queue_slider.setVisible(False)
        safety_layout.addWidget(self.queue_slider)

        note = QLabel("💡 Queue duration limit cannot be lower than max video length")
        note.setStyleSheet("font-size: 11px; color: #666; padding-left: 4px;")
        safety_layout.addWidget(note)

        scope_note = QLabel("These limits apply to Hypnotube videos and BambiCloud audio sessions.")
        scope_note.setStyleSheet("font-size: 11px; color: #888; padding-left: 4px;")
        scope_note.setWordWrap(True)
        safety_layout.addWidget(scope_note)

        safety_group.setLayout(safety_layout)
        layout.addWidget(safety_group)

        layout.addWidget(self._create_bambicloud_tab())
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_text_replacer_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        self.tr_enabled_row = ToggleRow("🔄 Enable Bambi Dictionary", "System-wide text replacement (requires AutoHotkey)")
        self.tr_enabled_row.toggled.connect(self._on_text_replacer_toggled)
        layout.addWidget(self.tr_enabled_row)

        self.ahk_status = QLabel()
        self.ahk_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ahk_status.setStyleSheet("font-size: 11px; padding: 4px;")
        layout.addWidget(self.ahk_status)

        table_label = QLabel("📝 Bambi Dictionary Rules")
        table_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff6bd6;")
        layout.addWidget(table_label)

        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(3)
        self.rules_table.setHorizontalHeaderLabels(["Trigger", "Replacement", ""])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rules_table.setColumnWidth(2, 50)
        self.rules_table.setMinimumHeight(200)
        self.rules_table.setStyleSheet("""
            QTableWidget { background: #151521; border: 1px solid #333; border-radius: 6px; }
            QTableWidget::item { padding: 6px; color: #f5f5ff; }
            QHeaderView::section { background: #1a1a2a; color: #ff6bd6; padding: 8px; }
        """)
        layout.addWidget(self.rules_table)

        add_layout = QHBoxLayout()
        self.trigger_input = QLineEdit()
        self.trigger_input.setPlaceholderText("Trigger (e.g., i)")
        add_layout.addWidget(self.trigger_input)
        add_layout.addWidget(QLabel("→"))
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Replacement (e.g., Bambi)")
        add_layout.addWidget(self.replacement_input)
        add_btn = QPushButton("➕ Add")
        add_btn.clicked.connect(self._add_rule)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        for name in ["Bambi Soft", "Bambi Immersion", "Bambi Overwrite", "Bambi Hardcore"]:
            btn = QPushButton(name)
            btn.setStyleSheet("padding: 5px 10px; font-size: 11px;")
            btn.clicked.connect(lambda _, n=name: self._load_preset(n))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        action_layout = QHBoxLayout()
        reset_btn = QPushButton("🔄 Reset Defaults")
        reset_btn.clicked.connect(self._reset_rules)
        action_layout.addWidget(reset_btn)
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.clicked.connect(self._clear_rules)
        action_layout.addWidget(clear_btn)
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self._export_rules)
        action_layout.addWidget(export_btn)
        import_btn = QPushButton("📥 Import")
        import_btn.clicked.connect(self._import_rules)
        action_layout.addWidget(import_btn)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        self.rule_count_label = QLabel("0 rules")
        self.rule_count_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self.rule_count_label)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_gag_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Master enable
        self.gag_enabled_row = ToggleRow("🔇 Enable Bambi Gag", "Gags typed text in Discord (and other apps) when active")
        self.gag_enabled_row.toggled.connect(self._on_gag_master_toggled)
        layout.addWidget(self.gag_enabled_row)

        # Remote URL
        remote_layout = QVBoxLayout()
        remote_label = QLabel("Remote Status URL (Notepad.cc direct raw link):")
        remote_label.setStyleSheet("font-size: 12px; color: #ccc;")
        remote_layout.addWidget(remote_label)
        self.gag_remote_input = QLineEdit()
        self.gag_remote_input.setPlaceholderText("https://notepad.cc/raw/...")
        self.gag_remote_input.textChanged.connect(self._on_gag_remote_changed)
        remote_layout.addWidget(self.gag_remote_input)
        hint = QLabel("Leave empty to use local toggle only. The file must contain 'ON' or 'OFF'.")
        hint.setStyleSheet("font-size: 10px; color: #888;")
        remote_layout.addWidget(hint)
        layout.addLayout(remote_layout)

        # Local toggle
        self.gag_local_row = ToggleRow("🔘 Force Gag ON (Local)", "Overrides remote when no remote URL is set")
        self.gag_local_row.toggled.connect(self._on_gag_local_toggled)
        layout.addWidget(self.gag_local_row)

        # Status indicator
        self.gag_status_label = QLabel("Gag is: OFF")
        self.gag_status_label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 8px; background: #151521; border-radius: 6px;")
        self.gag_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.gag_status_label)

        # Connect to gag_manager signals if available
        if self.gag_manager:
            self.gag_manager.status_changed.connect(self._on_gag_status_changed)
            self.gag_manager.error_occurred.connect(self._on_gag_error)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_bambicloud_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Master enable
        self.bambicloud_enabled_row = ToggleRow("☁️ Enable Bambicloud Support",
                                               "Special handling for bambicloud.com audio content")
        self.bambicloud_enabled_row.toggled.connect(self._on_bambicloud_toggled)
        layout.addWidget(self.bambicloud_enabled_row)

        # Countdown enable
        self.bambicloud_countdown_row = ToggleRow("⏱️ Enable Countdown Overlay",
                                                 "Show desktop countdown before each media session")
        self.bambicloud_countdown_row.toggled.connect(self._on_bambicloud_countdown_toggled)
        layout.addWidget(self.bambicloud_countdown_row)

        # Animation type
        animation_layout = QHBoxLayout()
        animation_layout.addWidget(QLabel("Animation Type:"))
        self.bambicloud_animation_combo = QComboBox()
        self.bambicloud_animation_combo.addItem("Spiral", "spiral")
        self.bambicloud_animation_combo.addItem("None", "none")
        self.bambicloud_animation_combo.addItem("Custom file", "custom")
        self.bambicloud_animation_combo.currentTextChanged.connect(self._on_bambicloud_setting_changed)
        animation_layout.addWidget(self.bambicloud_animation_combo)
        animation_layout.addStretch()
        self.bambicloud_animation_widget = QWidget()
        self.bambicloud_animation_widget.setLayout(animation_layout)
        layout.addWidget(self.bambicloud_animation_widget)

        self.bambicloud_custom_file_button = QPushButton("Select GIF or video file")
        self.bambicloud_custom_file_button.clicked.connect(self._select_bambicloud_animation)
        self.bambicloud_custom_file_label = QLabel("No custom animation selected")
        self.bambicloud_custom_file_label.setStyleSheet("font-size: 11px; color: #888;")
        custom_file_layout = QHBoxLayout()
        custom_file_layout.addWidget(self.bambicloud_custom_file_button)
        custom_file_layout.addWidget(self.bambicloud_custom_file_label, 1)
        self.bambicloud_custom_file_widget = QWidget()
        self.bambicloud_custom_file_widget.setLayout(custom_file_layout)
        layout.addWidget(self.bambicloud_custom_file_widget)

        # Color scheme
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color Scheme:"))
        self.bambicloud_color_combo = QComboBox()
        self.bambicloud_color_combo.addItem("Neon - bright green, magenta, cyan", "neon")
        self.bambicloud_color_combo.addItem("Pastel - soft pink, lavender, mint", "pastel")
        self.bambicloud_color_combo.addItem("Dark - deep blue, violet, red", "dark")
        self.bambicloud_color_combo.addItem("Custom - choose your own hex colors", "custom")
        self.bambicloud_color_combo.currentTextChanged.connect(self._on_bambicloud_setting_changed)
        color_layout.addWidget(self.bambicloud_color_combo)
        color_layout.addStretch()
        self.bambicloud_color_widget = QWidget()
        self.bambicloud_color_widget.setLayout(color_layout)
        layout.addWidget(self.bambicloud_color_widget)

        self.bambicloud_color_help = QLabel("Colors control the spiral bands and outline during BambiCloud playback.")
        self.bambicloud_color_help.setWordWrap(True)
        self.bambicloud_color_help.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.bambicloud_color_help)
        self.bambicloud_custom_color_buttons = []
        self.bambicloud_custom_color_widget = QWidget()
        custom_color_layout = QHBoxLayout(self.bambicloud_custom_color_widget)
        for index, label in enumerate(("Primary", "Outline", "Accent")):
            button = QPushButton(f"Choose {label} color")
            button.clicked.connect(lambda _, color_index=index: self._choose_bambicloud_color(color_index))
            self.bambicloud_custom_color_buttons.append(button)
            custom_color_layout.addWidget(button)
        layout.addWidget(self.bambicloud_custom_color_widget)

        # Countdown duration
        countdown_duration_layout = QHBoxLayout()
        countdown_duration_layout.addWidget(QLabel("Countdown Duration:"))
        self.bambicloud_countdown_duration_slider = QSlider(Qt.Orientation.Horizontal)
        self.bambicloud_countdown_duration_slider.setRange(5, 300)
        self.bambicloud_countdown_duration_slider.setValue(120)
        self.bambicloud_countdown_duration_slider.valueChanged.connect(self._on_bambicloud_countdown_duration_changed)
        countdown_duration_layout.addWidget(self.bambicloud_countdown_duration_slider)
        self.bambicloud_countdown_duration_label = QLabel("2 min")
        self.bambicloud_countdown_duration_slider.valueChanged.connect(
            lambda v: self.bambicloud_countdown_duration_label.setText(
                f"{v} sec" if v < 60 else f"{v // 60} min {v % 60} sec" if v % 60 else f"{v // 60} min"))
        countdown_duration_layout.addWidget(self.bambicloud_countdown_duration_label)
        self.bambicloud_countdown_duration_widget = QWidget()
        self.bambicloud_countdown_duration_widget.setLayout(countdown_duration_layout)
        layout.addWidget(self.bambicloud_countdown_duration_widget)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ---------- Bambicloud signal handlers ----------
    def _on_bambicloud_toggled(self, checked: bool):
        if self._manager.is_locked:
            return
        self._manager.update_bambicloud(enabled=checked)
        self._update_bambicloud_visibility()
        self.settings_changed.emit()

    def _on_bambicloud_countdown_toggled(self, checked: bool):
        if self._manager.is_locked:
            return
        self._manager.update_bambicloud(countdown_enabled=checked)
        self._update_bambicloud_visibility()
        self.settings_changed.emit()

    def _update_bambicloud_visibility(self):
        enabled = self.bambicloud_enabled_row.isChecked()
        countdown_enabled = self.bambicloud_countdown_row.isChecked()
        self.bambicloud_animation_widget.setVisible(enabled)
        self.bambicloud_custom_file_widget.setVisible(enabled and self.bambicloud_animation_combo.currentData() == "custom")
        self.bambicloud_color_widget.setVisible(enabled)
        self.bambicloud_color_help.setVisible(enabled)
        self.bambicloud_custom_color_widget.setVisible(enabled and self.bambicloud_color_combo.currentData() == "custom")
        self.bambicloud_countdown_duration_widget.setVisible(countdown_enabled)

    def _on_bambicloud_setting_changed(self):
        if self._manager.is_locked:
            return
        self._manager.update_bambicloud(
            animation_type=self.bambicloud_animation_combo.currentData(),
            color_scheme=self.bambicloud_color_combo.currentData()
        )
        self._update_bambicloud_visibility()
        self.settings_changed.emit()

    def _select_bambicloud_animation(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select BambiCloud animation", "",
            "Media files (*.gif *.mp4 *.webm *.avi *.mkv *.mov *.wmv *.m4v);;All files (*.*)"
        )
        if path:
            self._manager.update_bambicloud(custom_animation_path=path)
            self.bambicloud_custom_file_label.setText(path)
            self._update_bambicloud_visibility()
            self.settings_changed.emit()

    def _choose_bambicloud_color(self, color_index):
        color = QColorDialog.getColor(parent=self, title="Choose BambiCloud color")
        if color.isValid():
            current = self._manager.bambicloud.custom_colors.split(",")
            while len(current) < 3:
                current.append("#ff00ff")
            current[color_index] = color.name()
            self._manager.update_bambicloud(custom_colors=",".join(current))
            self.settings_changed.emit()

    def _on_bambicloud_countdown_duration_changed(self, value: int):
        if self._manager.is_locked:
            return
        self._manager.update_bambicloud(countdown_duration=value)
        self.settings_changed.emit()

    # ---------- Gag signal handlers ----------
    def _on_gag_master_toggled(self, checked: bool):
        if self._manager.is_locked:
            return
        self._manager.update_gag(enabled=checked)
        if self.gag_manager:
            if checked:
                self.gag_manager.start()
            else:
                self.gag_manager.stop()

    def _on_gag_remote_changed(self, text: str):
        if self._manager.is_locked:
            return
        self._manager.update_gag(remote_url=text)
        # Disable local toggle if remote URL is set
        self.gag_local_row.setEnabled(not bool(text.strip()))
        if self.gag_manager:
            self.gag_manager.reload()

    def _on_gag_local_toggled(self, checked: bool):
        if self._manager.is_locked:
            return
        self._manager.update_gag(local_toggle=checked)
        if self.gag_manager:
            self.gag_manager.reload()

    def _on_gag_status_changed(self, on: bool):
        self.gag_status_label.setText(f"Gag is: {'ON' if on else 'OFF'}")
        self.gag_status_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; padding: 8px; background: #151521; border-radius: 6px; "
            f"color: {'#7dff9a' if on else '#ff6b6b'};"
        )

    def _on_gag_error(self, msg: str):
        QMessageBox.warning(self, "Gag Error", msg)

    # ---------- Connections and loading ----------
    def _connect_signals(self):
        self._manager.lock_state_changed.connect(self._on_lock_state_changed)
        self._manager.playback_settings_changed.connect(self._on_playback_changed)
        self._manager.safety_settings_changed.connect(self._on_safety_changed)
        self._manager.text_replacer_settings_changed.connect(self._on_text_replacer_changed)
        self._manager.all_settings_changed.connect(self._on_all_settings_changed)

    def _load_from_manager(self):
        p = self._manager.playback
        self.hardlock_row.setChecked(p.input_lock)
        self.clickthrough_row.setChecked(p.click_through)
        self.opacity_slider.setValue(p.opacity)
        self.opacity_widget.setVisible(p.click_through)
        self.multimonitor_row.setChecked(p.multi_monitor)
        self.mute_audio_row.setChecked(p.mute_other_audio)
        self.volume_slider.setValue(p.volume)

        s = self._manager.safety
        self.video_limit_toggle.setChecked(s.max_video_length_enabled)
        self.video_slider.setValue(s.max_video_length_minutes)
        self.video_slider.setAction(s.max_video_length_action)
        self.video_slider.setVisible(s.max_video_length_enabled)

        self.queue_limit_toggle.setChecked(s.max_queue_duration_enabled)
        self.queue_slider.setValue(s.max_queue_duration_minutes)
        self.queue_slider.setAction(s.max_queue_duration_action)
        self.queue_slider.setVisible(s.max_queue_duration_enabled)

        if s.max_video_length_enabled:
            self.queue_slider.setMinimum(s.max_video_length_minutes)

        tr = self._manager.text_replacer
        self.tr_enabled_row.setChecked(tr.enabled)
        self._load_rules_table(tr.rules)
        self._update_ahk_status()

        # Gag settings
        g = self._manager.gag
        self.gag_enabled_row.setChecked(g.enabled)
        self.gag_remote_input.setText(g.remote_url)
        self.gag_local_row.setChecked(g.local_toggle)
        self.gag_local_row.setEnabled(not bool(g.remote_url.strip()))
        # Update status label if gag_manager is running
        if self.gag_manager and self.gag_manager.is_running:
            self._on_gag_status_changed(self.gag_manager.current_state)

        # Bambicloud settings
        bc = self._manager.bambicloud
        self.bambicloud_enabled_row.setChecked(bc.enabled)
        self.bambicloud_countdown_row.setChecked(bc.countdown_enabled)
        self.bambicloud_animation_combo.setCurrentText("Custom file" if bc.animation_type == "custom" else bc.animation_type.title())
        color_index = self.bambicloud_color_combo.findData(bc.color_scheme)
        if color_index >= 0:
            self.bambicloud_color_combo.setCurrentIndex(color_index)
        self.bambicloud_custom_file_label.setText(bc.custom_animation_path or "No custom animation selected")
        self.bambicloud_countdown_duration_slider.setValue(bc.countdown_duration)
        self._update_bambicloud_visibility()

        # Apply lock state immediately after loading
        self._on_lock_state_changed(self._manager.is_locked)

    # ---------- Rule table methods ----------
    def _load_rules_table(self, rules: dict):
        self.rules_table.setRowCount(0)
        for trigger, replacement in rules.items():
            self._add_rule_to_table(trigger, replacement)
        self._update_rule_count()

    def _add_rule_to_table(self, trigger: str, replacement: str):
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)
        self.rules_table.setItem(row, 0, QTableWidgetItem(trigger))
        self.rules_table.setItem(row, 1, QTableWidgetItem(replacement))
        del_btn = QPushButton("❌")
        del_btn.setStyleSheet("background: transparent; border: none;")
        del_btn.clicked.connect(lambda: self._delete_rule(row))
        self.rules_table.setCellWidget(row, 2, del_btn)

    def _delete_rule(self, row: int):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to modify rules.")
            return
        self.rules_table.removeRow(row)
        self._save_rules_from_table()
        self._update_rule_count()

    def _add_rule(self):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to add rules.")
            return
        trigger = self.trigger_input.text().strip()
        replacement = self.replacement_input.text().strip()
        if not trigger or not replacement:
            return
        self._add_rule_to_table(trigger, replacement)
        self.trigger_input.clear()
        self.replacement_input.clear()
        self._save_rules_from_table()
        self._update_rule_count()

    def _save_rules_from_table(self):
        rules = {}
        for row in range(self.rules_table.rowCount()):
            trigger = self.rules_table.item(row, 0)
            replacement = self.rules_table.item(row, 1)
            if trigger and replacement:
                rules[trigger.text()] = replacement.text()
        if rules != self._manager.text_replacer.rules:
            self._manager.set_text_replacer_rules(rules)

    def _load_preset(self, preset_name: str):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to load presets.")
            return
        presets = {
            "Bambi Soft": {
                "i": "Bambi", "me": "Bambi", "my": "Bambi’s", "mine": "Bambi’s", "myself": "Bambi",
                "brain": "soft fluffy brain", "thoughts": "sparkly pink thoughts",
                "smart": "bright and cheerful", "understand": "try to understand",
                "serious": "grown‑up serious stuff", "complicated": "a bit tricky"
            },

            "Bambi Immersion": {
                "i": "Bambi", "me": "Bambi", "my": "Bambi’s", "mine": "Bambi’s", "myself": "Bambi",
                "im": "Bambi is", "i’m": "Bambi is", "ive": "Bambi has", "id": "Bambi would", "ill": "Bambi will",
                "we": "Bambi and her friends", "our": "Bambi’s",
                "want": "crave", "need": "really need", "choose": "let someone choose", "decide": "let someone decide",
                "think": "drift a little", "remember": "try to remember", "focus": "try to focus gently",
                "smart": "sweet and simple", "understand": "try to understand with Bambi’s soft brain",
                "serious": "grown‑up serious things", "complicated": "too tricky for Bambi"
            },

            "Bambi Overwrite": {
                "i": "your gentle bimbo‑minded Bambi", "me": "gentle bimbo‑minded Bambi",
                "my": "Bambi’s soft little mind", "mine": "Bambi’s soft little mind",
                "myself": "gentle bimbo‑minded Bambi",
                "think": "drift deeper", "remember": "struggle to recall softly",
                "focus": "try really hard to focus with Bambi’s empty head",
                "brain": "empty soft bimbo brain",
                "want": "crave deeply", "need": "desperately need",
                "choose": "obey softly", "decide": "let someone decide for Bambi",
                "smart": "cute but clueless",
                "understand": "try to understand with Bambi’s tiny brain",
                "serious": "grown‑up serious stuff", "complicated": "way too hard for Bambi",
                "stop": "sink further", "resist": "melt gently", "control": "give in completely"
            },

            "Bambi Hardcore": {
                "i": "your soft empty‑headed Bambi", "me": "your soft empty‑headed Bambi",
                "my": "your soft Bambi’s tiny drifting mind", "mine": "your soft Bambi’s tiny drifting mind",
                "myself": "your soft empty‑headed Bambi",

                "im": "your soft empty‑headed Bambi is",
                "i’m": "your soft empty‑headed Bambi is",
                "ive": "your soft empty‑headed Bambi has",
                "id": "your soft empty‑headed Bambi would",
                "ill": "your soft empty‑headed Bambi will",

                "think": "drift deeper without thoughts",
                "thoughts": "soft floaty pink thoughts",
                "brain": "empty soft bimbo brain",
                "remember": "try to recall through the soft haze",
                "focus": "struggle to focus with Bambi’s empty head",
                "understand": "try to understand with Bambi’s tiny brain",
                "idea": "soft little sparkly idea",

                "want": "crave helplessly",
                "need": "desperately need in a soft way",
                "choose": "let someone choose for Bambi",
                "decide": "let someone decide for Bambi",
                "try": "try softly with Bambi’s empty head",

                "smart": "cute but clueless",
                "serious": "grown‑up serious stuff",
                "complicated": "way too hard for Bambi",

                "stop": "sink further",
                "resist": "melt softly",
                "control": "give in completely"
            }
        }
        if preset_name in presets:
            for trigger, replacement in presets[preset_name].items():
                exists = False
                for row in range(self.rules_table.rowCount()):
                    if self.rules_table.item(row, 0).text().lower() == trigger.lower():
                        exists = True
                        break
                if not exists:
                    self._add_rule_to_table(trigger, replacement)
            self._save_rules_from_table()
            self._update_rule_count()

    def _reset_rules(self):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to reset rules.")
            return
        reply = QMessageBox.question(self, "Reset Rules", "Reset to default Bambi rules?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.reset_text_replacer_to_default()
            self._load_rules_table(self._manager.text_replacer.rules)

    def _clear_rules(self):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to clear rules.")
            return
        reply = QMessageBox.question(self, "Clear Rules", "Remove ALL replacement rules?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.set_text_replacer_rules({})
            self.rules_table.setRowCount(0)
            self._update_rule_count()

    def _export_rules(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Rules", "", "JSON (*.json)")
        if file_path:
            rules = {}
            for row in range(self.rules_table.rowCount()):
                trigger = self.rules_table.item(row, 0)
                replacement = self.rules_table.item(row, 1)
                if trigger and replacement:
                    rules[trigger.text()] = replacement.text()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(rules, f, indent=2)
            QMessageBox.information(self, "Export", f"Exported {len(rules)} rules.")

    def _import_rules(self):
        if self._manager.is_locked:
            QMessageBox.warning(self, "Settings Locked", "Unlock settings to import rules.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Rules", "", "JSON (*.json)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                reply = QMessageBox.question(self, "Import", f"Found {len(rules)} rules. Replace existing?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    self.rules_table.setRowCount(0)
                for trigger, replacement in rules.items():
                    exists = False
                    for row in range(self.rules_table.rowCount()):
                        if self.rules_table.item(row, 0).text() == trigger:
                            exists = True
                            break
                    if not exists:
                        self._add_rule_to_table(trigger, replacement)
                self._save_rules_from_table()
                self._update_rule_count()
                QMessageBox.information(self, "Import", f"Imported {len(rules)} rules.")
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", str(e))

    def _update_rule_count(self):
        count = self.rules_table.rowCount()
        self.rule_count_label.setText(f"{count} rule{'s' if count != 1 else ''}")

    def _update_ahk_status(self):
        from pathlib import Path
        ahk_paths = [Path(__file__).parent.parent / "ahk" / "AutoHotkeyU64.exe",
                     Path("C:/Program Files/AutoHotkey/AutoHotkey.exe")]
        available = any(p.exists() for p in ahk_paths)
        if available:
            self.ahk_status.setText("✅ AutoHotkey Ready")
            self.ahk_status.setStyleSheet("color: #7dff9a;")
        else:
            self.ahk_status.setText("⚠️ AutoHotkey Not Found")
            self.ahk_status.setStyleSheet("color: #ffcc9b;")

    # ---------- Setting change handlers ----------
    def _on_setting_changed(self, *args):
        """Handle changes to playback and safety settings (not text replacer)."""
        if self._manager.is_locked:
            return
        if self.queue_limit_toggle.isChecked() and self.video_limit_toggle.isChecked():
            video_limit = self.video_slider.value()
            queue_limit = self.queue_slider.value()
            if queue_limit < video_limit:
                self.queue_slider.setValue(video_limit)
        self._user_editing = True
        try:
            self._manager.update_safety(
                max_video_length_enabled=self.video_limit_toggle.isChecked(),
                max_video_length_minutes=self.video_slider.value(),
                max_video_length_action=self.video_slider.action(),
                max_queue_duration_enabled=self.queue_limit_toggle.isChecked(),
                max_queue_duration_minutes=self.queue_slider.value(),
                max_queue_duration_action=self.queue_slider.action()
            )
            self._manager.update_playback(
                input_lock=self.hardlock_row.isChecked(),
                click_through=self.clickthrough_row.isChecked(),
                opacity=self.opacity_slider.value(),
                multi_monitor=self.multimonitor_row.isChecked(),
                volume=self.volume_slider.value(),
                mute_other_audio=self.mute_audio_row.isChecked()
            )
        finally:
            self._user_editing = False
        self.settings_changed.emit()

    def _on_text_replacer_toggled(self, checked: bool):
        """Handle text replacer enable/disable independently."""
        if self._manager.is_locked:
            return
        self._manager.update_text_replacer(enabled=checked)
        self.settings_changed.emit()

    def _on_clickthrough_toggled(self, checked: bool):
        self.opacity_widget.setVisible(checked)
        if checked:
            self.hardlock_row.setChecked(False)
        if not self._manager.is_locked:
            self.opacity_slider.setEnabled(checked)
        self._on_setting_changed()

    def _on_video_limit_toggled(self, checked: bool):
        self.video_slider.setVisible(checked)
        if checked:
            self.queue_slider.setMinimum(self.video_slider.value())
        self._on_setting_changed()

    def _on_video_limit_value_changed(self, value: int):
        if self.queue_limit_toggle.isChecked():
            current_queue = self.queue_slider.value()
            if current_queue < value:
                self.queue_slider.setValue(value)
        self.queue_slider.setMinimum(value)
        self._on_setting_changed()

    def _on_queue_limit_toggled(self, checked: bool):
        self.queue_slider.setVisible(checked)
        if checked and self.video_limit_toggle.isChecked():
            video_limit = self.video_slider.value()
            queue_limit = self.queue_slider.value()
            if queue_limit < video_limit:
                self.queue_slider.setValue(video_limit)
            self.queue_slider.setMinimum(video_limit)
        self._on_setting_changed()

    def _on_lock_btn_clicked(self):
        if self._manager.is_locked:
            self._unlock_settings()
        else:
            self._lock_settings()

    def _lock_settings(self):
        dialog = OTPDialog(mode="set", parent=self)
        if dialog.exec() == OTPDialog.DialogCode.Accepted:
            otp = dialog.get_otp()
            self._manager.lock_with_otp(otp)
            QMessageBox.information(self, "Settings Locked",
                "All settings are now locked!\n\nThe application will use these settings.\nYou'll need your BambiCode to change anything.")

    def _unlock_settings(self):
        stored_hash = self._manager.get_stored_otp_hash()
        dialog = OTPDialog(mode="verify", stored_hash=stored_hash, parent=self)
        if dialog.exec() == OTPDialog.DialogCode.Accepted:
            otp = dialog.get_otp()
            if self._manager.unlock_with_otp(otp):
                QMessageBox.information(self, "Settings Unlocked", "You can now modify settings.")
            else:
                QMessageBox.warning(self, "Error", "Failed to unlock settings.")

    def _on_lock_state_changed(self, locked: bool):
        self._update_lock_ui()
        enabled = not locked
        self.hardlock_row.setEnabled(enabled)
        self.clickthrough_row.setEnabled(enabled)
        self.multimonitor_row.setEnabled(enabled)
        self.mute_audio_row.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled and self.clickthrough_row.isChecked())
        self.video_limit_toggle.setEnabled(enabled)
        self.video_slider.setEnabled(enabled)
        self.queue_limit_toggle.setEnabled(enabled)
        self.queue_slider.setEnabled(enabled)
        self.bambicloud_enabled_row.setEnabled(enabled)
        self.bambicloud_countdown_row.setEnabled(enabled)
        self.bambicloud_animation_combo.setEnabled(enabled)
        self.bambicloud_custom_file_button.setEnabled(enabled)
        self.bambicloud_color_combo.setEnabled(enabled)
        for button in self.bambicloud_custom_color_buttons:
            button.setEnabled(enabled)
        self.bambicloud_countdown_duration_slider.setEnabled(enabled)
        self.tr_enabled_row.setEnabled(enabled)
        self.rules_table.setEnabled(enabled)
        self.trigger_input.setEnabled(enabled)
        self.replacement_input.setEnabled(enabled)
        # Gag controls
        self.gag_enabled_row.setEnabled(enabled)
        self.gag_remote_input.setEnabled(enabled)
        self.gag_local_row.setEnabled(enabled and not bool(self.gag_remote_input.text().strip()))
        self.bambicloud_enabled_row.setEnabled(enabled)
        self.bambicloud_countdown_row.setEnabled(enabled)
        self.bambicloud_animation_combo.setEnabled(enabled)
        self.bambicloud_color_combo.setEnabled(enabled)
        self.bambicloud_countdown_duration_slider.setEnabled(enabled)

    def _update_lock_ui(self):
        if self._manager.is_locked:
            self.lock_status.setText("🔒 SETTINGS LOCKED - Enter BambiCode to modify")
            self.lock_status.setStyleSheet("font-size: 13px; padding: 10px; background: #2a1a1a; border-radius: 8px; color: #ff6b6b; font-weight: bold;")
            self.lock_btn.setText("🔐 Enter BambiCode to Unlock")
            self.lock_btn.setStyleSheet("QPushButton { background: #26263a; color: #ff6bd6; font-size: 15px; font-weight: bold; padding: 14px; border-radius: 10px; border: 1px solid #ff6bd6; }")
        else:
            self.lock_status.setText("🔓 Settings Unlocked - Click below to lock")
            self.lock_status.setStyleSheet("font-size: 13px; padding: 10px; background: #1a2a1a; border-radius: 8px; color: #7dff9a; font-weight: bold;")
            self.lock_btn.setText("💾 Save & Lock Settings")
            self.lock_btn.setStyleSheet("QPushButton { background: #ff6bd6; color: #0b0b12; font-size: 15px; font-weight: bold; padding: 14px; border-radius: 10px; }")

    def _on_playback_changed(self, settings): pass
    def _on_safety_changed(self, settings): pass
    def _on_text_replacer_changed(self, settings): pass
    def _on_all_settings_changed(self):
        """Refresh UI when settings are changed from external source"""
        if not self._user_editing:
            self._load_from_manager()

    def get_player_settings(self) -> dict:
        return self._manager.get_player_settings_dict()

    def is_locked(self) -> bool:
        return self._manager.is_locked