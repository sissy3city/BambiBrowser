"""Video player using mpv directly - multi-screen, sync-free, with queue support."""

import os
import sys
import time
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from collections import deque

import math
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QRectF, QPointF
from PyQt6.QtGui import QGuiApplication, QPainter, QColor, QPen, QFont, QPolygonF, QMovie
from PyQt6.QtWidgets import QLabel, QLCDNumber, QWidget, QVBoxLayout
from PyQt6.QtWidgets import QSizePolicy
try:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False

from core.hard_lock import HardLock
from core.audio_muter import mute_other_applications, unmute_all_applications, is_audio_muting_available
from core.window_manager import apply_window_properties

logger = logging.getLogger("BambiBrowser.Player")


class SpiralCanvas(QWidget):
    """Qt rendering of the extension's interlocking fuzzy spiral."""

    def __init__(self, color_scheme="neon", custom_colors=""):
        super().__init__()
        self.setMinimumSize(400, 400)
        self.frame = 0
        self.words = [
            "Airhead barbie", "Bambi", "Bambi butt lock", "Bambi cum and collapse",
            "Bambi cunt lock", "Bambi does as shes told", "Bambi face lock",
            "Bambi freeze", "Bambi hips lock", "Bambi limbs lock", "Bambi limp",
            "Bambi lips lock", "Bambi posture lock", "Bambi reset", "Bambi sleep",
            "Bambi throat lock", "Bambi tits lock", "Bambi uniform lock",
            "Bambi waist lock", "Bambi wake and obey", "Bimbo doll",
            "Blonde moment", "Braindead bobblehead", "Cock zombie now",
            "Cockblank lovedoll", "Drop for cock", "Giggletime", "Good girl",
            "Primped and pampered", "Safe and secure", "Snap and forget",
            "Zap cock drain obey"
        ]
        self.word_index = 0
        self.last_time = 0.0

        self.settings = {
            'arms': 5, 'turns': 2, 'curve': 2.5, 'width': 0.5,
            'wobble': 0.05, 'wphase': 0.1, 'wspeed': 0.5,
            'speed': 0.8, 'dir': 1
        }
        self.colors = self._get_colors(color_scheme, custom_colors)

    @staticmethod
    def _get_colors(color_scheme, custom_colors):
        palettes = {
            "neon": ("#ffffff", "#00ff00", "#000000", "#ff00ff"),
            "pastel": ("#ffd1dc", "#98fb98", "#d8bfd8", "#ffb6c1"),
            "dark": ("#303030", "#5c6bc0", "#080808", "#8e24aa"),
        }
        if color_scheme == "custom" and custom_colors:
            colors = [value.strip() for value in custom_colors.split(",") if value.strip()]
            if colors:
                primary = colors[0]
                secondary = colors[1] if len(colors) > 1 else primary
                return primary, secondary, "#000000", secondary
        return palettes.get(color_scheme, palettes["neon"])

    def _point(self, offset, cur, w_angle, w_size):
        settings = self.settings
        rotation = cur * settings['turns'] * math.tau + offset
        radius = self.radius * math.pow(cur, settings['curve'])
        if settings['dir']:
            rotation = math.tau - rotation
        rotation += settings['wobble'] * math.sin(cur * w_size + w_angle)
        return QPointF(
            self.center_x + radius * math.cos(rotation),
            self.center_y + radius * math.sin(rotation)
        )

    def _arm(self, offset, w_angle, w_size):
        steps = max(1, int(90 * self.settings['turns']))
        return [self._point(offset, i / steps, w_angle, w_size) for i in range(steps + 1)]

    def _draw_layer(self, painter, angle, fill_color, stroke_color, w_angle, w_size):
        settings = self.settings
        band_width = settings['width'] / settings['arms']
        painter.setPen(QPen(QColor(stroke_color), 3))
        for index in range(settings['arms']):
            offset = index / settings['arms'] * math.tau + angle
            outside = self._arm(offset, w_angle, w_size)
            inside = self._arm(offset + band_width * math.tau, w_angle, w_size)
            painter.drawPolyline(QPolygonF(outside))
            painter.drawPolyline(QPolygonF(inside))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clear background
        painter.fillRect(self.rect(), QColor("#0a0a0a"))

        self.center_x = self.width() / 2
        self.center_y = self.height() / 2
        self.radius = max(self.width(), self.height()) * 0.95
        self.frame += 1
        current_time = self.frame / 60.0
        settings = self.settings
        speed = current_time * settings['dir'] * settings['speed']
        w_angle = current_time * settings['wspeed']
        w_phase = current_time * settings['wphase']
        w_size = math.pi * (5 - 4 * math.cos(w_phase))
        self._draw_layer(painter, speed, self.colors[0], self.colors[1], w_angle, w_size)
        self._draw_layer(painter, speed + math.pi / 2, self.colors[2], self.colors[3], w_angle + math.pi / 2, w_size)

        painter.setPen(QPen(QColor('#ff6bd6')))
        painter.setFont(QFont('Arial', 28, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.words[self.word_index])


def get_mpv_path() -> Optional[Path]:
    """Locate mpv executable in bundled folder or system PATH."""
    base = Path(__file__).parent.parent

    if sys.platform == "win32":
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

    which = shutil.which("mpv")
    return Path(which) if which else None


class MPVProcess(QObject):
    """Manages a single mpv instance on one screen."""
    process_ended = pyqtSignal(int)   # screen_index
    error_occurred = pyqtSignal(str)

    def __init__(self, screen_index: int, settings: Dict[str, Any], mute_secondary_audio: bool = True):
        super().__init__()
        self.screen_index = screen_index
        self.settings = settings
        self.mute_secondary_audio = mute_secondary_audio
        self._process: Optional[subprocess.Popen] = None
        self._is_playing = False
        self._mpv_path = get_mpv_path()

        if not self._mpv_path:
            logger.error(f"mpv not found for screen {screen_index}")

    def _build_command(self, url: str) -> List[str]:
        """Build the mpv command line."""
        is_bambicloud_audio = self.settings.get('bambicloud_audioOnly') or self.settings.get('bambicloud_audio_only')
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
            f"--referrer={'https://bambicloud.com/' if is_bambicloud_audio else 'https://hypnotube.com/'}",
            "--hwdec=auto-safe",
            "--vo=gpu-next",
            "--video-sync=display-resample",
            "--profile=fast",
            "--cache=yes",
            "--cache-secs=2.0",
        ]

        if self.screen_index > 0 and self.mute_secondary_audio:
            cmd.append("--no-audio")
        else:
            volume = self.settings.get('volume', 100)
            percent = min(100, int(volume * 100 / 256))
            cmd.append(f"--volume={percent}")

        if is_bambicloud_audio:
            cmd = [argument for argument in cmd if not argument.startswith(("--hwdec=", "--vo=", "--video-sync=", "--profile="))]
            cmd.extend([
                "--no-video",
                "--force-window=no",
                "--audio-buffer=1.0",
                "--demuxer-readahead-secs=20",
            ])

        return cmd

    def start(self, url: str) -> bool:
        """Launch mpv."""
        if not self._mpv_path:
            self.error_occurred.emit("mpv not found")
            return False

        cmd = self._build_command(url)
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            env = None
            if sys.platform != "win32":
                # Force mpv onto XWayland rather than a native Wayland surface.
                # Wayland doesn't let a client place itself on an arbitrary
                # monitor - under a native Wayland surface, --screen=N and all
                # of core/linux/window_manager_linux.py's opacity/click-through/
                # topmost handling silently do nothing and every instance
                # collapses onto the compositor's active output. Stripping
                # WAYLAND_DISPLAY makes mpv fall back to X11/XWayland, where
                # --screen=N correctly targets the same monitor indices Qt
                # reports via get_available_monitors().
                env = os.environ.copy()
                env.pop("WAYLAND_DISPLAY", None)
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                env=env,
            )
            self._is_playing = True
            logger.info(f"Screen {self.screen_index}: mpv started (PID {self._process.pid})")

            if self.settings.get('click_through') or self.settings.get('opacity', 100) < 100:
                QTimer.singleShot(800, self._apply_window_properties)

            QTimer.singleShot(500, self._check_process)
            return True
        except Exception as e:
            logger.error(f"Failed to start mpv: {e}")
            self.error_occurred.emit(str(e))
            return False

    def _check_process(self):
        if self._process is None:
            return
        if self._process.poll() is not None:
            self._is_playing = False
            self.process_ended.emit(self.screen_index)
        else:
            QTimer.singleShot(500, self._check_process)

    def _apply_window_properties(self):
        if not self._process:
            return
        opacity = self.settings.get('opacity', 100)
        click_through = self.settings.get('click_through', False)
        applied = apply_window_properties(self._process.pid, opacity, click_through)
        if not applied and self.is_playing:
            QTimer.singleShot(500, self._apply_window_properties)

    def stop(self):
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
    """Manages multiple mpv instances across screens for a single video."""
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

        if self._input_lock_enabled:
            QTimer.singleShot(1000, self._apply_hard_lock)

        if self._mute_other_audio and is_audio_muting_available():
            mpv_pids = [
                player._process.pid
                for player in self._players.values()
                if player._process is not None
            ]
            if mute_other_applications(keep_pids=mpv_pids):
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
                    logger.info("HARDLOCK ACTIVE")
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


