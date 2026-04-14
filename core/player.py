"""Video player using VLC with dynamic input handling."""

import os
import sys
import subprocess
import time
import logging
import tempfile
import ctypes
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker, QThread
from PyQt6.QtGui import QGuiApplication

from core.hard_lock import HardLock

logger = logging.getLogger("BambiBrowser.Player")


# Windows API for audio session control
try:
    from ctypes import wintypes
    from ctypes import POINTER, byref
    
    AUDCLNT_SESSIONFLAGS_DISPLAY_HIDE = 0x00000001
    AUDCLNT_SESSIONFLAGS_EXPIRE_WHEN_UNOWNED = 0x00000010
    
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8)
        ]
    
    audio_api_available = True
except:
    audio_api_available = False
    logger.warning("Audio session API not available")


def find_vlc() -> Optional[str]:
    """Find VLC executable using caching."""
    if hasattr(find_vlc, '_cached_path'):
        return find_vlc._cached_path
    
    base_dir = Path(__file__).parent.parent
    
    # Check bundled VLC first
    vlc_path = base_dir / "vlc" / "vlc.exe"
    if vlc_path.exists():
        find_vlc._cached_path = str(vlc_path)
        return find_vlc._cached_path
    
    # Check common installation paths
    candidates = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    
    for path in candidates:
        if Path(path).exists():
            find_vlc._cached_path = path
            return path
    
    find_vlc._cached_path = None
    return None


