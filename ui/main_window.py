# ui/main_window.py
"""Main application window - simplified with unified settings."""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent

from core.settings_manager import SettingsManager
from ui.settings_panel import UnifiedSettingsPanel
from ui.styles import DARK_THEME

logger = logging.getLogger("BambiBrowser.UI")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, player, server, hard_lock, text_replacer, settings_manager: SettingsManager):
        super().__init__()
        
        self.player = player
        self.server = server
        self.hard_lock = hard_lock
        self.text_replacer = text_replacer
        self.settings_manager = settings_manager
        
        self.setWindowTitle("BambiBrowser")
        self.setMinimumSize(550, 650)
        self.resize(600, 800)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setStyleSheet(DARK_THEME)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_settings_to_player()
    
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
        
        subtitle = QLabel("deep • mindless • bliss")
        subtitle.setStyleSheet("font-size: 12px; color: #888; font-style: italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(subtitle)
        
        # Unified Settings Panel
        self.settings_panel = UnifiedSettingsPanel(self.settings_manager)
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
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
        """Connect signals."""
        self.player.status_changed.connect(self._on_player_status)
        self.server.status_changed.connect(self._on_server_status)
        self.settings_manager.lock_state_changed.connect(self._on_lock_state_changed)
        
        # Connect text replacer if available
        if self.text_replacer:
            self.settings_manager.text_replacer_settings_changed.connect(
                self._apply_text_replacer_settings
            )
    
    def _apply_settings_to_player(self):
        """Apply current settings to player."""
        settings = self.settings_manager.get_player_settings_dict()
        self.player.update_settings(**settings)
    
    def _apply_text_replacer_settings(self, settings):
        """Apply text replacer settings."""
        if not self.text_replacer:
            return
        
        # Update rules
        self.text_replacer.set_rules(settings.rules)
        
        # Update enabled state
        if settings.enabled and not self.text_replacer.is_enabled:
            self.text_replacer.start()
        elif not settings.enabled and self.text_replacer.is_enabled:
            self.text_replacer.stop()
    
    def _on_settings_changed(self):
        """Settings changed in UI."""
        self._apply_settings_to_player()
    
    def _on_lock_state_changed(self, locked: bool):
        """Lock state changed."""
        if locked:
            # Also lock the text replacer
            if self.text_replacer:
                self.text_replacer.lock_settings()
    
    def _on_player_status(self, is_playing: bool):
        if is_playing:
            if self.settings_manager.playback.input_lock:
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
    
    def _on_server_status(self, is_running: bool):
        pass  # Silent
    
    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()
    
    def update_player_status(self, is_playing: bool):
        self._on_player_status(is_playing)
    
    def update_server_status(self, is_running: bool):
        pass