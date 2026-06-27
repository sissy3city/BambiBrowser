"""
AutoHotkey manager – find, download, generate scripts, and run process.
"""

import os
import logging
import subprocess
import tempfile
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional, Dict

# Import get_base_dir from core.utils
from core.utils import get_base_dir

logger = logging.getLogger("BambiBrowser.AHKManager")

AHK_DOWNLOAD_URL = "https://www.autohotkey.com/download/1.1/AutoHotkey_1.1.37.02.zip"


class AHKManager:
    """Manages AutoHotkey executable, script generation, and lifecycle."""

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

    def start(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Start AutoHotkey with the given replacement rules."""
        if not self.is_available:
            logger.error("AutoHotkey not available")
            return False

        self.stop()  # ensure no stale process

        script_content = self._generate_script(rules, use_prefix, prefix_char)
        temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
        temp_dir.mkdir(exist_ok=True)
        self._script_path = temp_dir / "bambi_replacements.ahk"
        self._script_path.write_text(script_content, encoding="utf-8")

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                [self._ahk_exe, str(self._script_path)],
                creationflags=creationflags
            )
            # brief wait to catch immediate exit
            import time
            time.sleep(0.3)
            if self._process.poll() is not None:
                logger.error("AutoHotkey exited immediately")
                return False
            logger.info(f"AutoHotkey started with {len(rules)} rules")
            return True
        except Exception as e:
            logger.error(f"Failed to start AutoHotkey: {e}")
            return False

    def stop(self) -> None:
        """Stop the running AutoHotkey process and clean up script."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except:
                try:
                    self._process.kill()
                except:
                    pass
            self._process = None
            logger.info("AutoHotkey stopped")

        if self._script_path and self._script_path.exists():
            try:
                self._script_path.unlink()
            except:
                pass

    def reload(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Reload with new rules (stop + start)."""
        return self.start(rules, use_prefix, prefix_char)

    def get_script_preview(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> str:
        """Return the script that would be generated (for preview)."""
        return self._generate_script(rules, use_prefix, prefix_char)

    # ---------- Internal ----------
    def _find_or_download_ahk(self) -> None:
        """Locate AHK executable; if missing, download it."""
        self._ahk_exe = self._find_ahk()
        if self._ahk_exe:
            return

        logger.info("AutoHotkey not found – attempting to download...")
        if self._download_ahk():
            self._ahk_exe = self._find_ahk()
            if self._ahk_exe:
                logger.info(f"AutoHotkey installed at: {self._ahk_exe}")
                return

        logger.error("Could not obtain AutoHotkey. Please install manually.")

    def _find_ahk(self) -> Optional[str]:
        """Search for AutoHotkey executable in common locations and bundled folder."""
        base = Path(get_base_dir())  # <-- FIX: use get_base_dir() for bundled location
        candidates = [
            # System installs
            r"C:\Program Files\AutoHotkey\AutoHotkeyU64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
            # Bundled (next to executable)
            str(base / "ahk" / "AutoHotkeyU64.exe"),
            str(base / "ahk" / "AutoHotkey64.exe"),
            str(base / "ahk" / "AutoHotkey.exe"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path

        # PATH fallback
        import shutil
        exe = shutil.which("AutoHotkeyU64.exe") or shutil.which("AutoHotkey.exe")
        return exe

    def _download_ahk(self) -> bool:
        """Download and extract AutoHotkey to the bundled `ahk/` folder."""
        ahk_dir = Path(get_base_dir()) / "ahk"   # <-- FIX: use get_base_dir()
        ahk_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ahk_dir / "ahk-u64.zip"

        try:
            logger.info(f"Downloading from {AHK_DOWNLOAD_URL} ...")
            urllib.request.urlretrieve(AHK_DOWNLOAD_URL, str(zip_path))
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(ahk_dir)
            zip_path.unlink()

            # Move files from possible subfolder to root ahk/
            for item in ahk_dir.iterdir():
                if item.is_dir() and item.name.lower() in ("autohotkey", "ahk"):
                    for sub in item.iterdir():
                        target = ahk_dir / sub.name
                        if not target.exists():
                            shutil.move(str(sub), str(target))
                    shutil.rmtree(item)

            # Ensure at least one AutoHotkey*.exe exists
            if any(ahk_dir.glob("AutoHotkey*.exe")):
                return True
            else:
                logger.error("No AutoHotkey executable found after extraction")
                return False
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return False

    def _generate_script(self, rules: Dict[str, str], use_prefix: bool, prefix_char: str) -> str:
        """Generate the AHK script content."""
        lines = [
            "; BambiBrowser – Auto‑generated Text Replacement",
            "#NoEnv",
            "#SingleInstance Force",
            "#Persistent",
            "#NoTrayIcon",
            "SendMode Input",
            "SetWorkingDir %A_ScriptDir%",
            ""
        ]
        if use_prefix:
            lines.append(f"; Prefix mode: type '{prefix_char}' before trigger")
            for original, replacement in rules.items():
                if not original or not replacement:
                    continue
                esc = replacement.replace("`", "``").replace("%", "`%").replace(";", "`;")
                lines.append(f":*:{prefix_char}{original}::{esc}")
        else:
            lines.append("; Auto‑replace mode (triggers on space/enter)")
            for original, replacement in rules.items():
                if not original or not replacement:
                    continue
                esc = replacement.replace("`", "``").replace("%", "`%").replace(";", "`;")
                lines.append(f"::{original}::{esc}")

        lines.append("")
        lines.append("Menu, Tray, Tip, BambiBrowser AHK Active")
        lines.append('TrayTip, BambiBrowser, Text replacement active!, 3, 1')
        return "\n".join(lines)