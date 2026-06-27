#!/usr/bin/env python3
"""
BambiBrowser – Desktop Application
Fullscreen video player with HardLock, OS‑level text replacement, and Bambi Gag.
Auto‑elevates to administrator for full HardLock functionality.
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

base_dir = Path(__file__).parent
os.environ["PATH"] = str(base_dir) + os.pathsep + os.environ.get("PATH", "")


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
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def request_admin_privileges():
    if is_admin():
        return True
    if sys.platform != "win32":
        return False
    if os.environ.get("BAMBI_ELEVATED") == "1":
        return False
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        temp_app = QApplication.instance() or QApplication(sys.argv)
        reply = QMessageBox.question(
            None,
            "Administrator Rights Required",
            "BambiBrowser needs Administrator rights for full HardLock functionality.\n\n"
            "Without admin rights:\n"
            "• HardLock will use fallback methods (less reliable)\n"
            "• Text Replacer may not work in all applications\n"
            "• Bambi Gag may have limited scope\n\n"
            "Do you want to restart with Administrator privileges?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.No:
            return False
        script = sys.argv[0]
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        os.environ["BAMBI_ELEVATED"] = "1"
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            f'"{script}" {params}',
            os.path.dirname(script), 1
        )
        sys.exit(0)
    except Exception as e:
        print(f"Failed to request admin: {e}")
        return False


# Add the missing wrapper function
def check_and_request_admin():
    """Wrapper for request_admin_privileges."""
    return request_admin_privileges()


def kill_old_instance(base_dir):
    pid_file = os.path.join(base_dir, "bambibrowser.pid")
    current_pid = os.getpid()
    if os.path.exists(pid_file):
        try:
            old_pid = int(Path(pid_file).read_text().strip())
            if old_pid != current_pid:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(old_pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    os.kill(old_pid, signal.SIGTERM)
                time.sleep(1)
        except:
            pass
    Path(pid_file).write_text(str(current_pid))

    def cleanup():
        try:
            if os.path.exists(pid_file):
                saved_pid = Path(pid_file).read_text().strip()
                if saved_pid == str(current_pid):
                    os.remove(pid_file)
        except:
            pass
    atexit.register(cleanup)


def cleanup_leftover_ahk_scripts():
    """Kill any leftover AHK processes from previous BambiBrowser instances."""
    if sys.platform != "win32":
        return
    try:
        # Find all AutoHotkey processes with command lines containing our script names
        result = subprocess.run(
            ["wmic", "process", "where", "name like 'AutoHotkey%'", "get", "processid,commandline", "/format:csv"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            for line in lines[1:]:  # skip header
                parts = line.split(',')
                if len(parts) >= 2:
                    # commandline might be in first column, pid in last
                    cmd = parts[0].lower() if parts else ""
                    pid = parts[-1].strip() if len(parts) > 1 else ""
                    if "bambi_replacements.ahk" in cmd or "bambi_gag.ahk" in cmd:
                        if pid and pid.isdigit():
                            try:
                                subprocess.run(["taskkill", "/F", "/PID", pid],
                                               capture_output=True, check=False)
                                logger = logging.getLogger("BambiBrowser")
                                logger.info(f"Killed leftover AHK process {pid}")
                            except:
                                pass
    except Exception as e:
        # Silent fail
        pass


def create_version_file(base_dir, logger):
    version_file = Path(base_dir) / "VERSION"
    if not version_file.exists():
        try:
            with open(version_file, 'w', encoding='utf-8') as f:
                f.write("6.3.0")   # <-- Updated to 6.3.0
            logger.info("Created VERSION file with 6.3.0")
        except Exception as e:
            logger.warning(f"Could not create VERSION file: {e}")


class BambiBrowserApp:
    def __init__(self, skip_admin_check=False):
        self.base_dir = get_base_dir()
        self.logger = setup_logging(self.base_dir)
        create_version_file(self.base_dir, self.logger)

        self.has_admin = is_admin()
        if not skip_admin_check and sys.platform == "win32" and not self.has_admin:
            if os.environ.get("BAMBI_ADMIN_CHECKED") != "1":
                os.environ["BAMBI_ADMIN_CHECKED"] = "1"
                self.logger.warning("Running without admin – HardLock fallback will be used")

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("BambiBrowser")
        self.app.setApplicationVersion("6.3.0")   # <-- Updated to 6.3.0
        self.app.setQuitOnLastWindowClosed(False)

        # Import core modules
        from core.hard_lock import HardLock
        from core.player import VideoPlayer
        from core.server import BambiServer
        from core.text_replacer import TextReplacer
        from core.settings_manager import SettingsManager
        from core.gag_manager import GagManager
        from ui.main_window import MainWindow
        from ui.tray_icon import TrayIconManager
        from PyQt6.QtGui import QIcon

        # Set icon
        icon_path = os.path.join(self.base_dir, "resources", "icon.png")
        if os.path.exists(icon_path):
            self.app.setWindowIcon(QIcon(icon_path))

        # Core components
        self.logger.info("Initializing HardLock...")
        self.hard_lock = HardLock()

        self.logger.info("Initializing Settings Manager...")
        self.settings_manager = SettingsManager()

        self.logger.info("Initializing VideoPlayer...")
        self.player = VideoPlayer(self.hard_lock)

        self.logger.info("Initializing HTTP Server...")
        self.server = BambiServer(self.player, port=5655)

        self.logger.info("Initializing OS Text Replacer...")
        self.text_replacer = TextReplacer(self.settings_manager)

        self.logger.info("Initializing Gag Manager...")
        self.gag_manager = GagManager(Path(self.base_dir), self.settings_manager)

        # Ensure ffprobe
        self._ffprobe_path = None
        QTimer.singleShot(1000, self._initialize_ffprobe)

        # UI
        self.logger.info("Creating main window...")
        self.main_window = MainWindow(
            self.player,
            self.server,
            self.hard_lock,
            self.text_replacer,
            self.settings_manager,
            self.gag_manager
        )

        # Auto-updater
        self.logger.info("Initializing auto-updater...")
        from core.auto_updater import AutoUpdater
        self.updater = AutoUpdater(Path(self.base_dir))
        self.update_dialog = None
        self.updater.update_available.connect(self._on_update_available)
        self.updater.error_occurred.connect(self._on_update_error)

        # Tray – pass shutdown callback
        self.logger.info("Setting up system tray...")
        self.tray = TrayIconManager(self.main_window, self.app, self.shutdown)

        # Signals
        self.player.status_changed.connect(self._on_player_status_changed)
        self.server.status_changed.connect(self._on_server_status_changed)

        # Ensure cleanup on app quit
        self._shutting_down = False
        self.app.aboutToQuit.connect(self._on_about_to_quit)

        self.logger.info(f"BambiBrowser initialized (Admin: {self.has_admin})")

    def _initialize_ffprobe(self):
        try:
            from core.ffmpeg_downloader import ensure_ffprobe, get_ffprobe_status
            self._ffprobe_path = ensure_ffprobe(Path(self.base_dir))
            if self._ffprobe_path:
                self.logger.info(f"ffprobe available: {self._ffprobe_path}")
        except Exception as e:
            self.logger.warning(f"ffprobe init error: {e}")

    def _on_player_status_changed(self, is_playing):
        if self.main_window:
            self.main_window.update_player_status(is_playing)

    def _on_server_status_changed(self, is_running):
        if self.main_window:
            self.main_window.update_server_status(is_running)

    def _on_update_available(self, version, url):
        self.logger.info(f"Update available: {version}")
        try:
            from ui.update_dialog import UpdateDialog
            self.update_dialog = UpdateDialog(self.main_window)
            self.update_dialog.set_updater(self.updater, self.updater.current_version)
            self.update_dialog.show_update_available(version, url)
        except Exception as e:
            self.logger.error(f"Failed to show update dialog: {e}")

    def _on_update_error(self, error):
        self.logger.warning(f"Auto-updater error: {error}")

    def _on_about_to_quit(self):
        """Called when the application is about to quit."""
        if not self._shutting_down:
            self.shutdown()

    def start(self):
        if self.server:
            threading.Thread(target=self._start_server, daemon=True).start()
        if self.main_window:
            self.main_window.show()
            if not self.has_admin:
                self.main_window.status_label.setText("⚠️ No Admin - Limited HardLock & Text Replacer")
                self.main_window.status_label.setStyleSheet(
                    "font-size: 11px; color: #ffcc9b; padding: 5px;"
                )
                QTimer.singleShot(2000, self._show_admin_warning)
        if self.updater:
            QTimer.singleShot(3000, self.updater.check_for_updates)
        if self.tray:
            self.tray.start()
        signal.signal(signal.SIGINT, lambda *args: self.shutdown())
        self.logger.info("Application started")
        try:
            return self.app.exec()
        except Exception as e:
            self.logger.critical(f"Application crashed: {e}")
            return 1

    def _start_server(self):
        if self.server:
            try:
                if not self.server.start():
                    self.logger.error("Failed to start HTTP server")
            except Exception as e:
                self.logger.error(f"HTTP server error: {e}")

    def _show_admin_warning(self):
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.main_window,
                "Limited Functionality",
                "Running without Administrator privileges.\n\n"
                "HardLock will use fallback mode (less reliable).\n"
                "Text Replacer and Gag may not work in all apps.\n\n"
                "Restart as Administrator for full features."
            )
        except:
            pass

    def shutdown(self):
        """Clean shutdown of all components."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.logger.info("Shutting down...")

        # Stop text replacer and gag first
        if self.text_replacer:
            self.text_replacer.stop()
        if self.gag_manager:
            self.gag_manager.cleanup()

        # Stop other components
        if self.updater:
            self.updater.cleanup()
        if self.server:
            self.server.stop()
        if self.hard_lock:
            self.hard_lock.unlock()
        if self.player:
            self.player.cleanup()
        if self.tray:
            self.tray.stop()

        # Kill any leftover AHK scripts (safety net)
        cleanup_leftover_ahk_scripts()

        # Allow processes to exit cleanly
        time.sleep(0.2)
        try:
            self.app.quit()
        except:
            pass
        self.logger.info("Shutdown complete")


def main():
    # Kill any leftover AHK scripts from previous runs
    cleanup_leftover_ahk_scripts()

    if "--no-tray" in sys.argv:
        os.environ["BAMBI_NO_TRAY"] = "1"
    if "--no-admin" in sys.argv:
        os.environ["BAMBI_SKIP_ADMIN"] = "1"
    if os.environ.get("BAMBI_SKIP_ADMIN") != "1":
        check_and_request_admin()

    base_dir = get_base_dir()
    kill_old_instance(base_dir)
    try:
        app = BambiBrowserApp()
        return app.start()
    except Exception as e:
        logger = logging.getLogger("BambiBrowser")
        logger.critical(f"Fatal startup error: {e}")
        logger.critical(traceback.format_exc())
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            qt_app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "BambiBrowser - Fatal Error", f"Failed to start:\n\n{e}")
        except:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())