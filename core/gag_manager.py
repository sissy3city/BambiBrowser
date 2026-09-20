"""Bambi Gag – AutoHotkey based text gagging on Windows, evdev/uinput-based on Linux."""

import sys
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger("BambiBrowser.GagManager")


class GagManager(QObject):
    status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, base_dir: Path, settings_manager):
        super().__init__()
        self.base_dir = base_dir
        self.settings_manager = settings_manager
        self._enabled = False
        self._current_state = False
        self._linux_engine = None

        if sys.platform == "win32":
            self._state_file: Optional[Path] = None

            # Create timer BEFORE loading settings
            self._state_timer = QTimer()
            self._state_timer.timeout.connect(self._read_state_file)
            self._state_timer.setInterval(1000)

            from core.windows.ahk_manager import AHKManager
            self._ahk = AHKManager()
        else:
            from core.linux.linux_gag_engine import LinuxGagEngine
            self._linux_engine = LinuxGagEngine()
            self._linux_engine.status_changed.connect(self._on_linux_state_changed)
            self._linux_engine.error_occurred.connect(self.error_occurred.emit)

        self._load_settings()
        if self.settings_manager:
            # Only listen to gag-specific changes, not all_settings_changed
            self.settings_manager.gag_settings_changed.connect(self._on_settings_changed)

    @property
    def is_available(self) -> bool:
        if self._linux_engine is not None:
            return self._linux_engine.is_available
        return self._ahk.is_available

    @property
    def is_running(self) -> bool:
        if self._linux_engine is not None:
            return self._linux_engine.is_running
        return self._ahk.is_running

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
            self.error_occurred.emit("Bambi Gag engine not available")
            return False

        if self.settings_manager:
            settings = self.settings_manager.get_gag_settings()
        else:
            settings = self._default_settings()

        if not settings.enabled:
            return False

        if self._linux_engine is not None:
            self.stop()
            if self._linux_engine.start(settings):
                self._enabled = True
                self._current_state = self._linux_engine.current_state
                logger.info("Bambi Gag started (Linux)")
                return True
            return False

        return self._start_windows(settings)

    def _start_windows(self, settings) -> bool:
        temp_dir = Path(tempfile.gettempdir()) / "BambiBrowser"
        temp_dir.mkdir(exist_ok=True)
        self._state_file = temp_dir / "gag_state.txt"

        script_content = self._generate_script(settings)
        if not self._ahk.run_script(script_content, "bambi_gag.ahk"):
            self.error_occurred.emit("Failed to start Bambi Gag")
            return False

        self._enabled = True
        self._state_timer.start()
        logger.info("Bambi Gag started")
        return True

    def stop(self) -> None:
        if self._linux_engine is not None:
            self._linux_engine.stop()
            self._enabled = False
            return

        was_running = self._ahk.is_running
        self._ahk.stop()
        self._state_timer.stop()
        self._enabled = False
        if was_running:
            logger.info("Bambi Gag stopped")

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

    def _on_linux_state_changed(self, active: bool):
        self._current_state = active
        self.status_changed.emit(active)

    def _default_settings(self):
        class Dummy:
            enabled = False
            remote_url = ""
            local_toggle = False
        return Dummy()

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
    ; Remove UTF-8 BOM
    raw := RegExReplace(raw, "^\\xEF\\xBB\\xBF")
    ; ============================================================
    ; NOTEPAD.CC FIX: Extract text from <pre> tag
    ; ============================================================
    ; Method 1: Look for <pre>...</pre> content (notepad.cc style)
    preStart := InStr(raw, "<pre")
    if (preStart > 0) {{
        ; Find the closing > of the opening <pre> tag
        tagEnd := InStr(raw, ">", , preStart)
        if (tagEnd > 0) {{
            preEnd := InStr(raw, "</pre>", , tagEnd)
            if (preEnd > 0) {{
                ; Extract everything between > and </pre>
                content := SubStr(raw, tagEnd + 1, preEnd - tagEnd - 1)
                ; Strip any remaining HTML tags from the content
                content := RegExReplace(content, "<[^>]*>", "")
                ; Remove whitespace
                content := RegExReplace(content, "[\\r\\n\\t ]", "")
                if (content = "ON")
                    gagEnabled := true
                else if (content = "OFF")
                    gagEnabled := false
                WriteState()
                UpdateTray()
                return
            }}
        }}
    }}
    ; Method 2: Fallback – strip all HTML tags and look for ON/OFF
    raw := RegExReplace(raw, "<[^>]*>", "")
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
