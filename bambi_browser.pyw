#!/usr/bin/env python3
"""
BambiBrowser - Desktop Application
Fullscreen video player with HardLock capabilities.
Auto-elevates to administrator for full HardLock functionality.
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


def request_admin_privileges():
    """
    Request administrator privileges by relaunching the application.
    Returns True if already admin, False if user declined.
    """
    if is_admin():
        return True
    
    if sys.platform != "win32":
        return False  # Non-Windows, can't auto-elevate
    
    # Check if we already tried to elevate (prevent infinite loop)
    if os.environ.get("BAMBI_ELEVATED") == "1":
        return False
    
    # Show message to user
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        
        # Create a temporary QApplication for the dialog
        temp_app = QApplication.instance()
        if not temp_app:
            temp_app = QApplication(sys.argv)
        
        reply = QMessageBox.question(
            None,
            "Administrator Rights Required",
            "BambiBrowser needs Administrator rights for full HardLock functionality.\n\n"
            "Without admin rights:\n"
            "• HardLock will use fallback methods (less reliable)\n"
            "• Text Replacer (AutoHotkey) may not work in all applications\n\n"
            "Do you want to restart with Administrator privileges?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.No:
            return False
        
        # Relaunch as admin
        script = sys.argv[0]
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        
        # Set environment variable to prevent infinite elevation loop
        os.environ["BAMBI_ELEVATED"] = "1"
        
        # Use ShellExecute with runas to elevate
        ctypes.windll.shell32.ShellExecuteW(
            None,                               # hwnd
            "runas",                            # operation
            sys.executable,                     # file
            f'"{script}" {params}',             # parameters
            os.path.dirname(script),            # directory
            1                                   # show window (SW_SHOWNORMAL)
        )
        
        sys.exit(0)  # Exit current instance
        
    except Exception as e:
        print(f"Failed to request admin privileges: {e}")
        return False


def check_and_request_admin():
    """Check admin rights and request if needed."""
    if is_admin():
        print("[BambiBrowser] [OK] Running with Administrator privileges")
        return True
    
    print("[BambiBrowser] [WARN] Not running as Administrator")
    print("[BambiBrowser] Requesting elevation...")
    
    if request_admin_privileges():
        # This code won't be reached if elevation was successful (process exits)
        return True
    
    print("[BambiBrowser] [WARN] Continuing without Administrator privileges")
    print("[BambiBrowser]    - HardLock will use fallback methods")
    print("[BambiBrowser]    - Text Replacer may have limited functionality")
    return False


def show_admin_warning_dialog():
    """Show a warning dialog about limited functionality without admin rights."""
    try:
        from PyQt6.QtWidgets import QMessageBox
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Limited Functionality")
        msg.setText("Running without Administrator privileges")
        msg.setInformativeText(
            "Some features will be limited:\n\n"
            "🔒 HardLock: Fallback mode (less reliable)\n"
            "🔄 Text Replacer: May not work in all apps\n\n"
            "For full functionality, restart the application as Administrator."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
    except:
        pass


def create_version_file(base_dir: str, logger):
    """Create VERSION file if it doesn't exist."""
    version_file = Path(base_dir) / "VERSION"
    if not version_file.exists():
        try:
            with open(version_file, 'w', encoding='utf-8') as f:
                f.write("6.1.0")  # Current version
            logger.info("Created VERSION file with 6.1.0")
        except Exception as e:
            logger.warning(f"Could not create VERSION file: {e}")


