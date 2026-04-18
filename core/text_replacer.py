"""OS-level text replacement powered by AutoHotkey - 100% reliable system-wide."""

import logging
import os
import subprocess
import tempfile
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger("BambiBrowser.TextReplacer")

# AutoHotkey download URL (Unicode 64-bit portable version)
AHK_DOWNLOAD_URL = "https://www.autohotkey.com/download/ahk-u64.zip"


class AHKDownloader(QThread):
    """Background thread for downloading AutoHotkey."""
    
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, target_dir: Path):
        super().__init__()
        self.target_dir = target_dir
    
    def run(self):
        """Download and extract AutoHotkey."""
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            zip_path = self.target_dir / "ahk-u64.zip"
            
            self.progress.emit("Downloading AutoHotkey...")
            logger.info(f"Downloading from {AHK_DOWNLOAD_URL}")
            
            urllib.request.urlretrieve(AHK_DOWNLOAD_URL, str(zip_path))
            
            self.progress.emit("Extracting AutoHotkey...")
            logger.info("Extracting AutoHotkey...")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.target_dir)
            
            zip_path.unlink()
            
            # Move files from subdirectory if needed
            for item in self.target_dir.iterdir():
                if item.is_dir() and item.name.lower() in ["autohotkey", "ahk"]:
                    for subitem in item.iterdir():
                        target = self.target_dir / subitem.name
                        if not target.exists():
                            shutil.move(str(subitem), str(target))
                    shutil.rmtree(item)
            
            # Find the actual exe
            exe_path = None
            for exe in self.target_dir.rglob("AutoHotkey*.exe"):
                exe_path = exe
                break
            
            if exe_path and exe_path.exists():
                self.progress.emit("AutoHotkey installed successfully!")
                logger.info(f"AutoHotkey installed at: {exe_path}")
                self.finished.emit(True, str(exe_path))
            else:
                self.progress.emit("Failed to find AutoHotkey.exe after extraction")
                logger.error("AutoHotkey.exe not found after extraction")
                self.finished.emit(False, "")
                
        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            self.progress.emit(error_msg)
            logger.error(error_msg)
            self.finished.emit(False, "")


