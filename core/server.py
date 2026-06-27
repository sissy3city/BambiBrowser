"""HTTP server for browser extension communication."""

import json
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable, TYPE_CHECKING
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, pyqtSignal, Qt

if TYPE_CHECKING:
    from core.player import VideoPlayer

logger = logging.getLogger("BambiBrowser.Server")


class PlayRequest:
    """Container for play request data."""
    def __init__(self, url: str, multi_monitor: bool = False, 
                 input_lock: bool = True, selected_monitors: list = None,
                 volume: int = 256, mute_other_audio: bool = False,
                 click_through: bool = False,
                 opacity: int = 100, escape_grace: int = 10):
        self.url = url
        self.multi_monitor = multi_monitor
        self.input_lock = input_lock
        self.selected_monitors = selected_monitors or []
        self.volume = volume
        self.mute_other_audio = mute_other_audio
        self.click_through = click_through
        self.opacity = opacity
        self.escape_grace = escape_grace


class BambiRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for BambiBrowser API."""
    
    player_instance: Optional["VideoPlayer"] = None
    server_instance: Optional["BambiServer"] = None
    permanence_callback: Optional[Callable[[bool], bool]] = None
    
    def log_message(self, *args):
        """Suppress default HTTP logging."""
        pass
    
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
    
    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))
    
    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()
    
    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self._send_json({"status": "running", "version": "5.0"})
            elif parsed.path == "/status":
                self._handle_status()
            elif parsed.path == "/monitors":
                self._handle_monitors()
            elif parsed.path == "/settings":
                self._handle_get_settings()
            else:
                self._send_json({"error": "not_found"}, 404)
        except Exception as e:
            logger.error(f"GET {self.path} error: {e}")
            self._send_json({"error": "internal_error"}, 500)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            data = json.loads(body.decode("utf-8") or "{}")
            logger.debug(f"POST {parsed.path} data: {data}")

            if parsed.path == "/play":
                self._handle_play(data)
            elif parsed.path == "/stop":
                self._handle_stop(data)
            elif parsed.path == "/settings":
                self._handle_post_settings(data)
            elif parsed.path == "/permanence":
                self._handle_permanence(data)
            else:
                self._send_json({"error": "not_found"}, 404)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid_json"}, 400)
        except Exception as e:
            logger.error(f"POST {self.path} error: {e}")
            self._send_json({"error": "internal_error"}, 500)
    
    # ----- Handlers -----
    def _handle_status(self):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return
        self._send_json(self.player_instance.get_status())
    
    def _handle_monitors(self):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return
        monitors = self.player_instance.get_available_monitors()
        self._send_json({"monitors": monitors, "count": len(monitors)})
    
    def _handle_get_settings(self):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return
        self._send_json(self.player_instance.settings)
    
    def _handle_play(self, data: dict):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return

        # ---- Settings lock check ----
        from PyQt6.QtCore import QSettings
        settings = QSettings("BambiBrowser", "Settings")
        otp_hash = settings.value("otp_hash", "")
        if not otp_hash or otp_hash.strip() == "":
            logger.warning("Play request rejected: Settings not locked")
            self._send_json({
                "error": "settings_not_locked",
                "message": "Settings must be saved and locked before playback."
            }, 403)
            return

        video_url = data.get("url") or data.get("videoUrl")
        if not video_url:
            self._send_json({"error": "no_url"}, 400)
            return

        saved_settings = self.player_instance.settings

        # ---- Video length limit ----
        if saved_settings.get("max_video_length_enabled", False):
            from core.duration_helper import estimate_video_duration
            max_video_minutes = saved_settings.get("max_video_length_minutes", 10)
            action = saved_settings.get("max_video_length_action", "Block & Show Warning")
            duration_seconds, source = estimate_video_duration(video_url)

            if duration_seconds is not None:
                video_duration_minutes = duration_seconds // 60
                max_seconds = max_video_minutes * 60
                if duration_seconds > max_seconds:
                    logger.warning(f"Video exceeds limit: {video_duration_minutes}m > {max_video_minutes}m")
                    if action == "Block & Show Warning":
                        self._send_json({
                            "error": "video_length_exceeded",
                            "message": f"Video is ~{video_duration_minutes}m, exceeds limit of {max_video_minutes}m"
                        }, 403)
                        return
                    elif action == "Auto-Skip Video":
                        self._send_json({
                            "skipped": True,
                            "message": f"Video skipped: ~{video_duration_minutes}m > {max_video_minutes}m limit"
                        }, 200)
                        return
                    elif action == "Stop Playback":
                        self.player_instance.stop()
                        self._send_json({
                            "error": "playback_stopped",
                            "message": f"Playback stopped: Video exceeds {max_video_minutes}m limit"
                        }, 403)
                        return
                    # Warn & Allow – continue

        # ---- Queue duration limit ----
        if saved_settings.get("max_queue_duration_enabled", False):
            max_queue_minutes = saved_settings.get("max_queue_duration_minutes", 60)
            action = saved_settings.get("max_queue_duration_action", "Reject New Videos")

            # Get current queue duration
            current_queue_sec = self.player_instance.queue_duration
            # Estimate duration for this video
            from core.duration_helper import estimate_video_duration
            new_duration_sec, _ = estimate_video_duration(video_url)
            if new_duration_sec is None:
                new_duration_sec = 60  # fallback 1 minute

            total_estimated = current_queue_sec + new_duration_sec
            max_sec = max_queue_minutes * 60

            if total_estimated > max_sec:
                logger.warning(f"Queue duration limit: {total_estimated//60}m > {max_queue_minutes}m")
                if action == "Reject New Videos":
                    self._send_json({
                        "error": "queue_duration_limit",
                        "message": f"Queue would be ~{total_estimated//60}m (limit: {max_queue_minutes}m)"
                    }, 403)
                    return
                elif action == "Stop Playback":
                    self.player_instance.stop()
                    self._send_json({
                        "error": "playback_stopped",
                        "message": f"Playback stopped: Queue exceeded {max_queue_minutes}m limit"
                    }, 403)
                    return
                elif action == "Clear Queue":
                    self.player_instance.clear_queue()
                    logger.info("Queue cleared due to duration limit")
                # Warn Only: continue

        # ---- Build play request ----
        request = PlayRequest(
            url=video_url,
            multi_monitor=bool(data.get("multi_monitor", saved_settings.get("multi_monitor", False))),
            input_lock=bool(data.get("input_lock", data.get("hard_lock", saved_settings.get("input_lock", True)))),
            selected_monitors=list(data.get("selected_monitors", saved_settings.get("selected_monitors", []))),
            volume=int(data.get("volume", saved_settings.get("volume", 256))),
            mute_other_audio=bool(data.get("mute_other_audio", saved_settings.get("mute_other_audio", False))),
            click_through=bool(data.get("click_through", saved_settings.get("click_through", False))),
            opacity=int(data.get("opacity", saved_settings.get("opacity", 100))),
        )

        logger.info(f"Play request accepted: {video_url[:60]}...")
        self.server_instance.play_requested.emit(request)
        self._send_json({"status": "playing", "queued": True})
    
    def _handle_stop(self, data: dict):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return
        self.server_instance.stop_requested.emit()
        self._send_json({"status": "stopped"})
    
    def _handle_post_settings(self, data: dict):
        if not self.player_instance:
            self._send_json({"error": "no_player"}, 500)
            return
        logger.info(f"Settings update requested: {data}")
        self.server_instance.settings_requested.emit(data)
        self._send_json({"status": "updated", "settings": self.player_instance.settings})
    
    def _handle_permanence(self, data: dict):
        enable = bool(data.get("enable", False))
        if self.permanence_callback:
            success = self.permanence_callback(enable)
            if success:
                self._send_json({"success": True, "message": "Permanence updated"})
            else:
                self._send_json({"success": False, "error": "Failed to update permanence"}, 500)
        else:
            self._send_json({"success": False, "error": "Permanence not supported"}, 500)


class BambiServer(QObject):
    """HTTP server for extension communication."""
    
    status_changed = pyqtSignal(bool)
    play_requested = pyqtSignal(object)
    stop_requested = pyqtSignal()
    settings_requested = pyqtSignal(dict)
    
    def __init__(self, player: "VideoPlayer", port: int = 5655):
        super().__init__()
        self.player = player
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        BambiRequestHandler.player_instance = player
        BambiRequestHandler.server_instance = self
        
        self.play_requested.connect(self._on_play_requested)
        self.stop_requested.connect(self.player.stop)
        self.settings_requested.connect(self._on_settings_requested)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def set_permanence_callback(self, callback: Callable[[bool], bool]):
        BambiRequestHandler.permanence_callback = callback
    
    def _on_play_requested(self, request: PlayRequest):
        settings = {
            "multi_monitor": request.multi_monitor,
            "input_lock": request.input_lock,
            "selected_monitors": request.selected_monitors,
            "volume": request.volume,
            "mute_other_audio": request.mute_other_audio,
            "click_through": request.click_through,
            "opacity": request.opacity,
        }
        logger.info(f"Playing with settings: {settings}")
        self.player.play(request.url, **settings)
    
    def _on_settings_requested(self, data: dict):
        clean_data = {}
        key_mappings = {
            "input_lock": ["input_lock", "inputLock", "hard_lock", "hardLock"],
            "mute_other_audio": ["mute_other_audio", "muteOtherAudio"],
            "click_through": ["click_through", "clickThrough"],
            "opacity": ["opacity"],
            "multi_monitor": ["multi_monitor", "multiMonitor"],
            "selected_monitors": ["selected_monitors", "selectedMonitors"],
            "volume": ["volume"],
        }
        for target_key, possible_keys in key_mappings.items():
            for key in possible_keys:
                if key in data:
                    clean_data[target_key] = data[key]
                    break
        logger.info(f"Applying settings: {clean_data}")
        self.player.update_settings(**clean_data)
    
    def start(self) -> bool:
        try:
            self._server = HTTPServer(("127.0.0.1", self.port), BambiRequestHandler)
            self._thread = threading.Thread(target=self._run_server, daemon=True)
            self._thread.start()
            self._running = True
            self.status_changed.emit(True)
            logger.info(f"HTTP server started on http://127.0.0.1:{self.port}")
            return True
        except OSError as e:
            logger.error(f"Failed to start server: {e}")
            return False
    
    def _run_server(self):
        try:
            self._server.serve_forever()
        except Exception as e:
            logger.error(f"Server error: {e}")
            self._running = False
            self.status_changed.emit(False)
    
    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as e:
                logger.error(f"Error stopping server: {e}")
            finally:
                self._running = False
                self.status_changed.emit(False)
                logger.info("HTTP server stopped")