def get_vlc_plugin_path(vlc_path: str) -> Optional[str]:
    """Get the plugins path for VLC."""
    vlc_dir = Path(vlc_path).parent
    
    # Try different possible plugin locations
    candidates = [
        vlc_dir / "plugins",
        vlc_dir / "vlc" / "plugins",  # For some portable versions
        vlc_dir.parent / "plugins",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    
    return None


class AudioManager:
    """Manages audio muting for other applications."""
    
    def __init__(self):
        self.muted = False
    
    def mute_other_apps(self):
        """Mute all audio sessions except VLC."""
        if self.muted or not audio_api_available:
            return
        
        try:
            import pythoncom
            from win32com.client import Dispatch
            
            pythoncom.CoInitialize()
            
            try:
                mmdevice = Dispatch("MMDeviceEnumerator.MMDeviceEnumerator")
                devices = mmdevice.EnumerateAudioEndPoints(0, 1)
                logger.info("Audio muting requested")
            finally:
                pythoncom.CoUninitialize()
            
            self.muted = True
            logger.info("Other applications muted")
            
        except Exception as e:
            logger.error(f"Failed to mute other apps: {e}")
    
    def unmute_other_apps(self):
        """Restore audio for other applications."""
        if not self.muted:
            return
        
        try:
            self.muted = False
            logger.info("Audio restored for other applications")
        except Exception as e:
            logger.error(f"Failed to unmute apps: {e}")


class VLCProcessMonitor(QThread):
    """Worker thread for monitoring VLC process."""
    
    process_ended = pyqtSignal(int)
    
    def __init__(self, screen_index: int, process: subprocess.Popen):
        super().__init__()
        self.screen_index = screen_index
        self.process = process
        self._running = True
    
    def run(self):
        """Monitor process efficiently."""
        if not self.process:
            return
        
        while self._running:
            try:
                poll_result = self.process.poll()
                
                if poll_result is not None:
                    logger.info(f"VLC process on screen {self.screen_index} ended with code {poll_result}")
                    break
                
                self.msleep(2000)
                
            except Exception as e:
                logger.error(f"Error monitoring VLC process: {e}")
                break
        
        self.process_ended.emit(self.screen_index)
    
    def stop(self):
        """Stop monitoring."""
        self._running = False


class VLCController(QObject):
    """Controls VLC instances with playlist support."""
    
    process_ended = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    queue_empty = pyqtSignal(int)
    
    def __init__(self, screen_index: int, settings: Dict[str, Any] = None):
        super().__init__()
        self.screen_index = screen_index
        self.settings = settings or {}
        self.volume = self.settings.get("volume", 256)
        self.no_audio = (screen_index > 0)
        self._process: Optional[subprocess.Popen] = None
        self._playlist_file: Optional[Path] = None
        self._queue: List[str] = []
        self._is_playing = False
        self._mutex = QMutex()
        self._monitor_thread: Optional[VLCProcessMonitor] = None
        
    def start(self, initial_url: str = None):
        """Start VLC with optional initial URL."""
        vlc_path = find_vlc()
        if not vlc_path:
            self.error_occurred.emit("VLC not found")
            return False
        
        with QMutexLocker(self._mutex):
            vlc_dir = Path(vlc_path).parent
            
            if initial_url:
                self._queue.append(initial_url)
            
            # Get plugin path for portable VLC
            plugin_path = get_vlc_plugin_path(vlc_path)
            
            # Build VLC command - using simpler arguments for portable VLC
            args = [
                vlc_path,
                "--play-and-exit",
                "--fullscreen",
                "--video-on-top",
                "--no-video-title-show",
                "--no-keyboard-events",
                "--no-mouse-events",
                "--key-toggle-fullscreen", "0",
                "--key-leave-fullscreen", "0",
                "--key-quit", "0",
                "--key-play-pause", "0",
                "--key-stop", "0",
                "--global-key-quit", "0",
                "--qt-fullscreen-screennumber", str(self.screen_index),
                f"--volume={self.volume}",
                "--no-qt-privacy-ask",
                "--no-qt-error-dialogs",
                "--ignore-config",  # Ignore any existing config
            ]
            
            # Add plugin path if found (critical for portable VLC)
            if plugin_path:
                args.extend(["--plugin-path", plugin_path])
                logger.info(f"Using plugin path: {plugin_path}")
            
            if self.no_audio:
                args.append("--no-audio")
            
            # Add the URL
            if self._queue:
                url = self._queue[0]
                args.append(url)
                logger.info(f"Playing URL: {url[:80]}...")
            
            logger.info(f"Starting VLC on screen {self.screen_index}")
            logger.info(f"VLC command: {' '.join(args[:10])}...")
            
            # Set up environment for portable VLC
            env = os.environ.copy()
            if plugin_path:
                env["VLC_PLUGIN_PATH"] = plugin_path
            env["PATH"] = str(vlc_dir) + ";" + env.get("PATH", "")
            
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                
                # Use PIPE to capture output for debugging
                self._process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                    env=env,
                    cwd=str(vlc_dir),
                )
                
                # Wait a bit and check if process is still running
                time.sleep(1.0)
                
                if self._process.poll() is not None:
                    # Process exited, capture error output
                    stdout, stderr = self._process.communicate(timeout=2)
                    error_msg = stderr.decode('utf-8', errors='ignore')
                    logger.error(f"VLC exited quickly with code {self._process.returncode}")
                    logger.error(f"VLC stderr: {error_msg[:500]}")
                    
                    # Try alternative method with playlist
                    return self._start_with_playlist(vlc_path, vlc_dir, plugin_path)
                
                self._is_playing = True
                
                # Apply window properties if needed
                if self.settings.get("click_through", False) or self.settings.get("opacity", 100) < 100:
                    QTimer.singleShot(1000, self._apply_window_properties)
                
                self._monitor_thread = VLCProcessMonitor(self.screen_index, self._process)
                self._monitor_thread.process_ended.connect(self._on_process_ended)
                self._monitor_thread.start()
                
                logger.info(f"VLC launched successfully on screen {self.screen_index}")
                return True
                
            except Exception as e:
                logger.error(f"Exception starting VLC: {e}")
                self.error_occurred.emit(str(e))
                return False
    
    def _apply_window_properties(self):
        """Apply window transparency and click-through."""
        try:
            import win32gui
            import win32con
            
            def find_vlc_window():
                def callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        window_text = win32gui.GetWindowText(hwnd)
                        if "VLC" in window_text:
                            windows.append(hwnd)
                            return False
                    return True
                
                windows = []
                win32gui.EnumWindows(callback, windows)
                return windows[0] if windows else None
            
            hwnd = find_vlc_window()
            
            if hwnd:
                current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                
                opacity = self.settings.get("opacity", 100)
                if opacity < 100:
                    alpha = int(opacity * 255 / 100)
                    new_style = current_style | win32con.WS_EX_LAYERED
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
                    win32gui.SetLayeredWindowAttributes(hwnd, 0, alpha, win32con.LWA_ALPHA)
                
                if self.settings.get("click_through", False):
                    new_style = current_style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
                
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                
                logger.info(f"Window properties applied - opacity: {opacity}%")
                
        except Exception as e:
            logger.error(f"Failed to apply window properties: {e}")
    
    def _start_with_playlist(self, vlc_path: str, vlc_dir: Path, plugin_path: Optional[str]) -> bool:
        """Fallback: use a playlist file with minimal arguments."""
        try:
            self._playlist_file = Path(tempfile.gettempdir()) / f"bambi_playlist_{self.screen_index}.m3u"
            with open(self._playlist_file, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for url in self._queue:
                    f.write(f"{url}\n")
            
            # Minimal arguments for maximum compatibility
            args = [
                vlc_path,
                str(self._playlist_file),
                "--play-and-exit",
                "--fullscreen",
                "--video-on-top",
                "--no-video-title-show",
                f"--volume={self.volume}",
                "--ignore-config",
            ]
            
            if plugin_path:
                args.extend(["--plugin-path", plugin_path])
            
            if self.no_audio:
                args.append("--no-audio")
            
            logger.info(f"Trying playlist method with args: {args[:8]}...")
            
            env = os.environ.copy()
            if plugin_path:
                env["VLC_PLUGIN_PATH"] = plugin_path
            env["PATH"] = str(vlc_dir) + ";" + env.get("PATH", "")
            
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                env=env,
                cwd=str(vlc_dir),
            )
            
            time.sleep(1.0)
            
            if self._process.poll() is not None:
                stdout, stderr = self._process.communicate(timeout=2)
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"Playlist method failed: {error_msg[:500]}")
                self.error_occurred.emit(f"VLC failed to start. Check that VLC portable has plugins folder.")
                return False
            
            self._is_playing = True
            self._monitor_thread = VLCProcessMonitor(self.screen_index, self._process)
            self._monitor_thread.process_ended.connect(self._on_process_ended)
            self._monitor_thread.start()
            
            logger.info(f"VLC launched with playlist on screen {self.screen_index}")
            return True
            
        except Exception as e:
            logger.error(f"Exception in playlist start: {e}")
            return False
    
    def _on_process_ended(self, screen_index: int):
        """Handle process ended."""
        logger.info(f"VLC process ended for screen {screen_index}")
        
        with QMutexLocker(self._mutex):
            self._is_playing = False
            
            if self._playlist_file and self._playlist_file.exists():
                try:
                    self._playlist_file.unlink()
                except:
                    pass
        
        self.process_ended.emit(screen_index)
        
        if len(self._queue) == 0:
            self.queue_empty.emit(screen_index)
    
    def add_to_queue(self, url: str):
        """Add URL to queue."""
        with QMutexLocker(self._mutex):
            self._queue.append(url)
            
            if not self._is_playing:
                self.start()
            
            logger.info(f"Screen {self.screen_index}: Added to queue ({len(self._queue)} total)")
    
    def skip(self):
        """Skip current video."""
        with QMutexLocker(self._mutex):
            if self._queue:
                self._queue.pop(0)
                
                if self._queue:
                    if self._process and self._process.poll() is None:
                        self._process.kill()
                        time.sleep(0.2)
                    self.start()
                    logger.info(f"Screen {self.screen_index}: Skipped, {len(self._queue)} remaining")
                else:
                    logger.info(f"Screen {self.screen_index}: Queue empty after skip")
                    self.queue_empty.emit(self.screen_index)
    
    def clear_queue(self):
        """Clear queue."""
        with QMutexLocker(self._mutex):
            self._queue.clear()
    
    def stop(self):
        """Stop VLC process."""
        with QMutexLocker(self._mutex):
            if self._monitor_thread and self._monitor_thread.isRunning():
                self._monitor_thread.stop()
                self._monitor_thread.wait(500)
                
            if self._process and self._process.poll() is None:
                self._process.terminate()
                time.sleep(0.3)
                if self._process.poll() is None:
                    self._process.kill()
            self._is_playing = False
            self._queue.clear()
    
    @property
    def is_playing(self) -> bool:
        return self._is_playing
    
    @property
    def queue_size(self) -> int:
        return len(self._queue)