class AHKManager:
    """Manages AutoHotkey script generation and execution."""
    
    def __init__(self):
        self._ahk_process: Optional[subprocess.Popen] = None
        self._script_path: Optional[Path] = None
        self._ahk_exe: Optional[str] = None
        
        # Find or download AHK
        self._ahk_exe = self._find_autohotkey()
        
        if not self._ahk_exe:
            logger.info("AutoHotkey not found - will attempt to download")
            self._download_autohotkey_sync()
            self._ahk_exe = self._find_autohotkey()
        
        if self._ahk_exe:
            logger.info(f"Using AutoHotkey: {self._ahk_exe}")
    
    def _get_ahk_dir(self) -> Path:
        """Get the directory for portable AutoHotkey."""
        base_dir = Path(__file__).parent.parent
        return base_dir / "ahk"
    
    def _find_autohotkey(self) -> Optional[str]:
        """Find AutoHotkey executable."""
        # Check common installation paths
        candidates = [
            r"C:\Program Files\AutoHotkey\AutoHotkeyU64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
        ]
        
        # Check portable in app directory
        ahk_dir = self._get_ahk_dir()
        preferred = ["AutoHotkeyU64.exe", "AutoHotkey64.exe", "AutoHotkeyU32.exe", "AutoHotkeyA32.exe", "AutoHotkey.exe"]
        
        for exe_name in preferred:
            exe_path = ahk_dir / exe_name
            if exe_path.exists():
                logger.info(f"Found portable AutoHotkey: {exe_path}")
                return str(exe_path)
        
        # Check subdirectories
        if ahk_dir.exists():
            for exe in ahk_dir.rglob("AutoHotkey*.exe"):
                logger.info(f"Found portable AutoHotkey at: {exe}")
                return str(exe)
        
        for path in candidates:
            if Path(path).exists():
                logger.info(f"Found AutoHotkey at: {path}")
                return path
        
        # Check PATH
        ahk_in_path = shutil.which("AutoHotkeyU64.exe") or shutil.which("AutoHotkey.exe")
        if ahk_in_path:
            logger.info(f"Found AutoHotkey in PATH: {ahk_in_path}")
            return ahk_in_path
        
        return None
    
    def _download_autohotkey_sync(self):
        """Synchronously download AutoHotkey."""
        ahk_dir = self._get_ahk_dir()
        ahk_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = ahk_dir / "ahk-u64.zip"
        
        try:
            logger.info(f"Downloading AutoHotkey from {AHK_DOWNLOAD_URL}...")
            print("[BambiBrowser] Downloading AutoHotkey (Unicode 64-bit, ~3.5 MB)...")
            
            urllib.request.urlretrieve(AHK_DOWNLOAD_URL, str(zip_path))
            
            logger.info("Extracting AutoHotkey...")
            print("[BambiBrowser] Extracting AutoHotkey...")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(ahk_dir)
            
            zip_path.unlink()
            
            # Move files from subdirectory if needed
            for item in ahk_dir.iterdir():
                if item.is_dir() and item.name.lower() in ["autohotkey", "ahk"]:
                    for subitem in item.iterdir():
                        target = ahk_dir / subitem.name
                        if not target.exists():
                            shutil.move(str(subitem), str(target))
                    shutil.rmtree(item)
            
            logger.info("AutoHotkey installed successfully!")
            print("[BambiBrowser] ✅ AutoHotkey installed successfully!")
            
        except Exception as e:
            logger.error(f"Failed to download AutoHotkey: {e}")
            print(f"[BambiBrowser] ❌ Failed to download: {e}")
    
    @property
    def is_available(self) -> bool:
        return self._ahk_exe is not None and Path(self._ahk_exe).exists()
    
    @property
    def is_running(self) -> bool:
        return self._ahk_process is not None and self._ahk_process.poll() is None
    
    def generate_script(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> str:
        """Generate an AutoHotkey script for the given replacement rules."""
        script_lines = [
            "; ================================================",
            "; BambiBrowser Auto-Generated Text Replacement",
            "; ================================================",
            "",
            "#NoEnv",
            "#SingleInstance Force",
            "#Persistent",
            "#NoTrayIcon",
            "SendMode Input",
            "SetWorkingDir %A_ScriptDir%",
            "",
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
                # NO ASTERISK = requires ending character (space, enter, tab, punctuation)
                script_lines.append(f"::{original}::{escaped}")
        
        script_lines.extend([
            "",
            "Menu, Tray, Tip, BambiBrowser AHK Active",
            "TrayTip, BambiBrowser, Text replacement active!, 3, 1",
        ])
        
        return "\n".join(script_lines)
    
    def start(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Start AutoHotkey with the generated script."""
        if not self.is_available:
            logger.error("AutoHotkey not available")
            return False
        
        self.stop()
        
        try:
            script_content = self.generate_script(rules, use_prefix, prefix_char)
            
            temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
            temp_dir.mkdir(exist_ok=True)
            
            self._script_path = temp_dir / "bambi_replacements.ahk"
            self._script_path.write_text(script_content, encoding="utf-8")
            
            logger.info(f"Script saved to: {self._script_path}")
            
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._ahk_process = subprocess.Popen(
                [self._ahk_exe, str(self._script_path)],
                creationflags=creationflags
            )
            
            import time
            time.sleep(0.5)
            
            if self._ahk_process.poll() is not None:
                logger.error("AutoHotkey exited immediately")
                return False
            
            logger.info(f"AutoHotkey running with {len(rules)} rules")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start: {e}")
            return False
    
    def stop(self):
        """Stop the AutoHotkey process."""
        if self._ahk_process:
            try:
                self._ahk_process.terminate()
                self._ahk_process.wait(timeout=2)
            except:
                try:
                    self._ahk_process.kill()
                except:
                    pass
            self._ahk_process = None
            logger.info("AutoHotkey stopped")
        
        if self._script_path and self._script_path.exists():
            try:
                self._script_path.unlink()
            except:
                pass
    
    def reload(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        """Reload the script with new rules."""
        return self.start(rules, use_prefix, prefix_char)


class TextReplacer(QObject):
    """
    System-wide text replacement powered by AutoHotkey.
    Reliable, fast, and works in all Windows applications.
    """
    
    replacements_updated = pyqtSignal(dict)
    replacement_triggered = pyqtSignal(str, str)
    status_changed = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._enabled = False
        self._locked = False  # Settings lock
        self._use_prefix = False  # Default to auto-replace mode
        self._prefix_char = ";"
        self._replacement_rules: Dict[str, str] = {}
        
        self._ahk = AHKManager()
        
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default Bambi replacement rules."""
        defaults = {
            "i": "Bambi",
            "me": "Bambi",
            "my": "Bambi's",
            "mine": "Bambi's",
            "myself": "Bambi",
            "im": "Bambi is",
            "ive": "Bambi has",
            "id": "Bambi would",
            "ill": "Bambi will",
            "we": "Bambi and friends",
            "our": "Bambi's",
            "ours": "Bambi's",
            "weve": "Bambi and friends have",
            "were": "Bambi and friends are",
            "well": "Bambi and friends will",
            "am": "is",
            "us": "Bambi",
        }
        self._replacement_rules = defaults.copy()
        logger.info(f"Loaded {len(self._replacement_rules)} default rules")
    
    # ========== Properties ==========
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def is_locked(self) -> bool:
        return self._locked
    
    @property
    def rules(self) -> dict:
        return self._replacement_rules.copy()
    
    @property
    def use_prefix(self) -> bool:
        return self._use_prefix
    
    @use_prefix.setter
    def use_prefix(self, value: bool):
        if self._locked:
            logger.warning("Cannot change mode - settings are locked")
            return
        self._use_prefix = value
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
    
    @property
    def prefix_char(self) -> str:
        return self._prefix_char
    
    @prefix_char.setter
    def prefix_char(self, value: str):
        if self._locked:
            logger.warning("Cannot change prefix - settings are locked")
            return
        self._prefix_char = value
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
    
    @property
    def ahk_available(self) -> bool:
        return self._ahk.is_available
    
    @property
    def ahk_path(self) -> Optional[str]:
        return self._ahk._ahk_exe
    
    # ========== Lock Management ==========
    
    def lock_settings(self):
        """Lock settings - prevents any changes."""
        self._locked = True
        logger.info("🔒 Text Replacer settings LOCKED")
    
    def unlock_settings(self):
        """Unlock settings."""
        self._locked = False
        logger.info("🔓 Text Replacer settings UNLOCKED")
    
    # ========== Rule Management ==========
    
    def set_rules(self, rules: Dict[str, str]):
        """Replace all rules with new ones."""
        if self._locked:
            logger.warning("Cannot modify rules - settings are locked")
            return
        
        self._replacement_rules.clear()
        for orig, repl in rules.items():
            if orig and repl:
                self._replacement_rules[orig.lower()] = repl
        self.replacements_updated.emit(self.rules)
        
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        
        logger.info(f"Rules updated: {len(self._replacement_rules)} rules")
    
    def add_rule(self, original: str, replacement: str):
        """Add a single replacement rule."""
        if self._locked:
            logger.warning("Cannot add rule - settings are locked")
            return
        
        if original and replacement:
            self._replacement_rules[original.lower()] = replacement
            self.replacements_updated.emit(self.rules)
            if self._enabled:
                self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
            logger.info(f"Added rule: '{original}' → '{replacement}'")
    
    def remove_rule(self, original: str):
        """Remove a replacement rule."""
        if self._locked:
            logger.warning("Cannot remove rule - settings are locked")
            return
        
        key = original.lower()
        if key in self._replacement_rules:
            del self._replacement_rules[key]
            self.replacements_updated.emit(self.rules)
            if self._enabled:
                self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
            logger.info(f"Removed rule: '{original}'")
    
    def clear_rules(self):
        """Clear all replacement rules."""
        if self._locked:
            logger.warning("Cannot clear rules - settings are locked")
            return
        
        self._replacement_rules.clear()
        self.replacements_updated.emit(self.rules)
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        logger.info("All rules cleared")
    
    def reset_to_default(self):
        """Reset to default Bambi rules."""
        if self._locked:
            logger.warning("Cannot reset - settings are locked")
            return
        
        self._load_default_rules()
        self.replacements_updated.emit(self.rules)
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        logger.info("Reset to default rules")
    
    # ========== Control Methods ==========
    
    def start(self) -> bool:
        """Start text replacement via AutoHotkey."""
        if self._enabled:
            return True
        
        if not self._ahk.is_available:
            logger.error("AutoHotkey not available even after download attempt")
            logger.error("Please install manually from: https://www.autohotkey.com/")
            return False
        
        success = self._ahk.start(self._replacement_rules, self._use_prefix, self._prefix_char)
        
        if success:
            self._enabled = True
            self.status_changed.emit(True)
            
            if self._use_prefix:
                logger.info(f"🔄 Text replacement STARTED - Type '{self._prefix_char}i' for Bambi")
            else:
                logger.info("🔄 Text replacement STARTED (Auto-replace mode)")
        
        return success
    
    def stop(self):
        """Stop text replacement."""
        if not self._enabled:
            return
        
        self._ahk.stop()
        self._enabled = False
        self.status_changed.emit(False)
        logger.info("Text replacement stopped")
    
    def toggle(self) -> bool:
        """Toggle text replacement on/off."""
        if self._enabled:
            self.stop()
        else:
            self.start()
        return self._enabled
    
    # ========== Status & Info ==========
    
    def get_status(self) -> dict:
        """Get current status."""
        return {
            "enabled": self._enabled,
            "locked": self._locked,
            "rule_count": len(self._replacement_rules),
            "use_prefix": self._use_prefix,
            "prefix_char": self._prefix_char,
            "ahk_available": self._ahk.is_available,
            "ahk_running": self._ahk.is_running,
            "ahk_path": self._ahk._ahk_exe,
        }
    
    def get_script_preview(self) -> str:
        """Get a preview of the current AHK script."""
        return self._ahk.generate_script(
            self._replacement_rules, 
            self._use_prefix, 
            self._prefix_char
        )
    
    def apply_settings(self, settings: dict):
        """Apply settings from storage (called after unlock)."""
        if self._locked:
            logger.warning("Cannot apply settings - locked")
            return
        
        if "rules" in settings:
            self.set_rules(settings["rules"])
        if "use_prefix" in settings:
            self._use_prefix = settings["use_prefix"]
        if "prefix_char" in settings:
            self._prefix_char = settings["prefix_char"]
        
        logger.info("Settings applied")