class BambiBrowserApp:
    """Main application controller."""
    
    def __init__(self, skip_admin_check: bool = False):
        self.base_dir = get_base_dir()
        self.logger = setup_logging(self.base_dir)
        
        # Ensure VERSION file exists for auto-updater
        create_version_file(self.base_dir, self.logger)
        
        # Check admin rights (skip if we already elevated or user chose to skip)
        self.has_admin = is_admin()
        
        if not skip_admin_check and sys.platform == "win32" and not self.has_admin:
            # Only check once per session
            if os.environ.get("BAMBI_ADMIN_CHECKED") != "1":
                os.environ["BAMBI_ADMIN_CHECKED"] = "1"
                self.logger.warning("Running without administrator privileges - HardLock fallback will be used")
        
        # Enable high DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
       
        # Create Qt Application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("BambiBrowser")
        self.app.setApplicationVersion("6.1.0")
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
        
        # Initialize OS Text Replacer
        self.logger.info("Initializing OS Text Replacer...")
        try:
            from core.text_replacer import TextReplacer
            self.text_replacer = TextReplacer()
            self.logger.info("OS Text Replacer initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize TextReplacer: {e}")
            self.text_replacer = None
        
        # Initialize Settings Manager (CENTRALIZED)
        self.logger.info("Initializing Settings Manager...")
        try:
            from core.settings_manager import SettingsManager
            self.settings_manager = SettingsManager()
            self.logger.info("Settings Manager initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize Settings Manager: {e}")
            self.settings_manager = None
        
        # Ensure ffprobe is available for accurate duration detection
        self.logger.info("Checking for ffprobe (duration detection)...")
        try:
            from core.ffmpeg_downloader import ensure_ffprobe, get_ffprobe_status
            
            # Schedule ffprobe check after UI is ready (so dialog can be shown)
            self._ffprobe_path = None
            QTimer.singleShot(1000, self._initialize_ffprobe)
        except Exception as e:
            self.logger.warning(f"ffprobe initialization failed: {e}")
            self._ffprobe_path = None
        
        # UI components
        self.logger.info("Creating main window...")
        try:
            self.main_window = MainWindow(
                self.player,
                self.server,
                self.hard_lock,
                self.text_replacer,
                self.settings_manager
            )
        except Exception as e:
            self.logger.error(f"Failed to create main window: {e}")
            self.main_window = None
        
        # Auto-updater
        self.logger.info("Initializing auto-updater...")
        try:
            from core.auto_updater import AutoUpdater
            self.updater = AutoUpdater(Path(self.base_dir))
            self.update_dialog = None
            # Connect update signals
            self.updater.update_available.connect(self._on_update_available)
            self.updater.error_occurred.connect(self._on_update_error)
            self.logger.info("Auto-updater initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize auto-updater: {e}")
            self.updater = None
        
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
    
    def _initialize_ffprobe(self):
        """Initialize ffprobe after UI is ready."""
        try:
            from core.ffmpeg_downloader import ensure_ffprobe, get_ffprobe_status
            
            self._ffprobe_path = ensure_ffprobe(Path(self.base_dir))
            
            if self._ffprobe_path:
                self.logger.info(f"ffprobe available: {self._ffprobe_path}")
                # Update status in main window if possible
                if self.main_window:
                    status = get_ffprobe_status(Path(self.base_dir))
                    if status.get("available"):
                        self.logger.info(f"Duration detection: ACCURATE (ffprobe {status.get('version', 'unknown')})")
                    else:
                        self.logger.info("Duration detection: ESTIMATES ONLY (ffprobe not available)")
            else:
                self.logger.info("ffprobe not available - using duration estimates")
        except Exception as e:
            self.logger.warning(f"ffprobe initialization error: {e}")
    
    def _on_player_status_changed(self, is_playing: bool):
        """Handle player status changes."""
        if self.main_window:
            self.main_window.update_player_status(is_playing)
   
    def _on_server_status_changed(self, is_running: bool):
        """Handle server status changes."""
        if self.main_window:
            self.main_window.update_server_status(is_running)
    
    def _on_update_available(self, version: str, url: str):
        """Handle update available signal from auto-updater."""
        self.logger.info(f"Update available: {version} from {url}")
        try:
            from ui.update_dialog import UpdateDialog
            
            # Create update dialog
            self.update_dialog = UpdateDialog(self.main_window)
            self.update_dialog.set_updater(self.updater, self.updater.current_version)
            self.update_dialog.show_update_available(version, url)
        except Exception as e:
            self.logger.error(f"Failed to show update dialog: {e}")
    
    def _on_update_error(self, error: str):
        """Handle updater errors."""
        self.logger.warning(f"Auto-updater error: {error}")
    
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
                self.main_window.status_label.setText("⚠️ No Admin - Limited HardLock & Text Replacer")
                self.main_window.status_label.setStyleSheet("""
                    font-size: 11px;
                    color: #ffcc9b;
                    padding: 5px;
                """)
                
                # Schedule warning dialog
                QTimer.singleShot(2000, show_admin_warning_dialog)
        
        # Start auto-updater check (delayed by 3 seconds to let UI settle)
        if self.updater:
            self.logger.info("Starting auto-updater background check...")
            QTimer.singleShot(3000, self.updater.check_for_updates)
        
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
        
        # Stop auto-updater
        if hasattr(self, 'updater') and self.updater:
            try:
                self.updater.cleanup()
                self.logger.info("Auto-updater stopped")
            except Exception as e:
                self.logger.error(f"Error stopping auto-updater: {e}")
        
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
        
        if hasattr(self, 'text_replacer') and self.text_replacer:
            try:
                self.text_replacer.stop()
                self.logger.info("Text Replacer stopped")
            except Exception as e:
                self.logger.error(f"Error stopping text replacer: {e}")
        
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
    
    if "--no-admin" in sys.argv:
        os.environ["BAMBI_SKIP_ADMIN"] = "1"
    
    if "--no-ffprobe" in sys.argv:
        os.environ["BAMBI_SKIP_FFPROBE"] = "1"
    
    # Request admin privileges unless skipped
    if os.environ.get("BAMBI_SKIP_ADMIN") != "1":
        check_and_request_admin()

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