# ----- VideoPlayer with queue -----

@dataclass
class QueuedVideo:
    url: str
    settings: Dict[str, Any]
    duration_seconds: Optional[int] = None  # estimated duration, if known


class VideoPlayer(QObject):
    status_changed = pyqtSignal(bool)
    queue_updated = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, hard_lock: HardLock):
        super().__init__()
        self.hard_lock = hard_lock
        self._manager: Optional[SeamlessPlaybackManager] = None
        self._is_playing = False
        self._started_at = 0.0
        self._current_monitors: List[int] = []

        # Queue
        self._queue: deque[QueuedVideo] = deque()
        self._current_video: Optional[QueuedVideo] = None
        self._queue_duration_total = 0  # total duration of queued videos (excluding current)

        # Load settings
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

        # Bambicloud settings
        self._bambicloud_enabled = settings.value("bambicloud/enabled", True, type=bool)
        self._bambicloud_animation_type = settings.value("bambicloud/animation_type", "spiral", type=str)
        self._bambicloud_color_scheme = settings.value("bambicloud/color_scheme", "neon", type=str)
        self._bambicloud_custom_animation_path = settings.value("bambicloud/custom_animation_path", "", type=str)
        self._bambicloud_custom_colors = settings.value("bambicloud/custom_colors", "#ff6bd6,#00ff00,#ff00ff", type=str)
        stored_countdown = settings.value("bambicloud/countdown_duration_seconds", None, type=int)
        if stored_countdown is None:
            stored_countdown = settings.value("bambicloud/countdown_duration", 2, type=int) * 60
        self._bambicloud_countdown_duration = max(5, min(300, stored_countdown))
        self._bambicloud_countdown_enabled = settings.value("bambicloud/countdown_enabled", True, type=bool)

        # Initialize countdown overlay variables
        self._countdown_overlay: Optional[QWidget] = None
        self._countdown_label: Optional[QLabel] = None
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._countdown_remaining = self._bambicloud_countdown_duration
        self._countdown_lock_applied = False

        # Initialize spiral overlay variables
        self._spiral_overlay: Optional[QWidget] = None
        self._spiral_canvas = None
        self._custom_media_player = None
        self._custom_audio_output = None
        self._custom_movie = None
        self._spiral_timer: Optional[QTimer] = None
        self._spiral_frame = 0
        self._pending_qv: Optional[QueuedVideo] = None
        self._pending_monitors: List[int] = []
        self._pending_playback_after_spiral = False

        if not get_mpv_path():
            logger.error("mpv not found - playback unavailable")
        else:
            logger.info("VideoPlayer initialized (mpv direct with queue)")

    def _update_countdown_display(self):
        """Update the countdown display"""
        if self._countdown_label:
            minutes, seconds = divmod(max(0, self._countdown_remaining), 60)
            self._countdown_label.display(f"{minutes:02d}:{seconds:02d}")
            self._countdown_label.repaint()

    def _update_countdown(self):
        """Update countdown timer"""
        self._countdown_remaining -= 1
        self._update_countdown_display()

        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._start_playback_after_countdown()

    def _on_countdown_clicked(self, event):
        """Handle click on countdown overlay"""
        # The global HardLock setting controls whether countdown can be skipped.
        can_skip = not self._input_lock

        if can_skip:
            self._countdown_timer.stop()
            self._start_playback_after_countdown()
        else:
            # Show visual feedback that skipping is not allowed
            if self._countdown_label:
                self._countdown_label.setStyleSheet("""
                    font-size: 48px;
                    font-weight: bold;
                    color: #ff6b6b;  /* Red color to indicate not allowed */
                """)
                # Reset color after brief flash
                QTimer.singleShot(500, lambda: self._countdown_label.setStyleSheet("""
                    font-size: 48px;
                    font-weight: bold;
                    color: #ff6bd6;
                """))

    def _hide_countdown_overlay(self):
        """Hide and cleanup the countdown overlay"""
        if self._countdown_overlay:
            self._countdown_timer.stop()
            self._countdown_overlay.hide()
            self._countdown_overlay.deleteLater()
            self._countdown_overlay = None
            self._countdown_label = None
        if self._countdown_lock_applied:
            self.hard_lock.unlock()
            self._countdown_lock_applied = False

    def _on_countdown_key_press(self, event):
        """Handle key press on countdown overlay - escape to skip if allowed"""
        if event.key() == Qt.Key.Key_Escape:
            # The global HardLock setting controls whether countdown can be skipped.
            can_skip = not self._input_lock

            if can_skip:
                self._countdown_timer.stop()
                self._start_playback_after_countdown()
            else:
                # Show visual feedback that skipping is not allowed
                if self._countdown_label:
                    self._countdown_label.setStyleSheet("""
                        font-size: 48px;
                        font-weight: bold;
                        color: #ff6b6b;  /* Red color to indicate not allowed */
                    """)
                    # Reset color after brief flash
                    QTimer.singleShot(500, lambda: self._countdown_label.setStyleSheet("""
                        font-size: 48px;
                        font-weight: bold;
                        color: #ff6bd6;
                    """))

    def _show_countdown_overlay(self, qv: QueuedVideo, monitors: List[int]):
        """Show countdown overlay before starting bambicloud playback"""
        if self._countdown_overlay is not None:
            logger.info("Countdown already active; ignoring duplicate overlay request")
            return

        # Store the video info for after countdown
        self._pending_qv = qv
        self._pending_monitors = monitors

        # Create and show countdown overlay (blank screen with just countdown)
        self._countdown_overlay = QWidget()
        self._countdown_overlay.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        # Set background to black for blank screen effect
        self._countdown_overlay.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._countdown_overlay.setStyleSheet("background-color: #000000; color: #ff6bd6;")

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        # Add countdown label (only thing visible on blank screen)
        self._countdown_label = QLCDNumber()
        self._countdown_label.setFixedSize(520, 150)
        self._countdown_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._countdown_label.setDigitCount(5)
        self._countdown_label.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self._countdown_label.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._countdown_label.setStyleSheet("""
            font-family: 'Courier New';
            font-size: 88px;
            font-weight: bold;
            color: #ff6bd6;
            background-color: #000000;
            letter-spacing: 4px;
        """)
        layout.addWidget(self._countdown_label, 0, Qt.AlignmentFlag.AlignCenter)

        self._countdown_overlay.setLayout(layout)

        screen = QGuiApplication.primaryScreen().geometry()
        self._countdown_overlay.setGeometry(screen)

        self._countdown_overlay.setWindowState(Qt.WindowState.WindowFullScreen)
        self._countdown_overlay.showFullScreen()

        if self._input_lock:
            self.hard_lock.lock()
            self._countdown_lock_applied = True

        # Set up countdown timer
        self._countdown_remaining = self._bambicloud_countdown_duration
        self._update_countdown_display()
        self._countdown_timer.start(1000)  # update every second

        # Make overlay clickable to skip if allowed
        self._countdown_overlay.mousePressEvent = self._on_countdown_clicked

        # Add escape key handling to skip countdown
        self._countdown_overlay.keyPressEvent = self._on_countdown_key_press
        self._countdown_overlay.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._countdown_overlay.setFocus()

    def _start_playback_after_countdown(self):
        """Start playback after countdown finishes or is skipped"""
        # Hide and cleanup countdown overlay
        self._hide_countdown_overlay()

        # The spiral is a BambiCloud visual; Hypnotube uses the shared countdown only.
        if (self._pending_qv.settings.get('bambicloud', False) and
            self._bambicloud_enabled and self._bambicloud_animation_type != "none"):
            self._show_spiral_overlay()

        if hasattr(self, '_pending_qv') and hasattr(self, '_pending_monitors'):
            success = self._start_playback(self._pending_qv, self._pending_monitors)
            delattr(self, '_pending_qv')
            delattr(self, '_pending_monitors')
            if not success:
                self._hide_spiral_overlay()
            return success
        return False

    # ---------- Properties ----------
    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _show_spiral_overlay(self):
        """Show spiral overlay similar to extension implementation"""
        # Create and show spiral overlay (blank screen with spiral visualization)
        self._spiral_overlay = QWidget()
        self._spiral_overlay.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        # Set background to #0a0a0a for bambicloud effect
        self._spiral_overlay.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._spiral_overlay.setStyleSheet("background-color: #000000; color: #ff6bd6;")

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        # Add spiral canvas using custom widget
        custom_path = self._bambicloud_custom_animation_path
        animation_type = self._bambicloud_animation_type
        custom_loaded = False
        if animation_type == "custom" and custom_path and os.path.isfile(custom_path):
            custom_loaded = self._show_custom_animation(custom_path, layout)
        if not custom_loaded:
            self._spiral_canvas = SpiralCanvas(
                self._bambicloud_color_scheme,
                self._bambicloud_custom_colors
            )
            self._spiral_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._spiral_canvas, 1)

        self._spiral_overlay.setLayout(layout)

        # Cover the display while BambiCloud audio is playing.
        screen = QGuiApplication.primaryScreen().geometry()
        self._spiral_overlay.setGeometry(screen)

        self._spiral_overlay.setWindowState(Qt.WindowState.WindowFullScreen)
        self._spiral_overlay.showFullScreen()

        # Initialize spiral animation
        self._spiral_frame = 0
        self._spiral_words = self._spiral_canvas.words if self._spiral_canvas else []
        self._spiral_word_index = 0

        # Set up a light animation timer; the canvas does the actual painting.
        self._spiral_timer = QTimer(self)
        self._spiral_timer.timeout.connect(self._update_spiral_animation)
        self._spiral_timer.start(33)  # ~30 FPS

        # Make overlay unskippable during spiral display
        self._spiral_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def _update_spiral_animation(self):
        """Update spiral animation frame"""
        if not self._spiral_overlay:
            return

        self._spiral_frame += 1

        # Update word display every ~3 seconds at 30 FPS.
        if self._spiral_canvas and self._spiral_frame % 90 == 0:
            self._spiral_word_index = (self._spiral_word_index + 1) % len(self._spiral_words)
            if self._spiral_canvas:
                self._spiral_canvas.word_index = self._spiral_word_index

        # Trigger repaint
        if hasattr(self, '_spiral_overlay') and self._spiral_overlay:
            if self._spiral_canvas:
                self._spiral_canvas.update()

    def _hide_spiral_overlay(self):
        """Hide and cleanup the spiral overlay"""
        if self._spiral_timer:
            self._spiral_timer.stop()
            self._spiral_timer.deleteLater()
            self._spiral_timer = None

        if self._spiral_overlay:
            self._spiral_overlay.hide()
            self._spiral_overlay.deleteLater()
            self._spiral_overlay = None

        if self._custom_media_player:
            self._custom_media_player.stop()
            self._custom_media_player.deleteLater()
            self._custom_media_player = None
        if self._custom_audio_output:
            self._custom_audio_output.deleteLater()
            self._custom_audio_output = None
        if self._custom_movie:
            self._custom_movie.stop()
            self._custom_movie.deleteLater()
            self._custom_movie = None

        # Start playback after spiral if pending
        if self._pending_playback_after_spiral and hasattr(self, '_pending_qv') and hasattr(self, '_pending_monitors'):
            self._pending_playback_after_spiral = False
            success = self._start_playback(self._pending_qv, self._pending_monitors)
            # Cleanup pending vars
            delattr(self, '_pending_qv')
            delattr(self, '_pending_monitors')
            return success

        return False

    def _show_custom_animation(self, path, layout):
        suffix = Path(path).suffix.lower()
        if suffix == ".gif":
            self._custom_movie = QMovie(path)
            self._custom_movie.setCacheMode(QMovie.CacheMode.CacheAll)
            animation_label = QLabel()
            animation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            animation_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            animation_label.setMovie(self._custom_movie)
            layout.addWidget(animation_label, 1)
            self._custom_movie.start()
            return True
        if not MULTIMEDIA_AVAILABLE:
            logger.warning("Qt multimedia unavailable; using spiral for custom animation")
            return False
        video_widget = QVideoWidget()
        video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(video_widget, 1)
        self._custom_media_player = QMediaPlayer(self)
        self._custom_audio_output = QAudioOutput(self)
        self._custom_audio_output.setVolume(0.0)
        self._custom_media_player.setAudioOutput(self._custom_audio_output)
        self._custom_media_player.setVideoOutput(video_widget)
        self._custom_media_player.setLoops(QMediaPlayer.Loops.Infinite)
        self._custom_media_player.setSource(QUrl.fromLocalFile(path))
        self._custom_media_player.play()
        return True

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def queue_duration(self) -> int:
        return self._queue_duration_total

    @property
    def vlc_available(self) -> bool:
        return get_mpv_path() is not None

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
            # Bambicloud settings
            "bambicloud_enabled": self._bambicloud_enabled,
            "bambicloud_animation_type": self._bambicloud_animation_type,
            "bambicloud_color_scheme": self._bambicloud_color_scheme,
            "bambicloud_custom_animation_path": self._bambicloud_custom_animation_path,
            "bambicloud_custom_colors": self._bambicloud_custom_colors,
            "bambicloud_countdown_duration": self._bambicloud_countdown_duration,
            "bambicloud_countdown_enabled": self._bambicloud_countdown_enabled,
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
        # Bambicloud settings
        if "bambicloud_enabled" in kwargs:
            self._bambicloud_enabled = bool(kwargs["bambicloud_enabled"])
        if "bambicloud_animation_type" in kwargs:
            self._bambicloud_animation_type = str(kwargs["bambicloud_animation_type"])
        if "bambicloud_color_scheme" in kwargs:
            self._bambicloud_color_scheme = str(kwargs["bambicloud_color_scheme"])
        if "bambicloud_custom_animation_path" in kwargs:
            self._bambicloud_custom_animation_path = str(kwargs["bambicloud_custom_animation_path"])
        if "bambicloud_custom_colors" in kwargs:
            self._bambicloud_custom_colors = str(kwargs["bambicloud_custom_colors"])
        if "bambicloud_countdown_duration" in kwargs:
            self._bambicloud_countdown_duration = max(5, min(300, int(kwargs["bambicloud_countdown_duration"])))
        if "bambicloud_countdown_enabled" in kwargs:
            self._bambicloud_countdown_enabled = bool(kwargs["bambicloud_countdown_enabled"])

    def get_available_monitors(self) -> List[int]:
        return list(range(len(QGuiApplication.screens())))

    # ---------- Playback control ----------
    def play(self, url: str, **kwargs) -> bool:
        """Play a video. If already playing, add to queue (unless queue full)."""
        self.update_settings(**kwargs)

        if not self.vlc_available:
            self.error_occurred.emit("mpv not found")
            return False

        # Determine monitors
        if self._multi_monitor:
            monitors = self._selected_monitors or self.get_available_monitors()
        else:
            monitors = [0]

        # Get duration for queue management (optional)
        duration = None
        if self._max_video_length_enabled or self._max_queue_duration_enabled:
            from core.duration_helper import estimate_video_duration
            dur, _ = estimate_video_duration(url)
            duration = dur

        # Create QueuedVideo
        qv = QueuedVideo(url=url, settings=kwargs.copy(), duration_seconds=duration)

        # Check the shared single-file limit for all supported media types.
        if self._max_video_length_enabled and duration is not None:
            max_sec = self._max_video_length_minutes * 60
            if duration > max_sec:
                action = self._max_video_length_action
                if action == "Block & Show Warning":
                    self.error_occurred.emit(f"Video too long: {duration//60}m > {self._max_video_length_minutes}m")
                    return False
                elif action == "Auto-Skip Video":
                    logger.info(f"Skipping long video: {duration//60}m > {max_sec//60}m")
                    return True  # pretend success, but we skip
                elif action == "Stop Playback":
                    self.stop()
                    self.error_occurred.emit(f"Stopped playback: video exceeds {self._max_video_length_minutes}m")
                    return False
                # Warn & Allow: fall through

        # Queue duration check
        if self._max_queue_duration_enabled and self._is_playing:
            new_duration = duration or 60  # assume 1 min if unknown
            if self._queue_duration_total + new_duration > self._max_queue_duration_minutes * 60:
                action = self._max_queue_duration_action
                if action == "Reject New Videos":
                    self.error_occurred.emit("Queue duration limit reached")
                    return False
                elif action == "Stop Playback":
                    self.stop()
                    self.error_occurred.emit("Playback stopped: queue duration limit exceeded")
                    return False
                elif action == "Clear Queue":
                    self.clear_queue()
                # Warn Only: continue

        # Show the shared pre-play countdown (BambiCloud gets the spiral on top of it;
        # Hypnotube uses the countdown alone) before starting the first video of a session.
        if not self._is_playing and self._bambicloud_countdown_enabled:
            self._show_countdown_overlay(qv, monitors)
            return True

        if not self._is_playing:
            return self._start_playback(qv, monitors)
        else:
            # Add to queue
            self._queue.append(qv)
            if duration:
                self._queue_duration_total += duration
            logger.info(f"Added to queue: {url[:60]}... (queue size {self.queue_size}, total duration {self.queue_duration}s)")
            self.queue_updated.emit(self.queue_size)
            return True

    def _start_playback(self, qv: QueuedVideo, monitors: List[int]) -> bool:
        """Start playing a QueuedVideo with given monitors."""
        if self._manager is not None:
            self._manager.stop_all()
            self._manager = None

        self._current_video = qv
        self._current_monitors = monitors

        # Determine settings to use - for bambicloud content, use bambicloud safety limits
        is_bambicloud = qv.settings.get('bambicloud', False)
        if is_bambicloud:
            # BambiCloud follows the same safety and queue settings as Bambi Player.
            settings_dict = self.settings.copy()
            settings_dict.update(qv.settings)
        else:
            # Use regular settings for non-bambicloud content
            settings_dict = self.settings

        self._manager = SeamlessPlaybackManager(self.hard_lock, settings_dict)
        self._manager.all_finished.connect(self._on_playback_finished)
        self._manager.error_occurred.connect(self._on_error)

        success = self._manager.start_playback(qv.url, monitors)
        if success:
            self._is_playing = True
            self._started_at = time.time()
            self.status_changed.emit(True)
            self.queue_updated.emit(self.queue_size)
            return True
        else:
            self._manager = None
            return False

    def _on_playback_finished(self):
        """Called when the current video finishes."""
        self._hide_spiral_overlay()
        self._is_playing = False
        self._current_video = None

        if self._queue:
            next_qv = self._queue.popleft()
            if next_qv.duration_seconds:
                self._queue_duration_total -= next_qv.duration_seconds
            if self._bambicloud_countdown_enabled:
                self._show_countdown_overlay(next_qv, self._current_monitors)
            else:
                self._start_playback(next_qv, self._current_monitors)
        else:
            self._manager = None
            self._current_monitors = []
            self.status_changed.emit(False)
            self.queue_updated.emit(0)
            logger.info("Playback finished (queue empty)")

    def _on_error(self, msg: str):
        self.error_occurred.emit(msg)

    def skip(self):
        """Skip current video and move to next in queue."""
        if self._manager:
            self._manager.skip_all()  # triggers _on_playback_finished
        else:
            self.stop()

    def stop(self):
        """Stop all playback and clear queue."""
        # Hide countdown overlay if visible
        self._hide_countdown_overlay()
        self._hide_spiral_overlay()

        if self._manager:
            self._manager.stop_all()
            self._manager = None
        self._is_playing = False
        self._current_video = None
        self._current_monitors = []
        self._queue.clear()
        self._queue_duration_total = 0
        self.status_changed.emit(False)
        self.queue_updated.emit(0)
        logger.info("Playback stopped, queue cleared")

    def clear_queue(self):
        """Clear the queue without stopping current video."""
        self._queue.clear()
        self._queue_duration_total = 0
        self.queue_updated.emit(0)
        logger.info("Queue cleared")

    def cleanup(self):
        self.stop()

    def get_status(self) -> dict:
        return {
            "playing": self._is_playing,
            "position_sec": time.time() - self._started_at if self._is_playing else None,
            "queue_size": self.queue_size,
            "queue_duration_sec": self.queue_duration,
            "settings": self.settings,
            "vlc_available": self.vlc_available,
        }
