"""Administrator elevation and legacy autostart cleanup - Windows only."""

import ctypes
import logging
import os
import sys
import winreg

logger = logging.getLogger("BambiBrowser.Elevation")


def is_admin() -> bool:
    """Return True if the current process has Administrator rights."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin_privileges() -> bool:
    """Offer to relaunch elevated via ShellExecuteW "runas".

    Returns False if already admin, if the user declines, or if an
    elevation attempt already happened this run (BAMBI_ELEVATED). On
    success this process exits and the elevated copy takes over.
    """
    if is_admin():
        return True
    if os.environ.get("BAMBI_ELEVATED") == "1":
        return False
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
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
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        else:
            executable = sys.executable
            script = sys.argv[0]
            params = ' '.join([f'"{script}"'] + [f'"{arg}"' for arg in sys.argv[1:]])
        os.environ["BAMBI_ELEVATED"] = "1"
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params,
            os.path.dirname(executable), 1
        )
        sys.exit(0)
    except Exception as e:
        print(f"Failed to request admin: {e}")
        return False


def remove_legacy_autostart_registry_entry() -> None:
    """Remove the old HKCU Run-key autostart entry, if one is still present.

    Older BambiBrowser versions registered autostart directly under the
    registry Run key. Autostart is now handled by core.autostart via Task
    Scheduler, so make sure no stale Run entry causes a duplicate launch.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, "BambiBrowser")
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass  # Already not present
    except Exception as e:
        logger.debug(f"Could not remove registry autostart entry: {e}")
