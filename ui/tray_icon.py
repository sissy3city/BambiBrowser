"""System tray icon functionality."""

import os
import sys
import threading
import logging
from typing import Optional, Callable

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("BambiBrowser.Tray")


class TrayIconManager(QObject):
    """Manages system tray icon."""

    def __init__(self, main_window, app: QApplication, shutdown_callback: Callable[[], None]):
        super().__init__()

        self.main_window = main_window
        self.app = app
        self.shutdown_callback = shutdown_callback
        self.tray_icon: Optional[QSystemTrayIcon] = None

        # Check if tray should be disabled
        self._enabled = os.environ.get("BAMBI_NO_TRAY") != "1"

        if self._enabled:
            self._setup_tray()

    def _setup_tray(self):
        """Setup system tray icon."""
        # Create icon
        icon_path = self._find_icon()
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            # Create fallback icon
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#ff6bd6"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(pixmap.rect(), 1, "B")
            painter.end()
            icon = QIcon(pixmap)

        self.tray_icon = QSystemTrayIcon(icon, self.app)
        self.tray_icon.setToolTip("BambiBrowser")

        # Create menu
        menu = QMenu()

        show_action = QAction("Show Window", self.app)
        show_action.triggered.connect(self.main_window.show)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

        # Show notification on start
        self.tray_icon.showMessage(
            "BambiBrowser",
            "Running in system tray",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

        # Connect signals
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _find_icon(self) -> Optional[str]:
        """Find icon file."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        candidates = [
            os.path.join(base_dir, "resources", "icon.png"),
            os.path.join(base_dir, "icon.png"),
            os.path.join(os.path.dirname(sys.executable), "icon.png") if getattr(sys, "frozen", False) else None,
        ]

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        return None

    def _on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.main_window.show()
            self.main_window.activateWindow()

    def _quit_app(self):
        """Quit the application."""
        logger.info("Quitting from tray...")
        if self.shutdown_callback:
            self.shutdown_callback()
        else:
            # Fallback: stop only player and server (legacy)
            self.main_window.player.cleanup()
            self.main_window.server.stop()
            self.app.quit()

    def start(self):
        """Show tray icon."""
        if self.tray_icon and self._enabled:
            self.tray_icon.show()
            logger.info("Tray icon shown")

    def stop(self):
        """Hide tray icon."""
        if self.tray_icon:
            self.tray_icon.hide()

    def show_message(self, title: str, message: str):
        """Show tray notification."""
        if self.tray_icon and self._enabled:
            self.tray_icon.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )