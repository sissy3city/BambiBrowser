"""AutoHotkey script generator for system-wide text replacement."""

import os
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("BambiBrowser.AHKGenerator")


class AHKGenerator:
    """Generates and manages AutoHotkey scripts for text replacement."""
    
    def __init__(self):
        self._ahk_process: Optional[subprocess.Popen] = None
        self._script_path: Optional[Path] = None
        self._ahk_exe = self._find_autohotkey()
    
    def _find_autohotkey(self) -> Optional[str]:
        """Find AutoHotkey executable."""
        # Common installation paths
        candidates = [
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files\AutoHotkey\v2\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
            # Portable - look in same directory as app
            str(Path(__file__).parent.parent / "ahk" / "AutoHotkey.exe"),
        ]
        
        for path in candidates:
            if Path(path).exists():
                logger.info(f"Found AutoHotkey at: {path}")
                return path
        
        # Check PATH
        import shutil
        ahk_in_path = shutil.which("AutoHotkey.exe")
        if ahk_in_path:
            logger.info(f"Found AutoHotkey in PATH: {ahk_in_path}")
            return ahk_in_path
        
        logger.warning("AutoHotkey not found. Download from: https://www.autohotkey.com/")
        return None
    
    @property
    def is_available(self) -> bool:
        return self._ahk_exe is not None
    
    @property
    def is_running(self) -> bool:
        return self._ahk_process is not None and self._ahk_process.poll() is None
    
    def generate_script(self, rules: Dict[str, str], 
                        use_prefix: bool = False,
                        prefix_char: str = ";") -> str:
        """
        Generate an AutoHotkey script for the given replacement rules.
        
        Args:
            rules: Dictionary of {original: replacement}
            use_prefix: If True, require prefix (e.g., ;i -> Bambi)
            prefix_char: The prefix character to use
        
        Returns:
            The full AHK script as a string
        """
        script_lines = [
            "; BambiBrowser Auto-Generated Text Replacement Script",
            "; DO NOT EDIT MANUALLY - Managed by BambiBrowser",
            "",
            "#NoEnv",
            "#SingleInstance Force",
            "SendMode Input",
            "SetWorkingDir %A_ScriptDir%",
            "",
        ]
        
        if use_prefix:
            # Prefix mode: ;i -> Bambi (most reliable)
            script_lines.append(f"; Prefix mode - type '{prefix_char}' before trigger words")
            script_lines.append("")
            
            for original, replacement in rules.items():
                # Escape any special characters
                escaped_replacement = replacement.replace("`", "``").replace("%", "`%")
                script_lines.append(f":*:{prefix_char}{original}::{escaped_replacement}")
        else:
            # Auto-replace mode: i -> Bambi (use with caution)
            script_lines.append("; Auto-replace mode - triggers on space/enter after word")
            script_lines.append("")
            
            for original, replacement in rules.items():
                escaped_replacement = replacement.replace("`", "``").replace("%", "`%")
                # :*: makes it trigger immediately without needing an ending character
                script_lines.append(f":::{original}::{escaped_replacement}")
        
        script_lines.append("")
        script_lines.append("; Script managed by BambiBrowser")
        
        return "\n".join(script_lines)
    
    def start(self, rules: Dict[str, str], use_prefix: bool = True) -> bool:
        """
        Start AutoHotkey with the generated script.
        
        Returns:
            True if started successfully, False otherwise
        """
        if not self._ahk_exe:
            logger.error("AutoHotkey not found")
            return False
        
        # Stop any existing instance
        self.stop()
        
        try:
            # Generate script
            script_content = self.generate_script(rules, use_prefix)
            
            # Save to temp file
            temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
            temp_dir.mkdir(exist_ok=True)
            
            self._script_path = temp_dir / "bambi_replacements.ahk"
            self._script_path.write_text(script_content, encoding="utf-8")
            
            logger.info(f"Script saved to: {self._script_path}")
            
            # Launch AutoHotkey
            self._ahk_process = subprocess.Popen(
                [self._ahk_exe, str(self._script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            
            logger.info("AutoHotkey started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start AutoHotkey: {e}")
            return False
    
    def stop(self):
        """Stop the AutoHotkey process."""
        if self._ahk_process:
            try:
                self._ahk_process.terminate()
                self._ahk_process.wait(timeout=3)
            except:
                try:
                    self._ahk_process.kill()
                except:
                    pass
            self._ahk_process = None
            logger.info("AutoHotkey stopped")
        
        # Clean up script file
        if self._script_path and self._script_path.exists():
            try:
                self._script_path.unlink()
            except:
                pass
    
    def reload(self, rules: Dict[str, str], use_prefix: bool = True) -> bool:
        """Reload the script with new rules."""
        return self.start(rules, use_prefix)
    
    def get_status(self) -> dict:
        return {
            "available": self.is_available,
            "running": self.is_running,
            "ahk_path": self._ahk_exe,
        }