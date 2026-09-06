"""Autostart at login - Windows Task Scheduler, or an XDG autostart .desktop file on Linux."""

import subprocess
import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger("BambiBrowser.Autostart")

TASK_NAME = "BambiBrowser"
_DESKTOP_FILE_NAME = "bambibrowser.desktop"


def _get_launch_command() -> str:
    """Return the command string the task will run (Windows)."""
    if getattr(sys, "frozen", False):
        # Compiled exe — run it directly
        return f'"{sys.executable}"'
    else:
        base_dir = Path(__file__).parent.parent
        script = base_dir / "bambi_browser.pyw"
        # Use pythonw so no console window appears
        python = Path(sys.executable)
        pythonw = python.parent / "pythonw.exe"
        exe = str(pythonw) if pythonw.exists() else str(python)
        return f'"{exe}" "{script}"'


def _get_autostart_desktop_path() -> Path:
    """Path to the XDG autostart .desktop file (Linux)."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "autostart" / _DESKTOP_FILE_NAME


def _get_linux_exec_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    base_dir = Path(__file__).parent.parent
    script = base_dir / "bambi_browser.pyw"
    return f'"{sys.executable}" "{script}"'


def is_enabled() -> bool:
    """Return True if the autostart entry exists."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", TASK_NAME],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Could not query autostart task: {e}")
            return False
    else:
        return _get_autostart_desktop_path().exists()


def enable() -> tuple[bool, str]:
    """Register the app to launch at login. Returns (success, message)."""
    if sys.platform == "win32":
        try:
            command = _get_launch_command()
            result = subprocess.run(
                [
                    "schtasks", "/Create",
                    "/TN", TASK_NAME,
                    "/TR", command,
                    "/SC", "ONLOGON",
                    "/RL", "HIGHEST",
                    "/F",
                ],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                logger.info(f"Autostart task created: {command}")
                return True, "Autostart enabled."
            else:
                msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"Failed to create autostart task: {msg}")
                return False, msg
        except Exception as e:
            logger.error(f"Exception creating autostart task: {e}")
            return False, str(e)
    else:
        try:
            desktop_path = _get_autostart_desktop_path()
            desktop_path.parent.mkdir(parents=True, exist_ok=True)
            exec_cmd = _get_linux_exec_command()
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=BambiBrowser\n"
                f"Exec={exec_cmd}\n"
                "X-GNOME-Autostart-enabled=true\n"
                "NoDisplay=false\n"
            )
            desktop_path.write_text(content, encoding="utf-8")
            logger.info(f"Autostart entry created: {desktop_path}")
            return True, "Autostart enabled."
        except Exception as e:
            logger.error(f"Exception creating autostart entry: {e}")
            return False, str(e)


def disable() -> tuple[bool, str]:
    """Remove the autostart entry. Returns (success, message)."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                logger.info("Autostart task removed.")
                return True, "Autostart disabled."
            else:
                msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"Failed to remove autostart task: {msg}")
                return False, msg
        except Exception as e:
            logger.error(f"Exception removing autostart task: {e}")
            return False, str(e)
    else:
        try:
            desktop_path = _get_autostart_desktop_path()
            if desktop_path.exists():
                desktop_path.unlink()
            logger.info("Autostart entry removed.")
            return True, "Autostart disabled."
        except Exception as e:
            logger.error(f"Exception removing autostart entry: {e}")
            return False, str(e)
