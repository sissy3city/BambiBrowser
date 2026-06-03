"""Video player using MPV (mpv.exe subprocess) – fast, reliable, no VLC."""

import os
import sys
import time
import logging
import subprocess
import ctypes
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from core.hard_lock import HardLock

logger = logging.getLogger("BambiBrowser.Player")

# Windows API for window manipulation
user32 = ctypes.windll.user32


def get_screen_geometry(screen_index: int) -> tuple:
    """Return (x, y, width, height) of the given screen."""
    screens = QGuiApplication.screens()
    if screen_index < len(screens):
        geom = screens[screen_index].geometry()
        return (geom.x(), geom.y(), geom.width(), geom.height())
    return (0, 0, 1920, 1080)


def get_mpv_path() -> Optional[Path]:
    """Find mpv.exe – first in bundled 'mpv' folder, then in PATH."""
    base = Path(__file__).parent.parent
    candidates = [
        base / "mpv" / "mpv.exe",
        base / "mpv" / "mpv.com",
        base / "mpv.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    # Check PATH
    which = shutil.which("mpv.exe")
    if which:
        return Path(which)
    return None


class MPVProcess(QObject):
    """
    Manages a single mpv.exe process for one monitor.
    Process is kept alive – after a video ends, it waits for the next.
    """

    process_ended = pyqtSignal(int)          # screen_index
    duration_ready = pyqtSignal(float)       # seconds
    error_occurred = pyqtSignal(str)

    def __init__(self, screen_index: int, settings: Dict[str, Any]):
        super().__init__()
        self.screen_index = screen_index
        self.settings = settings
        self._process: Optional[subprocess.Popen] = None
        self._current_url: Optional[str] = None
        self._queue: List[str] = []
        self._is_playing = False
        self._no_audio = (screen_index > 0)
        self._monitor_timer: Optional[QTimer] = None
        self._mutex = QMutex()
        self._mpv_path = get_mpv_path()

        if not self._mpv_path:
            logger.error(f"mpv.exe not found – cannot create player for screen {screen_index}")

    def _build_command(self, url: str) -> List[str]:
        cmd = [str(self._mpv_path), url]

        # Display and window
        cmd.append(f"--screen={self.screen_index}")
        cmd.append("--fullscreen")
        cmd.append("--ontop")
        cmd.append("--keep-open=no")              # exit when video ends
        cmd.append("--no-input-default-bindings")
        cmd.append("--no-input-vo-keyboard")
        cmd.append("--no-input-cursor")
        cmd.append("--no-osc")                    # no on-screen controls
        cmd.append("--really-quiet")
        cmd.append("--no-terminal")

        # Network
        cmd.append("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        cmd.append("--referrer=https://hypnotube.com/")

        # Audio
        if self._no_audio:
            cmd.append("--no-audio")
        else:
            volume = self.settings.get('volume', 100)
            percent = min(100, int(volume * 100 / 256))
            cmd.append(f"--volume={percent}")

        # ========== PERFORMANCE FIXES (add these) ==========
        cmd.append("--hwdec=auto-safe")               # hardware decoding
        cmd.append("--vo=gpu-next")                   # modern GPU renderer
        cmd.append("--video-sync=display-resample")   # smooth sync
        cmd.append("--profile=fast")                  # low-overhead (good for netbooks)
        # Optional: increase cache for network streams
        cmd.append("--cache=yes")
        cmd.append("--cache-secs=5.0")
        cmd.append("--demuxer-max-bytes=100M")
        # =================================================

        return cmd

    def _start_process(self, url: str) -> bool:
        """Launch mpv.exe with the given URL."""
        if not self._mpv_path:
            self.error_occurred.emit("mpv.exe not found")
            return False

        cmd = self._build_command(url)
        try:
            # CREATE_NO_WINDOW avoids a console window
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self._current_url = url
            self._is_playing = True

            # Start monitoring the process
            self._monitor_timer = QTimer()
            self._monitor_timer.timeout.connect(self._check_process)
            self._monitor_timer.start(500)

            # Apply click-through and opacity after a short delay (window must exist)
            if self.settings.get('click_through') or self.settings.get('opacity', 100) < 100:
                QTimer.singleShot(800, self._apply_window_properties)

            logger.info(f"Screen {self.screen_index}: started mpv.exe (PID {self._process.pid}) for {url[:80]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to start mpv: {e}")
            self.error_occurred.emit(str(e))
            return False

    def _check_process(self):
        """Called periodically to see if the process has ended."""
        if self._process and self._process.poll() is not None:
            # Process ended
            self._monitor_timer.stop()
            self._monitor_timer = None
            self._is_playing = False
            logger.info(f"Screen {self.screen_index}: mpv process ended (code {self._process.returncode})")
            self._on_process_ended()

    def _on_process_ended(self):
        """Play next video from queue or notify that playback finished."""
        with QMutexLocker(self._mutex):
            # Remove current video from queue
            if self._queue and self._queue[0] == self._current_url:
                self._queue.pop(0)

            if self._queue:
                next_url = self._queue[0]
                logger.info(f"Screen {self.screen_index}: playing next from queue")
                if self._start_process(next_url):
                    return
                else:
                    # Failed to start next – clear queue and signal end
                    self._queue.clear()
                    self.process_ended.emit(self.screen_index)
            else:
                logger.info(f"Screen {self.screen_index}: queue empty, playback finished")
                self.process_ended.emit(self.screen_index)

    def _apply_window_properties(self):
        """Apply opacity and click-through using Windows API."""
        if not self._process:
            return
        try:
            import win32gui
            import win32con

            # Find mpv's window – it's usually the topmost window with class "mpv"
            def enum_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    class_name = win32gui.GetClassName(hwnd)
                    if class_name == "mpv":
                        windows.append(hwnd)
                return True

            windows = []
            win32gui.EnumWindows(enum_callback, windows)
            hwnd = windows[-1] if windows else None

            if hwnd:
                current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                opacity = self.settings.get('opacity', 100)
                if opacity < 100:
                    alpha = int(opacity * 255 / 100)
                    new_style = current_style | win32con.WS_EX_LAYERED
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
                    win32gui.SetLayeredWindowAttributes(hwnd, 0, alpha, win32con.LWA_ALPHA)

                if self.settings.get('click_through'):
                    new_style = current_style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)

                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                logger.info(f"Screen {self.screen_index}: opacity {opacity}%, click-through={self.settings.get('click_through')}")
            else:
                # Try again later if window not found yet
                QTimer.singleShot(500, self._apply_window_properties)
        except Exception as e:
            logger.debug(f"Could not apply window properties: {e}")

    # ---------- Public API ----------
    def start(self, url: str) -> bool:
        """Start playback with an initial URL (clears previous queue)."""
        with QMutexLocker(self._mutex):
            self._queue.clear()
            self._queue.append(url)
            return self._start_process(url)

    def add_to_queue(self, url: str):
        """Add URL to queue; start playing if not already."""
        with QMutexLocker(self._mutex):
            self._queue.append(url)
            if not self._is_playing and self._queue:
                self._start_process(self._queue[0])

    def skip(self):
        """Skip current video (kill process, next will start automatically)."""
        with QMutexLocker(self._mutex):
            if self._process and self._process.poll() is None:
                logger.info(f"Screen {self.screen_index}: skipping current")
                self._process.terminate()
                # Wait a bit – _on_process_ended will handle playing next
                QTimer.singleShot(300, lambda: None)
            else:
                self._queue.clear()

    def stop(self):
        """Stop playback and clear queue."""
        with QMutexLocker(self._mutex):
            self._queue.clear()
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(2)
                except:
                    self._process.kill()
            self._process = None
            self._is_playing = False
            self._current_url = None
            if self._monitor_timer:
                self._monitor_timer.stop()
                self._monitor_timer = None

    def clear_queue(self):
        """Clear pending queue (does not stop current video)."""
        with QMutexLocker(self._mutex):
            self._queue.clear()

    @property
    def is_playing(self) -> bool:
        if self._process:
            return self._process.poll() is None
        return False

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def current_url(self) -> Optional[str]:
        return self._current_url

    def get_duration(self) -> Optional[float]:
        """
        Get duration of currently playing video.
        Since we don't have direct API, we use ffprobe or estimate.
        """
        if not self._current_url:
            return None
        # Delegate to duration_helper (keeps existing logic)
        from core.duration_helper import get_video_duration
        return get_video_duration(self._current_url)

    def cleanup(self):
        self.stop()


class SeamlessPlaybackManager(QObject):
    """
    Manages MPV processes across monitors.
    Processes are created lazily – only when a monitor is first used.
    """

    all_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    queue_updated = pyqtSignal(int, int)
    next_video_started = pyqtSignal(int, str)

    def __init__(self, hard_lock: HardLock, settings: Dict[str, Any]):
        super().__init__()
        self.hard_lock = hard_lock
        self.settings = settings
        self._players: Dict[int, MPVProcess] = {}
        self._active_screens = 0
        self._lock_applied = False
        self._input_lock_enabled = settings.get("input_lock", True)

    def _get_player(self, screen: int) -> MPVProcess:
        """Lazy creation: create only when this screen is first used."""
        if screen not in self._players:
            player = MPVProcess(screen, self.settings)
            player.process_ended.connect(self._on_process_ended)
            player.error_occurred.connect(self._on_error)
            self._players[screen] = player
            logger.info(f"Screen {screen}: MPV process manager created")
        return self._players[screen]

    def start_playback(self, url: str, monitors: List[int]) -> bool:
        """Start playback on all given monitors."""
        logger.info(f"Starting MPV on {len(monitors)} monitor(s)")
        for screen in monitors:
            player = self._get_player(screen)
            if not player.start(url):
                return False
            self._active_screens += 1

        if self._input_lock_enabled:
            self._video_check_timer = QTimer()
            self._video_check_timer.timeout.connect(self._check_video_and_lock)
            self._video_check_timer.start(200)
            self._video_check_attempts = 0
        return True

    def _check_video_and_lock(self):
        self._video_check_attempts += 1
        for player in self._players.values():
            if player.is_playing:
                if hasattr(self, '_video_check_timer'):
                    self._video_check_timer.stop()
                    self._video_check_timer.deleteLater()
                self._apply_hard_lock()
                return
        if self._video_check_attempts > 20:   # 4 seconds
            if hasattr(self, '_video_check_timer'):
                self._video_check_timer.stop()
                self._video_check_timer.deleteLater()
            self._apply_hard_lock()

    def _apply_hard_lock(self):
        if not self._lock_applied and self._input_lock_enabled:
            self.hard_lock.lock()
            self._lock_applied = True
            logger.info("🔒 HARDLOCK ACTIVE")

    def add_to_queue(self, url: str, monitors: List[int]):
        for screen in monitors:
            player = self._get_player(screen)
            player.add_to_queue(url)
            self.queue_updated.emit(screen, player.queue_size)

    def _on_process_ended(self, screen_index: int):
        logger.info(f"Screen {screen_index} finished")
        self._active_screens -= 1
        if self._active_screens <= 0:
            self._release_hard_lock()
            self.all_finished.emit()

    def _release_hard_lock(self):
        if self._lock_applied:
            self.hard_lock.unlock()
            self._lock_applied = False

    def _on_error(self, msg: str):
        logger.error(f"MPV error: {msg}")
        self.error_occurred.emit(msg)

    def skip_all(self):
        for player in self._players.values():
            player.skip()

    def stop_all(self):
        for player in self._players.values():
            player.stop()
        self._players.clear()
        self._active_screens = 0
        self._release_hard_lock()

    def clear_queue(self):
        for player in self._players.values():
            player.clear_queue()

    @property
    def is_playing(self) -> bool:
        return self._active_screens > 0

    @property
    def total_queue_size(self) -> int:
        return sum(p.queue_size for p in self._players.values())


@dataclass
class QueuedVideo:
    url: str
    settings: Dict[str, Any]


class VideoPlayer(QObject):
    """Main video player – drop‑in replacement, all original features work."""

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

        # Safety limits (same as original)
        self._max_video_length_enabled = False
        self._max_video_length_minutes = 10
        self._max_video_length_action = "Block & Show Warning"
        self._max_queue_duration_enabled = False
        self._max_queue_duration_minutes = 60
        self._max_queue_duration_action = "Reject New Videos"

        if not get_mpv_path():
            logger.error("mpv.exe not found – playback unavailable")
        else:
            logger.info(f"VideoPlayer initialized with MPV (mpv.exe) backend, volume={self._volume}")

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def vlc_available(self) -> bool:
        """Legacy property – true if mpv.exe is available."""
        return get_mpv_path() is not None

    @property
    def queue_size(self) -> int:
        if self._manager:
            return self._manager.total_queue_size
        return 0

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
        # Safety limits
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
        """Start playing or add to queue."""
        logger.info(f"MPV play() called")
        self.update_settings(**kwargs)

        if not get_mpv_path():
            self.error_occurred.emit("mpv.exe not found")
            return False

        if self._multi_monitor:
            monitors = self._selected_monitors or self.get_available_monitors()
        else:
            monitors = [0]

        if not self._is_playing:
            self._manager = SeamlessPlaybackManager(self.hard_lock, self.settings)
            self._manager.all_finished.connect(self._on_playback_finished)
            self._manager.error_occurred.connect(self._on_error)
            self._manager.queue_updated.connect(self._on_queue_updated)
            self._manager.next_video_started.connect(self._on_next_video_started)

            if self._manager.start_playback(url, monitors):
                self._is_playing = True
                self._current_monitors = monitors
                self._started_at = time.time()
                self.status_changed.emit(True)
                return True
            else:
                self._manager = None
                return False
        else:
            # Already playing – add to queue on the current monitors
            queue_monitors = self._current_monitors if self._current_monitors else [0]
            self._manager.add_to_queue(url, queue_monitors)
            self.queue_updated.emit(self.queue_size)
            return True

    def _on_queue_updated(self, screen_index: int, queue_size: int):
        self.queue_updated.emit(self.queue_size)

    def _on_next_video_started(self, screen_index: int, url: str):
        self._started_at = time.time()
        logger.info("Next video started, resetting timer")

    def _on_playback_finished(self):
        self._is_playing = False
        self._manager = None
        self._current_monitors = []
        self.status_changed.emit(False)
        logger.info("MPV playback finished")

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