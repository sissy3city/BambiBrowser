"""Main application window - Clean minimal UI with OTP protection."""

import os
import sys
import logging
import hashlib
import secrets
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QGroupBox, QCheckBox, QSlider,
    QLineEdit, QScrollArea, QFrame, QMessageBox, QApplication,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QCloseEvent

from ui.styles import DARK_THEME

logger = logging.getLogger("BambiBrowser.UI")


class OTPDialog(QDialog):
    """OTP verification dialog."""
    
    def __init__(self, mode: str = "verify", otp_hash: str = None, parent=None):
        super().__init__(parent)
        self.mode = mode  # "verify", "set", or "display"
        self.otp_hash = otp_hash  # SHA256 hash for verification
        self.generated_otp = None  # Only used in "set" mode
        
        self.setWindowTitle("🔒 BambiLock")
        self.setFixedSize(400, 250)
        self.setModal(True)
        self.setStyleSheet(DARK_THEME)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title = QLabel("🔒 Enter BambiCode")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff6bd6;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Description
        if mode == "set":
            desc = QLabel("Your settings are locked! Save this code to unlock later:")
            desc.setStyleSheet("font-size: 12px; color: #ffcc9b;")
        elif mode == "verify":
            desc = QLabel("Enter your BambiCode to unlock settings:")
            desc.setStyleSheet("font-size: 12px; color: #888;")
        else:
            desc = QLabel("")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # OTP Display (only in set mode)
        if mode == "set":
            # Generate new OTP
            self.generated_otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            
            otp_display = QLabel(self.generated_otp)
            otp_display.setStyleSheet("""
                font-size: 28px; 
                font-weight: bold; 
                color: #ff6bd6; 
                background: #151521;
                padding: 10px;
                border-radius: 8px;
                font-family: monospace;
            """)
            otp_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(otp_display)
            
            warning = QLabel("⚠️ Write this down! No recovery possible!")
            warning.setStyleSheet("font-size: 11px; color: #ff6b6b;")
            warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(warning)
        
        # OTP Input
        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("Enter 6-digit code...")
        self.otp_input.setMaxLength(6)
        self.otp_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.otp_input.setStyleSheet("""
            font-size: 20px; 
            padding: 10px;
            font-family: monospace;
        """)
        layout.addWidget(self.otp_input)
        
        # Buttons
        buttons = QDialogButtonBox()
        if mode == "verify":
            verify_btn = QPushButton("Unlock")
            verify_btn.setStyleSheet("background: #ff6bd6; color: #1a0b1f; font-weight: bold;")
            verify_btn.clicked.connect(self._verify)
            buttons.addButton(verify_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        elif mode == "set":
            # In set mode, automatically verify as user types
            self.otp_input.textChanged.connect(self._on_set_input_change)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.clicked.connect(self.reject)
        buttons.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        
        layout.addWidget(buttons)
        self.setLayout(layout)
        
        # Focus on input
        self.otp_input.setFocus()
    
    def _on_set_input_change(self, text):
        """Auto-verify when 6 digits entered in set mode."""
        if len(text) == 6:
            if text == self.generated_otp:
                self.accept()
    
    def _verify(self):
        """Verify entered OTP against stored hash."""
        entered_otp = self.otp_input.text()
        
        if not entered_otp or len(entered_otp) != 6:
            QMessageBox.warning(self, "Invalid Code", "Please enter a 6-digit code.")
            return
        
        # Check against stored hash
        import hashlib
        entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
        
        if entered_hash == self.otp_hash:
            self.accept()
        else:
            QMessageBox.warning(self, "Wrong Code", "Invalid BambiCode! Try again...")
            self.otp_input.clear()
            self.otp_input.setFocus()
    
    def get_otp(self) -> str:
        """Return the entered OTP."""
        return self.otp_input.text()
    
    def get_generated_otp(self) -> str:
        """Return the generated OTP (only valid in set mode)."""
        return self.generated_otp


class SettingsPanel(QWidget):
    """Settings panel with checkboxes - requires save to apply."""
    
    settings_saved = pyqtSignal(dict)
    unlock_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("BambiBrowser", "Settings")
        self._locked = False
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Settings Group
        settings_group = QGroupBox("⚙️ Playback Settings")
        settings_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #ff6bd6;
                border: 2px solid #333;
                border-radius: 12px;
                margin-top: 14px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 10px;
                background: #0b0b12;
            }
        """)
        
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(12)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        
        # HardLock
        self.hardlock_cb = QCheckBox("🔒 HardLock - Block all keyboard & mouse input (NO ESCAPE)")
        self.hardlock_cb.setStyleSheet(self._checkbox_style())
        settings_layout.addWidget(self.hardlock_cb)
        
        # Warning label for HardLock
        hardlock_warning = QLabel("⚠️ Once HardLock activates, there is NO way to escape until playback ends")
        hardlock_warning.setStyleSheet("font-size: 11px; color: #ff6b6b; padding-left: 28px;")
        settings_layout.addWidget(hardlock_warning)
        
        # Click-Through
        self.clickthrough_cb = QCheckBox("👻 Click-Through Mode - Video transparent & click-through")
        self.clickthrough_cb.setStyleSheet(self._checkbox_style())
        self.clickthrough_cb.toggled.connect(self._on_clickthrough_toggled)
        settings_layout.addWidget(self.clickthrough_cb)
        
        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_layout.setContentsMargins(30, 0, 0, 0)
        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("font-size: 13px; color: #888;")
        opacity_layout.addWidget(opacity_label)
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setEnabled(False)
        self.opacity_slider.setStyleSheet(self._slider_style())
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_value = QLabel("100%")
        self.opacity_value.setStyleSheet("font-size: 12px; color: #888; min-width: 40px;")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_value.setText(f"{v}%"))
        opacity_layout.addWidget(self.opacity_value)
        
        settings_layout.addLayout(opacity_layout)
        
        # Multi-Monitor
        self.multimonitor_cb = QCheckBox("🖥️ Multi-Monitor - Play across all displays")
        self.multimonitor_cb.setStyleSheet(self._checkbox_style())
        settings_layout.addWidget(self.multimonitor_cb)
        
        # Volume
        volume_layout = QHBoxLayout()
        volume_label = QLabel("🔊 Volume:")
        volume_label.setStyleSheet("font-size: 14px; color: #f5f5ff; font-weight: bold;")
        volume_layout.addWidget(volume_label)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 256)
        self.volume_slider.setValue(256)
        self.volume_slider.setStyleSheet(self._slider_style())
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_value = QLabel("100%")
        self.volume_value.setStyleSheet("font-size: 12px; color: #888; min-width: 40px;")
        self.volume_slider.valueChanged.connect(lambda v: self.volume_value.setText(f"{int(v/256*100)}%"))
        volume_layout.addWidget(self.volume_value)
        
        settings_layout.addLayout(volume_layout)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # Lock Status
        self.lock_status = QLabel("🔓 Settings Unlocked")
        self.lock_status.setStyleSheet("""
            font-size: 12px; 
            color: #7dff9a; 
            padding: 8px; 
            background: #151521;
            border-radius: 8px;
        """)
        self.lock_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lock_status)
        
        # Save Button
        self.save_btn = QPushButton("💾 Save Settings & Lock")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #ff6bd6;
                color: #1a0b1f;
                font-size: 16px;
                font-weight: bold;
                padding: 14px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #ff8be0;
            }
            QPushButton:disabled {
                background: #3a3a4a;
                color: #888;
            }
        """)
        self.save_btn.clicked.connect(self._save_settings)
        main_layout.addWidget(self.save_btn)
        
        # Unlock Button (hidden when unlocked)
        self.unlock_btn = QPushButton("🔐 Enter BambiCode to Unlock")
        self.unlock_btn.setStyleSheet("""
            QPushButton {
                background: #26263a;
                color: #ff6bd6;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 8px;
                border: 1px solid #ff6bd6;
            }
            QPushButton:hover {
                background: #333350;
            }
        """)
        self.unlock_btn.clicked.connect(self._request_unlock)
        self.unlock_btn.hide()
        main_layout.addWidget(self.unlock_btn)
        
        self.setLayout(main_layout)
    
    def _checkbox_style(self):
        return """
            QCheckBox {
                color: #f5f5ff;
                font-size: 14px;
                spacing: 10px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 2px solid #555;
                background: #151521;
            }
            QCheckBox::indicator:checked {
                background: #ff6bd6;
                border-color: #ff6bd6;
            }
            QCheckBox:disabled {
                color: #666;
            }
        """
    
    def _slider_style(self):
        return """
            QSlider::groove:horizontal {
                height: 6px;
                background: #26263a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ff6bd6;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #ff6bd6;
                border-radius: 3px;
            }
            QSlider:disabled {
                opacity: 0.5;
            }
        """
    
    def _on_clickthrough_toggled(self, checked):
        self.opacity_slider.setEnabled(checked)
        if checked:
            # Click-through and HardLock are mutually exclusive
            self.hardlock_cb.setChecked(False)
            self.hardlock_cb.setEnabled(False)
        else:
            self.hardlock_cb.setEnabled(not self._locked)
    
    def _load_settings(self):
        """Load saved settings."""
        # Load values with defaults
        self.hardlock_cb.setChecked(self.settings.value("hardlock", True, type=bool))
        self.clickthrough_cb.setChecked(self.settings.value("click_through", False, type=bool))
        self.opacity_slider.setValue(self.settings.value("opacity", 100, type=int))
        self.multimonitor_cb.setChecked(self.settings.value("multi_monitor", False, type=bool))
        self.volume_slider.setValue(self.settings.value("volume", 256, type=int))
        
        # Check if locked (OTP hash exists and is not empty)
        saved_otp_hash = self.settings.value("otp_hash", "")
        self._locked = bool(saved_otp_hash and saved_otp_hash.strip() != "")
        
        # Update UI state
        self._update_lock_state()
        
        # Apply click-through state
        if self.clickthrough_cb.isChecked():
            self.hardlock_cb.setEnabled(False)
        self.opacity_slider.setEnabled(self.clickthrough_cb.isChecked())
    
    def _update_lock_state(self):
        """Update UI based on lock state."""
        enabled = not self._locked
        
        self.hardlock_cb.setEnabled(enabled and not self.clickthrough_cb.isChecked())
        self.clickthrough_cb.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled and self.clickthrough_cb.isChecked())
        self.multimonitor_cb.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)
        
        if self._locked:
            self.lock_status.setText("🔒 Settings Locked - Enter BambiCode to modify")
            self.lock_status.setStyleSheet("""
                font-size: 12px; 
                color: #ff6b6b; 
                padding: 8px; 
                background: #151521;
                border-radius: 8px;
            """)
            self.save_btn.hide()
            self.unlock_btn.show()
        else:
            self.lock_status.setText("🔓 Settings Unlocked - Save to lock")
            self.lock_status.setStyleSheet("""
                font-size: 12px; 
                color: #7dff9a; 
                padding: 8px; 
                background: #151521;
                border-radius: 8px;
            """)
            self.save_btn.show()
            self.unlock_btn.hide()
    
    def _save_settings(self):
        """Save settings and lock with OTP."""
        # Show OTP generation dialog
        dialog = OTPDialog(mode="set", parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get the generated OTP and hash it
            generated_otp = dialog.get_generated_otp()
            entered_otp = dialog.get_otp()
            
            # Verify they match
            if generated_otp != entered_otp:
                QMessageBox.warning(self, "Error", "Code mismatch! Settings not saved.")
                return
            
            # Hash the OTP for storage
            import hashlib
            otp_hash = hashlib.sha256(generated_otp.encode()).hexdigest()
            
            # Save settings
            self.settings.setValue("hardlock", self.hardlock_cb.isChecked())
            self.settings.setValue("click_through", self.clickthrough_cb.isChecked())
            self.settings.setValue("opacity", self.opacity_slider.value())
            self.settings.setValue("multi_monitor", self.multimonitor_cb.isChecked())
            self.settings.setValue("volume", self.volume_slider.value())
            self.settings.setValue("otp_hash", otp_hash)
            
            self._locked = True
            self._update_lock_state()
            
            # Emit settings
            self.settings_saved.emit(self.get_settings())
            
            QMessageBox.information(
                self, 
                "Settings Saved & Locked", 
                "Your settings are now locked!\n\n"
                "The application will continue running with these settings.\n"
                "You'll need your BambiCode to change them later.\n\n"
                "⚠️ WARNING: If HardLock is enabled, there will be NO ESCAPE once video starts!"
            )
    
    def _request_unlock(self):
        """Request OTP to unlock settings."""
        saved_otp_hash = self.settings.value("otp_hash", "")
        
        if not saved_otp_hash:
            self._locked = False
            self._update_lock_state()
            return
        
        # Create verification dialog with the stored hash
        dialog = OTPDialog(mode="verify", otp_hash=saved_otp_hash, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # OTP verified successfully
            self._locked = False
            self.settings.remove("otp_hash")
            self._update_lock_state()
            QMessageBox.information(self, "Unlocked", "Settings unlocked! You can now modify them.")
    
    def get_settings(self):
        """Return current settings as dict."""
        return {
            "input_lock": self.hardlock_cb.isChecked(),
            "click_through": self.clickthrough_cb.isChecked(),
            "opacity": self.opacity_slider.value() if self.clickthrough_cb.isChecked() else 100,
            "multi_monitor": self.multimonitor_cb.isChecked(),
            "volume": self.volume_slider.value(),
        }
    
    def is_locked(self):
        return self._locked


class MainWindow(QMainWindow):
    """Main application window - minimal UI."""
    
    def __init__(self, player, server, hard_lock):
        super().__init__()
        
        self.player = player
        self.server = server
        self.hard_lock = hard_lock
        
        self.setWindowTitle("BambiBrowser")
        self.setMinimumSize(550, 650)
        self.resize(600, 800)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setStyleSheet(DARK_THEME)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_saved_settings()
    
    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0b0b12; }")
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)
        container_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("🎀 BambiBrowser")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #ff6bd6;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(header)
        
        # Subtitle
        subtitle = QLabel("deep • mindless • bliss")
        subtitle.setStyleSheet("font-size: 12px; color: #888; font-style: italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(subtitle)
        
        # Settings Panel
        self.settings_panel = SettingsPanel()
        self.settings_panel.settings_saved.connect(self._on_settings_saved)
        container_layout.addWidget(self.settings_panel)
        
        # Status indicator
        self.status_label = QLabel("🟢 Ready")
        self.status_label.setStyleSheet("""
            font-size: 11px; 
            color: #7dff9a; 
            padding: 5px;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.status_label)
        
        container_layout.addStretch()
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)
    
    def _connect_signals(self):
        self.player.status_changed.connect(self._on_player_status)
        self.server.status_changed.connect(self._on_server_status)
    
    def _apply_saved_settings(self):
        settings = self.settings_panel.get_settings()
        self.player.update_settings(**settings)
    
    def _on_settings_saved(self, settings):
        self.player.update_settings(**settings)
        self.status_label.setText("🟢 Settings Applied & Locked")
        QTimer.singleShot(3000, lambda: self.status_label.setText("🟢 Ready"))
    
    def _on_player_status(self, is_playing):
        if is_playing:
            if self.settings_panel.get_settings().get("input_lock", True):
                self.status_label.setText("🔒 Playing - HARDLOCK ACTIVE - NO ESCAPE")
                self.status_label.setStyleSheet("""
                    font-size: 11px; 
                    color: #ff6b6b; 
                    padding: 5px;
                    font-weight: bold;
                """)
            else:
                self.status_label.setText("🎬 Playing...")
                self.status_label.setStyleSheet("""
                    font-size: 11px; 
                    color: #7dff9a; 
                    padding: 5px;
                """)
        else:
            self.status_label.setText("🟢 Ready")
            self.status_label.setStyleSheet("""
                font-size: 11px; 
                color: #7dff9a; 
                padding: 5px;
            """)
    
    def _on_server_status(self, is_running):
        pass  # Silent
    
    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()
    
    def update_player_status(self, is_playing: bool):
        self._on_player_status(is_playing)
    
    def update_server_status(self, is_running: bool):
        pass