#!/usr/bin/env python3
"""
BambiBrowser - Desktop Application
Fullscreen video player with HardLock capabilities.
"""

import ctypes
import sys
import os
import signal
import logging
import threading
import traceback
import atexit
import time
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QTimer

from core.utils import get_base_dir, setup_logging


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions."""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger = logging.getLogger("BambiBrowser")
    logger.critical(f"Unhandled exception:\n{error_msg}")
   
    try:
        app = QApplication.instance()
        if app:
            QMessageBox.critical(
                None,
                "BambiBrowser - Critical Error",
                f"An unexpected error occurred:\n\n{exc_value}\n\nCheck bambi_browser.log for details."
            )
    except:
        pass
   
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = global_exception_handler


def is_admin():
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


class BambiBrowserApp:
    """Main application controller."""
   
    def __init__(self):
        self.base_dir = get_base_dir()
        self.logger = setup_logging(self.base_dir)
       
        # Check admin rights
        self.has_admin = is_admin()
        if sys.platform == "win32" and not self.has_admin:
            self.logger.warning("Running without administrator privileges - HardLock fallback will be used")
       
        # Enable high DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
       
        # Create Qt Application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("BambiBrowser")
        self.app.setApplicationVersion("5.0")
        self.app.setQuitOnLastWindowClosed(False)
       
        # Import Qt-dependent modules
        try:
            from core.hard_lock import HardLock
            from core.player import VideoPlayer
            from core.server import BambiServer
            from ui.main_window import MainWindow
            from ui.tray_icon import TrayIconManager
            from PyQt6.QtGui import QIcon
        except Exception as e:
            self.logger.critical(f"Failed to import modules: {e}")
            raise
       
        # Set application icon
        icon_path = os.path.join(self.base_dir, "resources", "icon.png")
        if os.path.exists(icon_path):
            self.app.setWindowIcon(QIcon(icon_path))
       
        # Core components
        self.logger.info("Initializing HardLock...")
        try:
            self.hard_lock = HardLock()
        except Exception as e:
            self.logger.error(f"Failed to initialize HardLock: {e}")
            self.hard_lock = None
       
        self.logger.info("Initializing VideoPlayer...")
        try:
            self.player = VideoPlayer(self.hard_lock) if self.hard_lock else None
        except Exception as e:
            self.logger.error(f"Failed to initialize VideoPlayer: {e}")
            self.player = None
       
        self.logger.info("Initializing HTTP Server...")
        try:
            self.server = BambiServer(self.player, port=5655) if self.player else None
        except Exception as e:
            self.logger.error(f"Failed to initialize HTTP Server: {e}")
            self.server = None
       
        # UI components
        self.logger.info("Creating main window...")
        try:
            self.main_window = MainWindow(self.player, self.server, self.hard_lock)
        except Exception as e:
            self.logger.error(f"Failed to create main window: {e}")
            self.main_window = None
       
        # Tray icon
        self.logger.info("Setting up system tray...")
        try:
            self.tray = TrayIconManager(self.main_window, self.app)
        except Exception as e:
            self.logger.error(f"Failed to setup tray icon: {e}")
            self.tray = None
       
        # Connect signals
        if self.player and self.server:
            self.player.status_changed.connect(self._on_player_status_changed)
            self.server.status_changed.connect(self._on_server_status_changed)
       
        self.logger.info(f"BambiBrowser initialized successfully (Admin: {self.has_admin})")
   
    def _on_player_status_changed(self, is_playing: bool):
        """Handle player status changes."""
        if self.main_window:
            self.main_window.update_player_status(is_playing)
   
    def _on_server_status_changed(self, is_running: bool):
        """Handle server status changes."""
        if self.main_window:
            self.main_window.update_server_status(is_running)
   
    def start(self):
        """Start the application."""
        # Start HTTP server
        if self.server:
            self.logger.info("Starting HTTP server...")
            server_thread = threading.Thread(target=self._start_server, daemon=True)
            server_thread.start()
       
        # Show main window
        if self.main_window:
            self.logger.info("Showing main window...")
            self.main_window.show()
           
            # Show admin warning in status if needed
            if not self.has_admin:
                self.main_window.status_label.setText("⚠️ No Admin - Limited HardLock")
                self.main_window.status_label.setStyleSheet("""
                    font-size: 11px;
                    color: #ffcc9b;
                    padding: 5px;
                """)
       
        # Start tray icon
        if self.tray:
            self.tray.start()
       
        # Enable Ctrl+C handling
        signal.signal(signal.SIGINT, lambda *args: self.shutdown())
       
        # Run application
        self.logger.info("Application started - entering event loop")
        try:
            return self.app.exec()
        except Exception as e:
            self.logger.critical(f"Application crashed: {e}")
            return 1
   
    def _start_server(self):
        """Start HTTP server in background thread."""
        if self.server:
            try:
                if not self.server.start():
                    self.logger.error("Failed to start HTTP server")
            except Exception as e:
                self.logger.error(f"HTTP server error: {e}")
   
    def shutdown(self):
        """Clean shutdown."""
        self.logger.info("Shutting down...")
       
        if self.server:
            try:
                self.server.stop()
            except Exception as e:
                self.logger.error(f"Error stopping server: {e}")
       
        if self.hard_lock:
            try:
                self.hard_lock.unlock()
            except Exception as e:
                self.logger.error(f"Error unlocking HardLock: {e}")
       
        if self.player:
            try:
                self.player.cleanup()
            except Exception as e:
                self.logger.error(f"Error cleaning up player: {e}")
       
        if self.tray:
            try:
                self.tray.stop()
            except Exception as e:
                self.logger.error(f"Error stopping tray: {e}")
       
        try:
            self.app.quit()
        except:
            pass
       
        self.logger.info("Shutdown complete")


def kill_old_instance(base_dir):
    pid_file = os.path.join(base_dir, "bambibrowser.pid")
    current_pid = os.getpid()


    if os.path.exists(pid_file):
        try:
            old_pid = int(Path(pid_file).read_text().strip())
            if old_pid != current_pid:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(old_pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    os.kill(old_pid, signal.SIGTERM)


                time.sleep(1)
        except Exception:
            pass


    Path(pid_file).write_text(str(current_pid))


    def cleanup():
        try:
            if os.path.exists(pid_file):
                saved_pid = Path(pid_file).read_text().strip()
                if saved_pid == str(current_pid):
                    os.remove(pid_file)
        except Exception:
            pass


    atexit.register(cleanup)


def main():
    """Entry point."""
    if "--no-tray" in sys.argv:
        os.environ["BAMBI_NO_TRAY"] = "1"

    base_dir = get_base_dir()
    kill_old_instance(base_dir)

    try:
        app = BambiBrowserApp()
        return app.start()
    except Exception as e:
        logger = logging.getLogger("BambiBrowser")
        logger.critical(f"Fatal error during startup: {e}")
        logger.critical(traceback.format_exc())
       
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            qt_app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "BambiBrowser - Fatal Error",
                f"Failed to start BambiBrowser:\n\n{e}"
            )
        except:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())