class SeamlessPlaybackManager(QObject):
    """Manages VLC instances with seamless queue across monitors."""
    
    all_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    queue_updated = pyqtSignal(int, int)
    
    def __init__(self, hard_lock: HardLock, settings: Dict[str, Any] = None):
        super().__init__()
        self.hard_lock = hard_lock
        self.settings = settings or {}
        self._controllers: Dict[int, VLCController] = {}
        self._active_screens = 0
        self._lock_applied = False
        self._audio_manager = AudioManager()
        self._input_lock_enabled = self.settings.get("input_lock", True)
    
    def start_playback(self, url: str, monitors: List[int]) -> bool:
        """Start playback on multiple monitors."""
        logger.info(f"Starting seamless playback on {len(monitors)} monitor(s)")
        
        if self.settings.get("mute_other_audio", False):
            self._audio_manager.mute_other_apps()
        
        for idx in monitors:
            controller = VLCController(idx, self.settings)
            controller.process_ended.connect(self._on_process_ended)
            controller.error_occurred.connect(self._on_error)
            controller.queue_empty.connect(self._on_queue_empty)
            
            self._controllers[idx] = controller
            success = controller.start(url)
            
            if not success:
                logger.error(f"Failed to start VLC on screen {idx}")
                return False
            
            self._active_screens += 1
        
        # Apply HardLock after video starts playing
        if self._input_lock_enabled:
            self._video_check_timer = QTimer()
            self._video_check_timer.timeout.connect(self._check_video_and_lock)
            self._video_check_timer.start(500)
            self._video_check_attempts = 0
            logger.info("🔒 HardLock will activate once video playback is confirmed")
        else:
            logger.info("HardLock disabled by user setting")
        
        return True
    
    def _check_video_and_lock(self):
        """Check if video is playing, then apply HardLock."""
        self._video_check_attempts += 1
        
        for controller in self._controllers.values():
            if controller.is_playing and controller._process:
                if controller._process.poll() is None:
                    if hasattr(self, '_video_check_timer'):
                        self._video_check_timer.stop()
                        self._video_check_timer.deleteLater()
                    
                    self._apply_hard_lock()
                    return
        
        # Timeout after 15 attempts (7.5 seconds)
        if self._video_check_attempts > 15:
            if hasattr(self, '_video_check_timer'):
                self._video_check_timer.stop()
                self._video_check_timer.deleteLater()
            logger.warning("Video start timeout - applying HardLock anyway")
            self._apply_hard_lock()
    
    def _apply_hard_lock(self):
        """Apply hard lock - NO ESCAPE."""
        if not self._lock_applied and self._input_lock_enabled:
            self.hard_lock.lock()
            self._lock_applied = True
            logger.info("🔒🔒🔒 HARDLOCK ACTIVE - NO ESCAPE - SYSTEM INPUT COMPLETELY BLOCKED 🔒🔒🔒")
    
    def add_to_queue(self, url: str, monitors: List[int]):
        """Add URL to queue."""
        for idx in monitors:
            if idx in self._controllers:
                self._controllers[idx].add_to_queue(url)
                self.queue_updated.emit(idx, self._controllers[idx].queue_size)
    
    def _on_process_ended(self, screen_index: int):
        """VLC process ended."""
        logger.info(f"Screen {screen_index}: VLC process ended")
        
        if screen_index in self._controllers:
            del self._controllers[screen_index]
        
        self._active_screens -= 1
        
        if self._active_screens <= 0:
            self._release_hard_lock()
            self._audio_manager.unmute_other_apps()
            self.all_finished.emit()
    
    def _on_queue_empty(self, screen_index: int):
        """Queue empty."""
        logger.info(f"Screen {screen_index}: Queue empty")
    
    def _release_hard_lock(self):
        """Release hard lock."""
        if self._lock_applied:
            self.hard_lock.unlock()
            self._lock_applied = False
            logger.info("HardLock released - system input restored")
    
    def _on_error(self, msg: str):
        """Error occurred."""
        logger.error(f"VLC error: {msg}")
        self.error_occurred.emit(msg)
    
    def skip_all(self):
        """Skip current video."""
        for controller in self._controllers.values():
            controller.skip()
    
    def stop_all(self):
        """Stop all VLC instances."""
        for controller in self._controllers.values():
            controller.stop()
        self._controllers.clear()
        self._active_screens = 0
        self._release_hard_lock()
        self._audio_manager.unmute_other_apps()
    
    @property
    def is_playing(self) -> bool:
        return self._active_screens > 0
    
    @property
    def total_queue_size(self) -> int:
        return sum(c.queue_size for c in self._controllers.values())


