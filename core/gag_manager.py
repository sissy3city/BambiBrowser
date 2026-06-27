"""Bambi Gag – AutoHotkey based text gagging filter with remote control."""

import os
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger("BambiBrowser.GagManager")

AHK_DOWNLOAD_URL = "https://www.autohotkey.com/download/1.1/AutoHotkey_1.1.37.02.zip"


class GagManager(QObject):
    status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, base_dir: Path, settings_manager):
        super().__init__()
        self.base_dir = base_dir
        self.settings_manager = settings_manager
        self._ahk_exe: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._script_path: Optional[Path] = None
        self._state_file: Optional[Path] = None
        self._enabled = False
        self._current_state = False

        # Create timer BEFORE loading settings
        self._state_timer = QTimer()
        self._state_timer.timeout.connect(self._read_state_file)
        self._state_timer.setInterval(1000)

        self._find_or_download_ahk()
        self._load_settings()
        if self.settings_manager:
            # Only listen to gag-specific changes, not all_settings_changed
            self.settings_manager.gag_settings_changed.connect(self._on_settings_changed)

    @property
    def is_available(self) -> bool:
        return self._ahk_exe is not None and Path(self._ahk_exe).exists()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def current_state(self) -> bool:
        return self._current_state

    def start(self) -> bool:
        if self._enabled:
            return True
        if not self.is_available:
            self.error_occurred.emit("AutoHotkey not available")
            return False
        self.stop()

        if self.settings_manager:
            settings = self.settings_manager.get_gag_settings()
        else:
            settings = self._default_settings()

        if not settings.enabled:
            return False

        script_content = self._generate_script(settings)
        temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
        temp_dir.mkdir(exist_ok=True)
        self._script_path = temp_dir / "bambi_gag.ahk"
        self._script_path.write_text(script_content, encoding="utf-8")
        self._state_file = temp_dir / "gag_state.txt"

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                [self._ahk_exe, str(self._script_path)],
                creationflags=creationflags
            )
            time.sleep(0.3)
            if self._process.poll() is not None:
                logger.error("Gag script exited immediately")
                return False
            self._enabled = True
            self._state_timer.start()
            logger.info("Bambi Gag started")
            return True
        except Exception as e:
            logger.error(f"Failed to start gag: {e}")
            self.error_occurred.emit(str(e))
            return False

    def stop(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except:
                try:
                    self._process.kill()
                except:
                    pass

            # Force kill if still running
            if self._process.poll() is None:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(self._process.pid)],
                        capture_output=True, check=False
                    )
                except:
                    pass

            time.sleep(0.1)
            self._process = None
            logger.info("Bambi Gag stopped")

        if self._script_path and self._script_path.exists():
            try:
                self._script_path.unlink()
            except:
                pass

        self._state_timer.stop()
        self._enabled = False

    def reload(self) -> bool:
        if not self._enabled:
            return False
        self.stop()
        return self.start()

    def cleanup(self):
        self.stop()

    def _load_settings(self):
        if not self.settings_manager:
            return
        settings = self.settings_manager.get_gag_settings()
        if settings.enabled:
            self.start()

    def _on_settings_changed(self, settings):
        """Called only when gag-specific settings change."""
        if settings.enabled and not self._enabled:
            self.start()
        elif not settings.enabled and self._enabled:
            self.stop()
        else:
            self.reload()

    def _default_settings(self):
        class Dummy:
            enabled = False
            remote_url = ""
            local_toggle = False
        return Dummy()

    def _find_or_download_ahk(self) -> None:
        self._ahk_exe = self._find_ahk()
        if self._ahk_exe:
            return
        logger.info("AutoHotkey not found – downloading for Gag...")
        if self._download_ahk():
            self._ahk_exe = self._find_ahk()

    def _find_ahk(self) -> Optional[str]:
        candidates = [
            r"C:\Program Files\AutoHotkey\AutoHotkeyU64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
            str(self.base_dir / "ahk" / "AutoHotkeyU64.exe"),
            str(self.base_dir / "ahk" / "AutoHotkey64.exe"),
            str(self.base_dir / "ahk" / "AutoHotkey.exe"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        import shutil
        return shutil.which("AutoHotkeyU64.exe") or shutil.which("AutoHotkey.exe")

    def _download_ahk(self) -> bool:
        ahk_dir = self.base_dir / "ahk"
        ahk_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ahk_dir / "ahk-u64.zip"
        try:
            import urllib.request, zipfile, shutil
            logger.info(f"Downloading from {AHK_DOWNLOAD_URL} ...")
            urllib.request.urlretrieve(AHK_DOWNLOAD_URL, str(zip_path))
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(ahk_dir)
            zip_path.unlink()
            for item in ahk_dir.iterdir():
                if item.is_dir() and item.name.lower() in ("autohotkey", "ahk"):
                    for sub in item.iterdir():
                        target = ahk_dir / sub.name
                        if not target.exists():
                            shutil.move(str(sub), str(target))
                    shutil.rmtree(item)
            return any(ahk_dir.glob("AutoHotkey*.exe"))
        except Exception as e:
            logger.error(f"AHK download failed: {e}")
            return False

    def _generate_script(self, settings) -> str:
        remote_url = settings.remote_url.strip() if settings.remote_url else ""
        local_toggle = settings.local_toggle if hasattr(settings, 'local_toggle') else False
        use_remote = bool(remote_url)
        local_toggle_str = "true" if local_toggle else "false"

        script = f"""; ============================================================
;  BAMBI GAG – Auto‑generated script (NO TRAY ICON)
; ============================================================
#Persistent
#SingleInstance Force
#NoTrayIcon
global gagEnabled := false
global lastState := false
global useRemote := {str(use_remote).lower()}
global remoteUrl := "{remote_url}"
global statusFile := A_Temp . "\\BambiBrowser\\gag_status.txt"
global stateFile := A_Temp . "\\BambiBrowser\\gag_state.txt"

FileCreateDir, %A_Temp%\\BambiBrowser

if (useRemote) {{
    SetTimer, CheckRemoteFlag, 5000
}} else {{
    gagEnabled := {local_toggle_str}
    lastState := gagEnabled
    WriteState()
}}

; No tray menu – we hide it completely
UpdateTray()

CheckRemoteFlag:
    UrlDownloadToFile, %remoteUrl%, %statusFile%
    FileRead, raw, %statusFile%
    raw := RegExReplace(raw, "^\\xEF\\xBB\\xBF")
    raw := RegExReplace(raw, "[\\r\\n\\t ]", "")
    if (raw = "ON")
        gagEnabled := true
    else if (raw = "OFF")
        gagEnabled := false
    WriteState()
    UpdateTray()
return

WriteState() {{
    global stateFile
    FileDelete, %stateFile%
    if (gagEnabled)
        FileAppend, ON, %stateFile%
    else
        FileAppend, OFF, %stateFile%
}}

UpdateTray() {{
    global gagEnabled, lastState
    ; Only play sound if state changed – no tray icon ever shown
    if (gagEnabled != lastState) {{
        if (gagEnabled)
            SoundPlay, *64
        else
            SoundPlay, *16
        lastState := gagEnabled
    }}
}}

ExitScript:
    ExitApp

#IfWinActive ahk_exe Discord.exe
Enter::
    if (!gagEnabled) {{
        SendInput {{Enter}}
        return
    }}
    WinActivate, ahk_exe Discord.exe
    Sleep 80
    SendInput ^a
    Sleep 60
    SendInput ^c
    Sleep 120
    ClipWait, 0.5
    if (ErrorLevel) {{
        SendInput {{Enter}}
        return
    }}
    text := Clipboard
    gagged := GagTransform(text)
    SendInput ^a
    Sleep 60
    SendInput {{Text}}%gagged%
    Sleep 120
    SendInput {{Enter}}
return
#IfWinActive

GagTransform(str) {{
    out := ""
    Loop, Parse, str
    {{
        c := A_LoopField
        if (c ~= "[a-zA-Z]") {{
            Random, idx, 1, 6
            if (idx = 1)
                syll := "mph"
            else if (idx = 2)
                syll := "mmph"
            else if (idx = 3)
                syll := "mh"
            else if (idx = 4)
                syll := "ph"
            else if (idx = 5)
                syll := "mmf"
            else
                syll := "hmmph"
            out .= syll
        }} else {{
            out .= c
        }}
    }}
    return out
}}
"""
        return script

    def _read_state_file(self):
        if not self._state_file or not self._state_file.exists():
            return
        try:
            state = self._state_file.read_text(encoding="utf-8").strip()
            new_state = state.upper() == "ON"
            if new_state != self._current_state:
                self._current_state = new_state
                self.status_changed.emit(new_state)
        except Exception as e:
            logger.debug(f"Failed to read gag state: {e}")