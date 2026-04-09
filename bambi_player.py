"""
BambiPlayer - Fullscreen VLC + HardLock + Tray Icon
Receives video URLs from the browser extension and plays them fullscreen.
"""

import os
import sys
import subprocess
import time
import threading
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import ctypes

import mouse
import pystray
from pystray import MenuItem as item
from PIL import Image

# Optional: keyboard may not be installed
try:
  import keyboard
  KEYBOARD_AVAILABLE = True
except ImportError:
  KEYBOARD_AVAILABLE = False

# Optional: multi-monitor support via screeninfo
try:
  from screeninfo import get_monitors
  SCREENINFO_AVAILABLE = True
except ImportError:
  SCREENINFO_AVAILABLE = False


def get_base_dir():
  if getattr(sys, "frozen", False):
    return os.path.dirname(sys.executable)
  return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

# ------------------------------------------------------
# Logging
# ------------------------------------------------------
log_path = os.path.join(BASE_DIR, "bambi_player.log")
logging.basicConfig(
  level=logging.INFO,
  format="[BambiPlayer] %(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("BambiPlayer")
file_handler = logging.FileHandler(log_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
  logging.Formatter("[BambiPlayer] %(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)


# ------------------------------------------------------
# HardLock
# ------------------------------------------------------
class HardLock:
  """
  Aggressive input lock:
  - Blocks all keyboard scancodes (if keyboard module available)
  - Hooks mouse and discards all events
  """

  def __init__(self):
    self.locked = False

  def _block_keys(self):
    if not KEYBOARD_AVAILABLE:
      logger.warning("keyboard module not available; cannot block keys fully")
      return
    for sc in range(1, 255):
      try:
        keyboard.block_key(sc)
      except Exception:
        pass

  def _block_mouse(self, _event):
    return True

  def lock(self):
    if self.locked:
      return
    self.locked = True
    logger.info("HardLock enabled")
    self._block_keys()
    try:
      mouse.hook(self._block_mouse)
    except Exception as e:
      logger.error(f"Failed to hook mouse: {e}")

  def unlock(self):
    if not self.locked:
      return
    try:
      if KEYBOARD_AVAILABLE:
        keyboard.unhook_all()
    except Exception:
      pass
    try:
      mouse.unhook_all()
    except Exception:
      pass
    self.locked = False
    logger.info("HardLock disabled")


# ------------------------------------------------------# Windows API Helper Functions
# ------------------------------------------------------
def get_monitor_info():
  """Get monitor dimensions and positions using Windows API"""
  if not SCREENINFO_AVAILABLE:
    return {}
  
  try:
    monitors = get_monitors()
    info = {}
    for idx, monitor in enumerate(monitors):
      info[idx] = {
        "x": monitor.x,
        "y": monitor.y,
        "width": monitor.width,
        "height": monitor.height,
        "x_end": monitor.x + monitor.width,
        "y_end": monitor.y + monitor.height
      }
      logger.debug(f"Monitor {idx}: x={monitor.x}, y={monitor.y}, w={monitor.width}, h={monitor.height}")
    return info
  except Exception as e:
    logger.error(f"Failed to get monitor info: {e}")
    return {}


# ------------------------------------------------------# Fullscreen Video Player
# ------------------------------------------------------
class FullscreenVideoPlayer:
  def __init__(self, server_port: int = 5655):
    self.server_port = server_port
    self.input_locker = HardLock()
    self.player_processes = []  # list of (process, monitor_index) tuples
    self.is_playing = False
    self.server = None
    self.media_player = None
    self.playback_lock = threading.Lock()  # Prevent race conditions
    self.playlist_queue = []  # Queue for pending videos: list of (url, multi_monitor, input_lock, selected_monitors)

    # Status fields for /status endpoint
    self.status_lock = threading.Lock()
    self.status_playing = False
    self.status_started_at = 0.0
    self.status_expected_length_sec = None

  # ---------- VLC detection ----------

  def _find_media_player(self) -> bool:
    vlc_path = Path(os.path.join(BASE_DIR, "vlc", "vlc.exe"))
    if vlc_path.exists():
      logger.info(f"Using bundled VLC at: {vlc_path}")
      self.media_player = str(vlc_path)
      return True

    # Fallback: try system VLC
    candidates = ["vlc"]
    if sys.platform == "win32":
      candidates.append(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
      candidates.append(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe")

    for c in candidates:
      try:
        subprocess.run([c, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.media_player = c
        logger.info(f"Using system VLC at: {c}")
        return True
      except Exception:
        continue

    logger.error("VLC not found (bundled or system).")
    return False

  # ---------- Multi-monitor helpers ----------

  def _get_monitor_indices(self):
    """
    Returns a list of monitor indices for multi-monitor playback.
    If screeninfo is not available, returns [0] (single monitor).
    """
    if not SCREENINFO_AVAILABLE:
      logger.warning("screeninfo not available; multi-monitor will behave as single-monitor")
      return [0]

    try:
      monitors = get_monitors()
      if not monitors:
        return [0]
      return list(range(len(monitors)))
    except Exception as e:
      logger.error(f"Failed to enumerate monitors: {e}")
      return [0]

  def _build_vlc_args(self, video_url: str, screen_index: int | None = None, total_monitors: int = 1):
    args = [
        self.media_player,
        "--no-one-instance",
        "--no-one-instance-when-started-from-file",
        "--fullscreen",
        "--video-on-top",
        "--play-and-exit",
        "--no-video-title-show",
        "--no-osd",
        "--no-qt-fs-controller",
        "--volume=256",
        "--no-mouse-events",
        "--no-keyboard-events",
    ]

    if screen_index is not None:
        args.append(f"--qt-fullscreen-screennumber={int(screen_index)}")

    if total_monitors > 1 and screen_index is not None and int(screen_index) > 0:
        args.append("--no-audio")

    args.append(video_url)
    return args

  # ---------- Playback ----------

  def _start_vlc_process(self, args):
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    logger.info(f"VLC command: {' '.join(args)}")
    
    # Retry logic for launching VLC (crash-resistant)
    max_retries = 3
    for attempt in range(max_retries):
      try:
        proc = subprocess.Popen(
          args,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
          creationflags=creation_flags,
        )
        
        # Give it a moment to verify it started
        time.sleep(0.2)
        if proc.poll() is None:  # Still running
          return proc
        else:
          logger.warning(f"VLC exited immediately (attempt {attempt+1}/{max_retries})")
          if attempt < max_retries - 1:
            time.sleep(0.5)
      except Exception as e:
        logger.error(f"VLC launch attempt {attempt+1} failed: {e}")
        if attempt < max_retries - 1:
          time.sleep(0.5)
    
    logger.error("VLC failed to start after all retry attempts")
    return None

  def play_fullscreen(self, video_url: str, multi_monitor: bool = False, input_lock: bool = False, selected_monitors: list = None) -> bool:
    # Guard against race conditions
    with self.playback_lock:
      if self.is_playing:
        # Add to queue instead of ignoring
        self.playlist_queue.append((video_url, multi_monitor, input_lock, selected_monitors))
        logger.info(f"✓ Video queued (playlist size: {len(self.playlist_queue)}): {video_url}")
        return True  # Return True to indicate the request was accepted

      if not self.media_player and (not self._find_media_player()):
        return False

      logger.info(f"Starting fullscreen playback: {video_url}")
      logger.info(f"Parameters: multi_monitor={multi_monitor}, selected_monitors={selected_monitors}, input_lock={input_lock}")
      self.player_processes = []
      
      # Store input_lock for _build_vlc_args to use
      self._input_lock = input_lock

      try:
        if multi_monitor:
          # Use selected monitors if provided, otherwise use all monitors
          if selected_monitors and len(selected_monitors) > 0:
            indices = [idx for idx in selected_monitors if isinstance(idx, int)]
            logger.info(f"✓ Using selected monitors: {indices}")
          else:
            indices = self._get_monitor_indices()
            logger.info(f"⚠ No selected monitors provided, using all monitors: {indices}")
          
          # Start VLC on each selected monitor
          for idx in indices:
            args = self._build_vlc_args(video_url, screen_index=idx, total_monitors=len(indices))
            proc = self._start_vlc_process(args)
            
            if proc is None:
              logger.error(f"[MONITOR {idx}] Failed to start VLC process")
              self._cleanup_processes()
              return False
            
            self.player_processes.append((proc, idx))
            logger.info(f"[MONITOR {idx}] Started VLC process (PID {proc.pid})")
            
        else:
          # Single-monitor: let VLC decide (usually primary)
          args = self._build_vlc_args(video_url, screen_index=None)
          proc = self._start_vlc_process(args)
          
          if proc is None:
            logger.error("[MONITOR 0] Failed to start VLC process")
            self._cleanup_processes()
            return False
          
          self.player_processes.append((proc, 0))
          logger.info(f"[MONITOR 0] Started VLC process (PID {proc.pid})")

        if not self.player_processes:
          logger.error("Failed to start any VLC process")
          return False

        self.is_playing = True

        with self.status_lock:
          self.status_playing = True
          self.status_started_at = time.time()
          self.status_expected_length_sec = None  # unknown; extension can treat as generic

        # Give VLC a moment to appear, then lock input if requested
        time.sleep(1)
        if input_lock:
          self.input_locker.lock()

        threading.Thread(target=self._monitor_playback, daemon=True).start()
        logger.info("✓ Fullscreen video started")
        return True

      except Exception as e:
        logger.error(f"Failed to start playback: {e}")
        self._cleanup_processes()
        return False

  def _cleanup_processes(self):
    for proc_tuple in self.player_processes:
      try:
        proc = proc_tuple[0] if isinstance(proc_tuple, tuple) else proc_tuple
        if proc.poll() is None:
          proc.terminate()
      except Exception:
        pass
    self.player_processes = []

  def _monitor_playback(self):
    try:
      for proc_tuple in self.player_processes:
        try:
          proc = proc_tuple[0] if isinstance(proc_tuple, tuple) else proc_tuple
          proc.wait()
        except Exception:
          pass
    finally:
      self.is_playing = False
      self._cleanup_processes()
      
      with self.status_lock:
        self.status_playing = False
      
      # Check if there are queued videos
      if self.playlist_queue:
        logger.info(f"Playback ended. Processing next video in queue ({len(self.playlist_queue)} remaining). HardLock stays active.")
        
        # Get next video from queue
        next_video = self.playlist_queue.pop(0)
        video_url, multi_monitor, input_lock, selected_monitors = next_video
        
        logger.info(f"▶ Playing next from playlist: {video_url}")
        time.sleep(0.5)  # Brief pause between videos
        
        # Recursively call play_fullscreen for the next video
        # This will either play it or queue it again if something else is playing
        # DO NOT release HardLock - keep it active throughout playlist
        self.play_fullscreen(video_url, multi_monitor=multi_monitor, input_lock=False, selected_monitors=selected_monitors)
      else:
        # Queue is empty - now release HardLock
        logger.info("Playback ended. Queue empty. HardLock released.")
        self.input_locker.unlock()

  # ---------- HTTP server ----------

  def start_server(self) -> bool:
    try:
      VideoServer.player_instance = self
      server_address = ("127.0.0.1", self.server_port)
      self.server = HTTPServer(server_address, VideoServer)
      threading.Thread(target=self._run_server, daemon=True).start()
      logger.info(f"✓ HTTP server started on http://127.0.0.1:{self.server_port}")
      return True
    except OSError as e:
      logger.error(f"Failed to start server: {e}")
      return False

  def stop_server(self):
    if self.server:
      try:
        self.server.shutdown()
      except Exception as e:
        logger.error(f"Error stopping server: {e}")

  def _run_server(self):
    try:
      self.server.serve_forever()
    except Exception as e:
      logger.error(f"Server error: {e}")
      # Try to restart the server if it crashes
      try:
        self.server.shutdown()
      except:
        pass
      # Restart the server
      time.sleep(2)
      logger.info("Attempting to restart HTTP server...")
      self.start_server()


# ------------------------------------------------------
# HTTP Handler
# ------------------------------------------------------
class VideoServer(BaseHTTPRequestHandler):
  player_instance: FullscreenVideoPlayer | None = None

  def _send_cors(self):
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")

  def log_message(self, *args):
    # Silence default HTTP logging
    return

  def do_OPTIONS(self):
    self.send_response(200)
    self._send_cors()
    self.end_headers()

  def do_GET(self):
    try:
      if self.path == "/health":
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"running"}')
        return

      if self.path == "/status":
        self._handle_status()
        return

      if self.path == "/monitors":
        self._handle_monitors()
        return

      self.send_response(404)
      self._send_cors()
      self.end_headers()
    except ConnectionAbortedError as e:
      # Client abruptly disconnected (extension reload, antivirus, etc.) - normal in some cases
      logger.debug(f"GET {self.path} - connection aborted by client")
    except Exception as e:
      logger.error(f"GET {self.path} error: {e}")
      try:
        self.send_response(500)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"internal"}')
      except:
        pass

  def _handle_status(self):
    player = VideoServer.player_instance
    if not player:
      self.send_response(500)
      self._send_cors()
      self.end_headers()
      return

    with player.status_lock:
      playing = bool(player.status_playing)
      started_at = player.status_started_at
      expected_len = player.status_expected_length_sec

    now = time.time()
    if playing and expected_len is not None:
      position = max(0.0, now - started_at)
      length = max(expected_len, position)
      remaining = max(0.0, length - position)
    else:
      position = None
      length = None
      remaining = None

    payload = {
      "playing": playing,
      "position_sec": position,
      "length_sec": length,
      "remaining_sec": remaining,
    }

    body = json.dumps(payload).encode("utf-8")
    self.send_response(200)
    self._send_cors()
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(body)

  def _handle_monitors(self):
    """Return list of available monitors"""
    player = VideoServer.player_instance
    if not player:
      self.send_response(500)
      self._send_cors()
      self.end_headers()
      return

    monitor_indices = player._get_monitor_indices()
    payload = {
      "monitors": monitor_indices,
      "count": len(monitor_indices)
    }

    body = json.dumps(payload).encode("utf-8")
    self.send_response(200)
    self._send_cors()
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(body)

  def _handle_permanence(self):
    """Handle permanence enable/disable - creates/removes startup shortcut"""
    try:
      length = int(self.headers.get("Content-Length", 0))
      body = self.rfile.read(length)
      data = json.loads(body.decode("utf-8") or "{}")

      enable = bool(data.get("enable", False))

      if enable:
        success = self._create_startup_shortcut()
        msg = "Permanence enabled - startup shortcut created"
      else:
        success = self._remove_startup_shortcut()
        msg = "Permanence disabled - startup shortcut removed"

      if success:
        logger.info(msg)
        self.send_response(200)
      else:
        logger.error(f"Failed to {'enable' if enable else 'disable'} permanence")
        self.send_response(500)

      self._send_cors()
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(json.dumps({"success": success, "message": msg}).encode("utf-8"))

    except Exception as e:
      logger.error(f"Permanence handler error: {e}")
      self.send_response(500)
      self._send_cors()
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(b'{"success":false,"error":"internal"}')

  def _create_startup_shortcut(self):
    """Create Windows startup folder shortcut for bambi_player (hidden with pythonw)"""
    try:
      # Get Windows startup folder path
      startup_folder = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
      if not os.path.exists(startup_folder):
        logger.error(f"Startup folder not found: {startup_folder}")
        return False

      # Path to this script
      script_path = os.path.abspath(__file__)
      bat_path = os.path.join(startup_folder, "BambiPlayer.bat")

      # Get pythonw.exe path (GUI mode - no console window)
      python_exe = sys.executable.replace("python.exe", "pythonw.exe")
      
      # If pythonw.exe doesn't exist, create it by copying python.exe or use fallback
      python_dir = os.path.dirname(sys.executable)
      pythonw_exe = os.path.join(python_dir, "pythonw.exe")
      
      if not os.path.exists(pythonw_exe):
        logger.warning(f"pythonw.exe not found at {pythonw_exe}, using python.exe with START /B")
        python_exe = sys.executable
      else:
        logger.info(f"Using pythonw.exe for hidden startup")

      # Create batch file with START /B to hide window
      bat_content = f'''@echo off
cd /d "{os.path.dirname(script_path)}"
START /B "" "{python_exe}" "{script_path}" --no-tray
exit
'''

      with open(bat_path, 'w') as f:
        f.write(bat_content)

      logger.info(f"✓ Startup shortcut created at: {bat_path} (hidden background process)")
      return True

    except Exception as e:
      logger.error(f"Failed to create startup shortcut: {e}")
      return False

  def _remove_startup_shortcut(self):
    """Remove Windows startup folder shortcut for bambi_player"""
    try:
      startup_folder = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
      bat_path = os.path.join(startup_folder, "BambiPlayer.bat")
      vbs_path = os.path.join(startup_folder, "BambiPlayer.vbs")

      removed = False
      
      # Try to remove batch file (new version)
      if os.path.exists(bat_path):
        os.remove(bat_path)
        logger.info(f"✓ Startup shortcut removed: {bat_path}")
        removed = True

      # Also try to remove old VBScript if it exists
      if os.path.exists(vbs_path):
        os.remove(vbs_path)
        logger.info(f"✓ Old VBScript startup file removed: {vbs_path}")
        removed = True

      if not removed:
        logger.warning(f"Startup shortcut not found at: {bat_path}")
        return True  # Return true even if file doesn't exist (already removed)

      return True

    except Exception as e:
      logger.error(f"Failed to remove startup shortcut: {e}")
      return False

  def do_POST(self):
    if self.path == "/permanence":
      self._handle_permanence()
      return
    
    if self.path != "/play":
      self.send_response(404)
      self._send_cors()
      self.end_headers()
      return

    player = VideoServer.player_instance
    if not player:
      self.send_response(500)
      self._send_cors()
      self.end_headers()
      return

    try:
      length = int(self.headers.get("Content-Length", 0))
      body = self.rfile.read(length)
      data = json.loads(body.decode("utf-8") or "{}")

      video_url = data.get("url") or data.get("videoUrl")
      multi_monitor = bool(data.get("multi_monitor", False))
      input_lock = bool(data.get("input_lock", False))
      selected_monitors = data.get("selected_monitors", None)

      if not video_url:
        self.send_response(400)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"no url"}')
        return

      ok = player.play_fullscreen(video_url, multi_monitor=multi_monitor, input_lock=input_lock, selected_monitors=selected_monitors)

      self.send_response(200)
      self._send_cors()
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      if ok:
        self.wfile.write(b'{"status":"playing"}')
      else:
        self.wfile.write(b'{"status":"already_playing"}')

    except ConnectionAbortedError as e:
      # Client abruptly disconnected - normal in some cases
      logger.debug(f"POST /play - connection aborted by client")
    except Exception as e:
      logger.error(f"POST /play error: {e}")
      try:
        self.send_response(500)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"internal"}')
      except:
        pass


# ------------------------------------------------------
# Tray icon
# ------------------------------------------------------
def quit_app(icon, _item):
  logger.info("Quitting BambiPlayer...")
  icon.stop()
  os._exit(0)


def run_tray_icon():
  icon_path = os.path.join(BASE_DIR, "icon.png")
  if not os.path.exists(icon_path):
    img = Image.new("RGB", (64, 64), color="black")
  else:
    img = Image.open(icon_path)

  menu = (item("Quit Bambi Player", quit_app),)
  icon = pystray.Icon("bambi_player", img, "Bambi Player", menu)
  icon.run()


# ------------------------------------------------------
# Main
# ------------------------------------------------------
def main():
  import argparse

  parser = argparse.ArgumentParser(description="BambiPlayer")
  parser.add_argument("--port", type=int, default=5655)
  parser.add_argument("--no-tray", action="store_true", help="Disable tray icon")
  args = parser.parse_args()

  try:
    player = FullscreenVideoPlayer(server_port=args.port)
  except Exception as e:
    logger.error(str(e))
    sys.exit(1)

  logger.info("======================================================================")
  logger.info("BambiPlayer - Fullscreen VLC + HardLock + Tray Icon")
  logger.info("======================================================================")

  if not player.start_server():
    sys.exit(1)

  if not args.no_tray:
    threading.Thread(target=run_tray_icon, daemon=False).start()
  else:
    logger.info("Tray icon disabled via --no-tray flag")

  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    logger.info("Shutting down...")
    player.stop_server()


if __name__ == "__main__":
  main()
