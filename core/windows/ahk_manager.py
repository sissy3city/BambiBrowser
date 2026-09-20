"""
AutoHotkey manager - find, download, run, and stop an AutoHotkey script.

Shared by TextReplacer (rule-based replacement script) and GagManager
(the fixed Bambi Gag script) - each owns its own AHKManager instance and
its own AHK process. `run_script()`/`stop()` are the generic process
lifecycle; `start()`/`reload()`/`get_script_preview()` are a convenience
layer on top for the replacement-rules use case.
"""

import os
import logging
import subprocess
import tempfile
import time
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional, Dict

from core.utils import get_base_dir

logger = logging.getLogger("BambiBrowser.AHKManager")

AHK_DOWNLOAD_URL = "https://www.autohotkey.com/download/1.1/AutoHotkey_1.1.37.02.zip"


class AHKManager:
    """Manages one AutoHotkey executable, script file, and process."""

    def __init__(self):
        self._ahk_exe: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._script_path: Optional[Path] = None
        self._find_or_download_ahk()

    # ---------- Public API ----------
    @property
    def is_available(self) -> bool:
        return self._ahk_exe is not None and Path(self._ahk_exe).exists()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def ahk_path(self) -> Optional[str]:
        return self._ahk_exe

    def run_script(self, script_content: str, script_name: str = "bambi_script.ahk") -> bool:
        """Write script_content to a temp file and launch AutoHotkey with it.

        Stops any script this manager is already running first.
        """
        if not self.is_available:
            logger.error("AutoHotkey not available")
            return False

        self.stop()

        temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
        temp_dir.mkdir(exist_ok=True)
        self._script_path = temp_dir / script_name
        self._script_path.write_text(script_content, encoding="utf-8")

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                [self._ahk_exe, str(self._script_path)],
                creationflags=creationflags
            )
            time.sleep(0.3)
            if self._process.poll() is not None:
                logger.error("AutoHotkey exited immediately")
                return False
            logger.info(f"AutoHotkey running: {script_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to start AutoHotkey: {e}")
            return False

    def stop(self) -> None:
        """Stop the running AutoHotkey process and clean up its script file."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

            # Force kill if still running - AutoHotkey scripts sometimes ignore terminate().
            if self._process.poll() is None:
                try:
                    import psutil
                    psutil.Process(self._process.pid).kill()
                except Exception:
                    pass

            time.sleep(0.1)
            self._process = None
            logger.info("AutoHotkey stopped")

        if self._script_path and self._script_path.exists():
            try:
                self._script_path.unlink()
            except Exception:
                pass

    # ---------- Text-replacement convenience API ----------
    def start(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Generate a replacement script from rules and run it."""
        return self.run_script(
            self._generate_replacement_script(rules, use_prefix, prefix_char),
            "bambi_replacements.ahk"
        )

    def reload(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Reload with new rules (stop + start)."""
        return self.start(rules, use_prefix, prefix_char)

    def get_script_preview(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> str:
        """Return the replacement script that would be generated (for preview)."""
        return self._generate_replacement_script(rules, use_prefix, prefix_char)

    # ---------- Internal ----------
    def _find_or_download_ahk(self) -> None:
        """Locate AHK executable; if missing, download it."""
        self._ahk_exe = self._find_ahk()
        if self._ahk_exe:
            logger.info(f"Using AutoHotkey: {self._ahk_exe}")
            return

        logger.info("AutoHotkey not found - attempting to download...")
        if self._download_ahk():
            self._ahk_exe = self._find_ahk()
            if self._ahk_exe:
                logger.info(f"AutoHotkey installed at: {self._ahk_exe}")
                return

        logger.error("Could not obtain AutoHotkey. Please install manually.")

    def _find_ahk(self) -> Optional[str]:
        """Search bundled ahk/ folder first, then system installs, then PATH."""
        ahk_dir = Path(get_base_dir()) / "ahk"
        preferred = ["AutoHotkeyU64.exe", "AutoHotkey64.exe", "AutoHotkeyU32.exe", "AutoHotkeyA32.exe", "AutoHotkey.exe"]
        for exe_name in preferred:
            exe_path = ahk_dir / exe_name
            if exe_path.exists():
                logger.info(f"Found portable AutoHotkey: {exe_path}")
                return str(exe_path)
        if ahk_dir.exists():
            for exe in ahk_dir.rglob("AutoHotkey*.exe"):
                logger.info(f"Found portable AutoHotkey at: {exe}")
                return str(exe)

        candidates = [
            r"C:\Program Files\AutoHotkey\AutoHotkeyU64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
        ]
        for path in candidates:
            if Path(path).exists():
                logger.info(f"Found AutoHotkey at: {path}")
                return path

        ahk_in_path = shutil.which("AutoHotkeyU64.exe") or shutil.which("AutoHotkey.exe")
        if ahk_in_path:
            logger.info(f"Found AutoHotkey in PATH: {ahk_in_path}")
            return ahk_in_path
        return None

    def _download_ahk(self) -> bool:
        """Download and extract AutoHotkey to the bundled ahk/ folder."""
        ahk_dir = Path(get_base_dir()) / "ahk"
        ahk_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ahk_dir / "ahk-u64.zip"

        try:
            logger.info(f"Downloading AutoHotkey from {AHK_DOWNLOAD_URL}...")
            urllib.request.urlretrieve(AHK_DOWNLOAD_URL, str(zip_path))
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(ahk_dir)
            zip_path.unlink()

            # Move files out of a possible subfolder into the root ahk/ dir.
            for item in ahk_dir.iterdir():
                if item.is_dir() and item.name.lower() in ("autohotkey", "ahk"):
                    for sub in item.iterdir():
                        target = ahk_dir / sub.name
                        if not target.exists():
                            shutil.move(str(sub), str(target))
                    shutil.rmtree(item)

            if any(ahk_dir.glob("AutoHotkey*.exe")):
                logger.info("AutoHotkey installed successfully!")
                return True
            logger.error("No AutoHotkey executable found after extraction")
            return False
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return False

    def _generate_replacement_script(self, rules: Dict[str, str], use_prefix: bool, prefix_char: str) -> str:
        """Generate the AHK text-replacement script content."""
        script_lines = [
            "; ================================================",
            "; BambiBrowser Auto-Generated Text Replacement",
            "; ================================================",
            "", "#NoEnv", "#SingleInstance Force", "#Persistent",
            "#NoTrayIcon", "SendMode Input", "SetWorkingDir %A_ScriptDir%", ""
        ]
        if use_prefix:
            script_lines.append(f"; Prefix Mode: Type '{prefix_char}' then trigger word")
            script_lines.append("")
            for original, replacement in rules.items():
                if not original or not replacement:
                    continue
                escaped = replacement.replace("`", "``").replace("%", "`%").replace(";", "`;")
                script_lines.append(f":*:{prefix_char}{original}::{escaped}")
        else:
            script_lines.append("; Auto-Replace Mode (Requires Space/Enter after word)")
            script_lines.append("")
            for original, replacement in rules.items():
                if not original or not replacement:
                    continue
                escaped = replacement.replace("`", "``").replace("%", "`%").replace(";", "`;")
                script_lines.append(f"::{original}::{escaped}")
        script_lines.extend(["", "Menu, Tray, Tip, BambiBrowser AHK Active", "TrayTip, BambiBrowser, Text replacement active!, 3, 1"])
        return "\n".join(script_lines)