@dataclass
class QueuedVideo:
    url: str
    settings: Dict[str, Any]


class VideoPlayer(QObject):
    """Main video player with seamless queue."""
    
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
        
        vlc = find_vlc()
        if vlc:
            logger.info(f"VideoPlayer initialized - VLC: {vlc}")
            # Check plugin path
            plugin_path = get_vlc_plugin_path(vlc)
            if plugin_path:
                logger.info(f"Plugin path found: {plugin_path}")
            else:
                logger.warning(f"No plugin path found for VLC at {vlc}")
            logger.info(f"Settings: input_lock={self._input_lock}, volume={self._volume}")
        else:
            logger.error("VLC not found!")
    
    @property
    def is_playing(self) -> bool:
        return self._is_playing
    
    @property
    def vlc_available(self) -> bool:
        return find_vlc() is not None
    
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
        }
    
    def update_settings(self, **kwargs):
        if "input_lock" in kwargs:
            self._input_lock = bool(kwargs["input_lock"])
        if "mute_other_audio" in kwargs:
            self._mute_other_audio = bool(kwargs["mute_other_audio"])
        if "click_through" in kwargs:
            self._click_through = bool(kwargs["click_through"])
            if self._click_through:
                self._input_lock = False
        if "opacity" in kwargs:
            self._opacity = max(10, min(100, int(kwargs["opacity"])))
        if "multi_monitor" in kwargs:
            self._multi_monitor = bool(kwargs["multi_monitor"])
        if "selected_monitors" in kwargs:
            self._selected_monitors = list(kwargs.get("selected_monitors", []))
        if "volume" in kwargs:
            self._volume = max(0, min(256, int(kwargs["volume"])))
    
    def get_available_monitors(self) -> List[int]:
        return list(range(len(QGuiApplication.screens())))
    
    def play(self, url: str, **kwargs) -> bool:
        """Play video or add to queue."""
        logger.info(f"play() called with url={url[:80]}...")
        self.update_settings(**kwargs)
        
        if not self.vlc_available:
            self.error_occurred.emit("VLC not found")
            return False
        
        monitors = self._selected_monitors if (self._multi_monitor and self._selected_monitors) else [0]
        
        logger.info(f"Using monitors: {monitors}")
        
        if not self._is_playing:
            self._manager = SeamlessPlaybackManager(self.hard_lock, self.settings)
            self._manager.all_finished.connect(self._on_playback_finished)
            self._manager.error_occurred.connect(self._on_error)
            self._manager.queue_updated.connect(self._on_queue_updated)
            
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
            self._manager.add_to_queue(url, monitors)
            self.queue_updated.emit(self.queue_size)
            return True
    
    def _on_queue_updated(self, screen_index: int, queue_size: int):
        self.queue_updated.emit(self.queue_size)
    
    def _on_playback_finished(self):
        self._is_playing = False
        self._manager = None
        self._current_monitors = []
        self.status_changed.emit(False)
        logger.info("Seamless playback finished")
    
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