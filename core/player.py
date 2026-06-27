"""Video player using mpv directly – multi‑screen, sync‑free."""

import os
import sys
import time
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QGuiApplication

from core.hard_lock import HardLock
from core.audio_muter import mute_other_applications, unmute_all_applications, is_audio_muting_available

logger = logging.getLogger("BambiBrowser.Player")

# Windows API for window properties
try:
    import win32gui
    import win32con
    import win32process
    WINDOWS_API = True
except ImportError:
    WINDOWS_API = False
    logger.warning("pywin32 not available – opacity/click‑through disabled")


def get_mpv_path() -> Optional[Path]:
    """Locate mpv executable in bundled folder or system PATH."""
    base = Path(__file__).parent.parent
    candidates = [
        base / "mpv" / "mpv.exe",
        base / "mpv" / "mpv.com",
        base / "mpv.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    which = shutil.which("mpv.exe")
    return Path(which) if which else None


class MPVProcess(QObject):
    """Manages a single mpv instance on one screen."""
    process_ended = pyqtSignal(int)   # screen_index
    error_occurred = pyqtSignal(str)

    def __init__(self, screen_index: int, settings: Dict[str, Any], mute_secondary_audio: bool = True):
        super().__init__()
        self.screen_index = screen_index
        self.settings = settings
        self.mute_secondary_audio = mute_secondary_audio  # always True for secondary screens
        self._process: Optional[subprocess.Popen] = None
        self._is_playing = False
        self._mpv_path = get_mpv_path()

        if not self._mpv_path:
            logger.error(f"mpv.exe not found for screen {screen_index}")

    def _build_command(self, url: str) -> List[str]:
        """Build the mpv command line."""
        cmd = [
            str(self._mpv_path),
            url,
            f"--screen={self.screen_index}",
            "--fullscreen",
            "--ontop",
            "--no-input-default-bindings",
            "--no-input-vo-keyboard",
            "--no-input-cursor",
            "--no-osc",
            "--really-quiet",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--referrer=https://hypnotube.com/",
            "--hwdec=auto-safe",
            "--vo=gpu-next",
            "--video-sync=display-resample",
            "--profile=fast",
            "--cache=yes",
            "--cache-secs=2.0",
        ]

        # Audio: always mute secondary screens; primary screen uses user volume
        if self.screen_index > 0 and self.mute_secondary_audio:
            cmd.append("--no-audio")
        else:
            volume = self.settings.get('volume', 100)
            percent = min(100, int(volume * 100 / 256))
            cmd.append(f"--volume={percent}")

        return cmd

    def start(self, url: str) -> bool:
        """Launch mpv."""
        if not self._mpv_path:
            self.error_occurred.emit("mpv.exe not found")
            return False

        cmd = self._build_command(url)
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            self._is_playing = True
            logger.info(f"Screen {self.screen_index}: mpv started (PID {self._process.pid})")

            # Apply opacity/click-through after window appears
            if WINDOWS_API and (self.settings.get('click_through') or self.settings.get('opacity', 100) < 100):
                QTimer.singleShot(800, self._apply_window_properties)

            # Monitor process exit
            QTimer.singleShot(500, self._check_process)
            return True
        except Exception as e:
            logger.error(f"Failed to start mpv: {e}")
            self.error_occurred.emit(str(e))
            return False

    def _check_process(self):
        """Poll the process and emit ended signal when it exits."""
        if self._process is None:
            return
        if self._process.poll() is not None:
            self._is_playing = False
            self.process_ended.emit(self.screen_index)
        else:
            QTimer.singleShot(500, self._check_process)

    def _apply_window_properties(self):
        """Apply opacity and click‑through using Win32 API."""
        if not WINDOWS_API or not self._process:
            return
        try:
            def enum_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "mpv":
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == self._process.pid:
                        windows.append(hwnd)
                return True

            windows = []
            win32gui.EnumWindows(enum_callback, windows)
            if windows:
                hwnd = windows[0]
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                opacity = self.settings.get('opacity', 100)
                if opacity < 100:
                    alpha = int(opacity * 255 / 100)
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)
                    win32gui.SetLayeredWindowAttributes(hwnd, 0, alpha, win32con.LWA_ALPHA)
                if self.settings.get('click_through'):
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                           style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED)
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            else:
                QTimer.singleShot(500, self._apply_window_properties)
        except Exception as e:
            logger.debug(f"Window properties error: {e}")

    def stop(self):
        """Terminate the mpv process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(2)
            except:
                self._process.kill()
        self._process = None
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def cleanup(self):
        self.stop()


class SeamlessPlaybackManager(QObject):
    """Manages multiple mpv instances across screens."""
    all_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, hard_lock: HardLock, settings: Dict[str, Any]):
        super().__init__()
        self.hard_lock = hard_lock
        self.settings = settings
        self._players: Dict[int, MPVProcess] = {}
        self._active_screens = 0
        self._lock_applied = False
        self._input_lock_enabled = settings.get("input_lock", True)
        self._mute_other_audio = settings.get("mute_other_audio", False)
        self._audio_muted = False

    def start_playback(self, url: str, monitors: List[int]) -> bool:
        if not monitors:
            return False

        self._players.clear()
        self._active_screens = len(monitors)

        for screen in monitors:
            # Secondary screens always have their audio muted (--no-audio)
            mute_secondary = screen > 0
            player = MPVProcess(
                screen,
                self.settings,
                mute_secondary_audio=mute_secondary
            )
            player.process_ended.connect(self._on_process_ended)
            player.error_occurred.connect(self._on_error)
            if not player.start(url):
                self.stop_all()
                return False
            self._players[screen] = player

        # Apply HardLock after a short delay
        if self._input_lock_enabled:
            QTimer.singleShot(1000, self._apply_hard_lock)

        # Mute other applications if enabled
        if self._mute_other_audio and is_audio_muting_available():
            if mute_other_applications():
                self._audio_muted = True
                logger.info("System audio muted for other applications")
            else:
                logger.warning("Failed to mute other applications")

        return True

    def _apply_hard_lock(self):
        if not self._lock_applied and self._input_lock_enabled:
            for player in self._players.values():
                if player.is_playing:
                    self.hard_lock.lock()
                    self._lock_applied = True
                    logger.info("🔒 HARDLOCK ACTIVE")
                    return
            QTimer.singleShot(500, self._apply_hard_lock)

    def _on_process_ended(self, screen_index: int):
        logger.info(f"Screen {screen_index} finished")
        self._active_screens -= 1
        if self._active_screens <= 0:
            self._release_hard_lock()
            self._restore_audio()
            self.all_finished.emit()

    def _release_hard_lock(self):
        if self._lock_applied:
            self.hard_lock.unlock()
            self._lock_applied = False

    def _restore_audio(self):
        if self._audio_muted:
            if unmute_all_applications():
                self._audio_muted = False
                logger.info("System audio restored")
            else:
                logger.warning("Failed to restore audio")

    def _on_error(self, msg: str):
        logger.error(f"MPV error: {msg}")
        self.error_occurred.emit(msg)

    def skip_all(self):
        for player in self._players.values():
            player.stop()
        self._players.clear()
        self._active_screens = 0
        self._release_hard_lock()
        self._restore_audio()

    def stop_all(self):
        self.skip_all()

    @property
    def is_playing(self) -> bool:
        return self._active_screens > 0


# ========== VideoPlayer (main interface) ==========
@dataclass
class QueuedVideo:
    url: str
    settings: Dict[str, Any]


class VideoPlayer(QObject):
    status_changed = pyqtSignal(bool)
    queue_updated = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, hard_lock: HardLock):
        super().__init__()
        self.hard_lock = hard_lock
        self._manager: Optional[SeamlessPlaybackManager] = None
        self._is_playing = False
        self._started_at: float = 0.0
        self._current_monitors: List[int] = []

        from PyQt6.QtCore import QSettings
        settings = QSettings("BambiBrowser", "Settings")

        self._input_lock = settings.value("hardlock", True, type=bool)
        self._mute_other_audio = False
        self._click_through = settings.value("click_through", False, type=bool)
        self._opacity = settings.value("opacity", 100, type=int)
        self._multi_monitor = settings.value("multi_monitor", False, type=bool)
        self._selected_monitors: List[int] = []
        self._volume = settings.value("volume", 256, type=int)

        self._max_video_length_enabled = False
        self._max_video_length_minutes = 10
        self._max_video_length_action = "Block & Show Warning"
        self._max_queue_duration_enabled = False
        self._max_queue_duration_minutes = 60
        self._max_queue_duration_action = "Reject New Videos"

        if not get_mpv_path():
            logger.error("mpv.exe not found – playback unavailable")
        else:
            logger.info("VideoPlayer initialized (mpv direct)")

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def vlc_available(self) -> bool:
        return get_mpv_path() is not None

    @property
    def queue_size(self) -> int:
        return 0   # No queue in this simplified version

    @property
    def settings(self) -> dict:
        return {
            "input_lock": self._input_lock,
            "mute_other_audio": self._mute_other_audio,
            "click_through": self._click_through,
            "opacity": self._opacity,
            "multi_monitor": self._multi_monitor,
            "selected_monitors": self._selected_monitors.copy(),
            "volume": self._volume,
            "max_video_length_enabled": self._max_video_length_enabled,
            "max_video_length_minutes": self._max_video_length_minutes,
            "max_video_length_action": self._max_video_length_action,
            "max_queue_duration_enabled": self._max_queue_duration_enabled,
            "max_queue_duration_minutes": self._max_queue_duration_minutes,
            "max_queue_duration_action": self._max_queue_duration_action,
        }

    def update_settings(self, **kwargs):
        if "input_lock" in kwargs:
            self._input_lock = bool(kwargs["input_lock"])
        if "mute_other_audio" in kwargs:
            self._mute_other_audio = bool(kwargs["mute_other_audio"])
        if "click_through" in kwargs:
            self._click_through = bool(kwargs["click_through"])
        if "opacity" in kwargs:
            self._opacity = max(10, min(100, int(kwargs["opacity"])))
        if "multi_monitor" in kwargs:
            self._multi_monitor = bool(kwargs["multi_monitor"])
        if "selected_monitors" in kwargs:
            self._selected_monitors = list(kwargs.get("selected_monitors", []))
        if "volume" in kwargs:
            self._volume = max(0, min(256, int(kwargs["volume"])))
        if "max_video_length_enabled" in kwargs:
            self._max_video_length_enabled = bool(kwargs["max_video_length_enabled"])
        if "max_video_length_minutes" in kwargs:
            self._max_video_length_minutes = max(5, int(kwargs["max_video_length_minutes"]))
        if "max_video_length_action" in kwargs:
            self._max_video_length_action = str(kwargs["max_video_length_action"])
        if "max_queue_duration_enabled" in kwargs:
            self._max_queue_duration_enabled = bool(kwargs["max_queue_duration_enabled"])
        if "max_queue_duration_minutes" in kwargs:
            self._max_queue_duration_minutes = max(30, int(kwargs["max_queue_duration_minutes"]))
        if "max_queue_duration_action" in kwargs:
            self._max_queue_duration_action = str(kwargs["max_queue_duration_action"])

    def get_available_monitors(self) -> List[int]:
        return list(range(len(QGuiApplication.screens())))

    def play(self, url: str, **kwargs) -> bool:
        logger.info(f"mpv play() called")
        self.update_settings(**kwargs)

        if not get_mpv_path():
            self.error_occurred.emit("mpv.exe not found")
            return False

        if self._multi_monitor:
            monitors = self._selected_monitors or self.get_available_monitors()
        else:
            monitors = [0]

        # Stop current playback if any
        if self._is_playing:
            self.stop()

        self._manager = SeamlessPlaybackManager(self.hard_lock, self.settings)
        self._manager.all_finished.connect(self._on_playback_finished)
        self._manager.error_occurred.connect(self._on_error)

        if self._manager.start_playback(url, monitors):
            self._is_playing = True
            self._current_monitors = monitors
            self._started_at = time.time()
            self.status_changed.emit(True)
            return True
        else:
            self._manager = None
            return False

    def _on_playback_finished(self):
        self._is_playing = False
        self._manager = None
        self._current_monitors = []
        self.status_changed.emit(False)
        logger.info("mpv playback finished")

    def _on_error(self, msg: str):
        self.error_occurred.emit(msg)

    def skip(self):
        if self._manager:
            self._manager.skip_all()

    def stop(self):
        if self._manager:
            self._manager.stop_all()
            self._manager = None
        self._is_playing = False
        self._current_monitors = []
        self.status_changed.emit(False)

    def cleanup(self):
        self.stop()

    def get_status(self) -> dict:
        return {
            "playing": self._is_playing,
            "position_sec": time.time() - self._started_at if self._is_playing else None,
            "queue_size": self.queue_size,
            "settings": self.settings,
            "vlc_available": self.vlc_available,
        }