"""
Linux setup diagnostics for BambiBrowser.

Checks that Linux-specific dependencies (mpv, python-evdev, python-uinput,
xdotool/wmctrl, pactl/wpctl, 'input' group membership) are present and
working, including a real empirical multi-monitor placement test: it
actually spawns a short-lived mpv window per detected screen and verifies
each one lands where Qt says that screen is. This is the only way to
reliably catch the "mpv opens a native Wayland surface and every window
collapses onto the active monitor" bug class - checking that mpv/xdotool
are merely *installed* wouldn't have caught it.
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("BambiBrowser.Diagnostics")

_STATUS_ORDER = {"pass": 0, "skip": 1, "warn": 2, "fail": 3}
_STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭"}


@dataclass
class DiagnosticResult:
    name: str
    status: str  # "pass", "warn", "fail", "skip"
    detail: str


def _check_binary(name: str, hint: str) -> DiagnosticResult:
    path = shutil.which(name)
    if path:
        return DiagnosticResult(name, "pass", f"found at {path}")
    return DiagnosticResult(name, "fail", f"not found - {hint}")


def check_system_binaries() -> List[DiagnosticResult]:
    if sys.platform == "win32":
        return [DiagnosticResult("system binaries", "skip", "Windows uses bundled mpv/AutoHotkey, not these")]

    results = [
        _check_binary("mpv", "install with: sudo dnf install mpv"),
        _check_binary("ffprobe", "install with: sudo dnf install ffmpeg ffmpeg-libs (needs RPM Fusion)"),
        _check_binary("xdotool", "install with: sudo dnf install xdotool"),
        _check_binary("wmctrl", "install with: sudo dnf install wmctrl"),
    ]
    pactl = shutil.which("pactl")
    wpctl = shutil.which("wpctl")
    if pactl or wpctl:
        results.append(DiagnosticResult("audio (pactl/wpctl)", "pass", f"pactl={pactl or 'missing'}, wpctl={wpctl or 'missing'}"))
    else:
        results.append(DiagnosticResult("audio (pactl/wpctl)", "fail", "neither found - install with: sudo dnf install pipewire-utils"))
    return results


def check_python_modules() -> List[DiagnosticResult]:
    if sys.platform == "win32":
        return [DiagnosticResult("python modules", "skip", "Windows uses pywin32/pycaw, not these")]

    results = []
    try:
        import PyQt6  # noqa: F401
        results.append(DiagnosticResult("PyQt6", "pass", "importable"))
    except Exception as e:
        results.append(DiagnosticResult("PyQt6", "fail", str(e)))

    try:
        import evdev  # noqa: F401
        results.append(DiagnosticResult("python-evdev", "pass", "importable"))
    except Exception as e:
        results.append(DiagnosticResult("python-evdev", "fail", f"{e} - install with: sudo dnf install python3-evdev"))

    try:
        from core.linux._uinput_compat import ensure_distutils_sysconfig_shim
        ensure_distutils_sysconfig_shim()
        import uinput  # noqa: F401
        results.append(DiagnosticResult("python-uinput", "pass", "importable"))
    except Exception as e:
        results.append(DiagnosticResult("python-uinput", "fail", f"{e} - install with: sudo dnf install python3-uinput"))

    try:
        import Xlib  # noqa: F401
        results.append(DiagnosticResult("python-xlib", "pass", "importable"))
    except Exception as e:
        results.append(DiagnosticResult("python-xlib", "warn", f"{e} - only needed for click-through; install with: sudo dnf install python3-xlib"))

    from core.linux import linux_keymap
    if linux_keymap.is_available():
        override = linux_keymap.get_layout_override()
        if override:
            results.append(DiagnosticResult(
                "Keyboard layout (xkbcommon)", "pass",
                f"forced to '{linux_keymap.describe_rmlvo(override)}' via the manual "
                "keyboard check - text replacer will match against this layout"
            ))
        else:
            rmlvo = linux_keymap.detect_rmlvo()
            detected = {k: v for k, v in rmlvo.items() if v}
            if detected:
                results.append(DiagnosticResult("Keyboard layout (xkbcommon)", "pass", f"detected {detected} - text replacer will match against this layout"))
            else:
                results.append(DiagnosticResult("Keyboard layout (xkbcommon)", "warn", "couldn't detect layout via setxkbmap - falling back to US (use the manual keyboard check to force one)"))
    else:
        results.append(DiagnosticResult("Keyboard layout (xkbcommon)", "fail", f"{linux_keymap.import_error()} - install with: pip install xkbcommon"))

    return results


def check_input_permissions() -> List[DiagnosticResult]:
    if sys.platform == "win32":
        return [DiagnosticResult("input permissions", "skip", "not applicable on Windows")]

    results = []
    try:
        import grp
        current_groups = {grp.getgrgid(g).gr_name for g in os.getgroups()}
        if "input" in current_groups:
            results.append(DiagnosticResult("'input' group membership", "pass", "current user is in the input group"))
        else:
            results.append(DiagnosticResult(
                "'input' group membership", "fail",
                "not in 'input' group - run: sudo usermod -aG input $USER (then log out/in)"
            ))
    except Exception as e:
        results.append(DiagnosticResult("'input' group membership", "warn", str(e)))

    uinput_path = "/dev/uinput"
    if os.path.exists(uinput_path):
        if os.access(uinput_path, os.R_OK | os.W_OK):
            results.append(DiagnosticResult("/dev/uinput access", "pass", "readable/writable"))
        else:
            results.append(DiagnosticResult("/dev/uinput access", "fail", "not readable/writable by current user"))
    else:
        results.append(DiagnosticResult("/dev/uinput access", "fail", "device node missing - is the uinput kernel module loaded?"))

    return results


def check_hardlock_grab() -> DiagnosticResult:
    """Non-destructive: enumerate and briefly grab/ungrab one keyboard device
    without actually engaging HardLock."""
    if sys.platform == "win32":
        return DiagnosticResult("HardLock (evdev grab)", "skip", "not applicable on Windows")

    try:
        import evdev
        from evdev import InputDevice, list_devices, ecodes
    except Exception as e:
        return DiagnosticResult("HardLock (evdev grab)", "fail", f"python-evdev unavailable: {e}")

    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except (PermissionError, OSError):
            continue
        caps = dev.capabilities()
        if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
            keyboards.append(dev)
        else:
            dev.close()

    if not keyboards:
        return DiagnosticResult("HardLock (evdev grab)", "fail", "no keyboard devices could be opened")

    ok, err = True, ""
    try:
        keyboards[0].grab()
        keyboards[0].ungrab()
    except Exception as e:
        ok, err = False, str(e)
    finally:
        for dev in keyboards:
            dev.close()

    if ok:
        return DiagnosticResult("HardLock (evdev grab)", "pass", f"{len(keyboards)} keyboard device(s) grabbable")
    return DiagnosticResult("HardLock (evdev grab)", "fail", err)


def _find_window_geometry(title: str) -> Optional[Tuple[int, int, int, int]]:
    try:
        out = subprocess.run(["xdotool", "search", "--name", title], capture_output=True, text=True, timeout=2)
        wid = out.stdout.split()[0] if out.stdout.strip() else None
        if not wid:
            return None
        geo = subprocess.run(["xdotool", "getwindowgeometry", "--shell", wid], capture_output=True, text=True, timeout=2)
        vals = dict(line.split("=", 1) for line in geo.stdout.strip().splitlines() if "=" in line)
        return int(vals["X"]), int(vals["Y"]), int(vals["WIDTH"]), int(vals["HEIGHT"])
    except Exception:
        return None


def check_monitors(settle_seconds: float = 2.5) -> List[DiagnosticResult]:
    """Actually spawns a short-lived mpv window per screen and checks it lands
    where Qt says that screen is - catches the Wayland/XWayland placement bug
    directly rather than just checking that mpv/xdotool are installed."""
    if sys.platform == "win32":
        return [DiagnosticResult("Multi-monitor placement", "skip", "not applicable on Windows")]

    mpv_path = shutil.which("mpv")
    if not mpv_path:
        return [DiagnosticResult("Multi-monitor placement", "skip", "mpv not installed")]

    try:
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        screens = QGuiApplication.screens()
    except Exception as e:
        return [DiagnosticResult("Multi-monitor placement", "fail", f"could not enumerate Qt screens: {e}")]

    if len(screens) < 2:
        return [DiagnosticResult("Multi-monitor placement", "skip", f"only {len(screens)} screen(s) detected - nothing to test")]

    if not shutil.which("xdotool"):
        return [DiagnosticResult("Multi-monitor placement", "skip", "xdotool not installed - can't verify window position")]

    env = os.environ.copy()
    env.pop("WAYLAND_DISPLAY", None)

    title_prefix = "bambi_diag_test"
    procs = []
    results = []
    for i in range(len(screens)):
        cmd = [
            mpv_path, f"--screen={i}", "--no-audio", "--fullscreen", "--idle=yes",
            f"--title={title_prefix}{i}", "av://lavfi:testsrc=size=320x240:rate=2",
        ]
        try:
            procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env))
        except Exception as e:
            results.append(DiagnosticResult(f"Monitor {i} test window", "fail", f"could not launch mpv: {e}"))

    time.sleep(settle_seconds)

    for i, screen in enumerate(screens):
        expected = screen.geometry()
        actual = _find_window_geometry(f"{title_prefix}{i}")
        if actual is None:
            results.append(DiagnosticResult(f"Monitor {i} ({screen.name()})", "fail", "test window not found"))
            continue
        ax, ay, _, _ = actual
        if abs(ax - expected.x()) <= 5 and abs(ay - expected.y()) <= 5:
            results.append(DiagnosticResult(f"Monitor {i} ({screen.name()})", "pass", f"landed at {ax},{ay} as expected"))
        else:
            results.append(DiagnosticResult(
                f"Monitor {i} ({screen.name()})", "fail",
                f"expected ~{expected.x()},{expected.y()}, landed at {ax},{ay} - "
                "mpv is likely opening a native Wayland surface instead of XWayland"
            ))

    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    return results


def check_autostart() -> DiagnosticResult:
    from core.autostart import is_enabled
    enabled = is_enabled()
    return DiagnosticResult("Autostart", "pass", f"{'enabled' if enabled else 'disabled'} (informational only)")


def run_all(include_monitor_test: bool = True) -> List[DiagnosticResult]:
    results: List[DiagnosticResult] = []
    results.extend(check_system_binaries())
    results.extend(check_python_modules())
    results.extend(check_input_permissions())
    results.append(check_hardlock_grab())
    if include_monitor_test:
        results.extend(check_monitors())
    results.append(check_autostart())
    return results


def worst_status(results: List[DiagnosticResult]) -> str:
    worst = "pass"
    for r in results:
        if _STATUS_ORDER[r.status] > _STATUS_ORDER[worst]:
            worst = r.status
    return worst


def format_results(results: List[DiagnosticResult]) -> str:
    lines = [f"{_STATUS_ICON.get(r.status, '?')} {r.name}: {r.detail}" for r in results]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manual checks
#
# run_all() above is fully automatic - it pokes each subsystem once and moves
# on. The helpers below back the "Manual checks" section of the diagnostics
# UI, where one subsystem can be inspected on demand: see what it is currently
# set to, exercise it, and change the setting if it is wrong.
#
# First manual check: audio. AudioTestPlayer opens a small, deliberately
# NOT-fullscreen mpv window playing a test pattern plus a tone or static
# noise, so the output path can be checked by ear. It never touches HardLock,
# the pre-play countdown, or the normal playback pipeline.
# ---------------------------------------------------------------------------


def _find_mpv() -> Optional[str]:
    """Locate mpv the same way core.player does, without importing it (that
    pulls in the whole PyQt playback stack)."""
    base = Path(__file__).parent.parent
    if sys.platform == "win32":
        for cand in (base / "mpv" / "mpv.exe", base / "mpv" / "mpv.com", base / "mpv.exe"):
            if cand.exists():
                return str(cand)
        which = shutil.which("mpv.exe")
        return which or None
    which = shutil.which("mpv")
    return which or None


def _pactl(*args: str) -> Optional[str]:
    """Run `pactl <args>`; return stripped stdout, or None on any failure."""
    if not shutil.which("pactl"):
        return None
    try:
        out = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3)
    except Exception as e:
        logger.debug(f"pactl {args} failed: {e}")
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def list_output_devices() -> List[Tuple[str, str]]:
    """Return [(sink_name, human_description)] for every output device pactl
    knows about. Empty list if pactl is unavailable."""
    listing = _pactl("list", "short", "sinks")
    if not listing:
        return []
    names = [parts[1] for parts in (ln.split("\t") for ln in listing.splitlines()) if len(parts) >= 2]
    descriptions = dict.fromkeys(names, "")
    detail = _pactl("list", "sinks")
    if detail:
        current = None
        for raw in detail.splitlines():
            stripped = raw.strip()
            if stripped.startswith("Name:"):
                current = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Description:") and current in descriptions:
                descriptions[current] = stripped.split(":", 1)[1].strip()
    return [(name, descriptions[name] or name) for name in names]


def get_default_output_device() -> Optional[str]:
    return _pactl("get-default-sink")


def set_default_output_device(name: str) -> Tuple[bool, str]:
    """Point PipeWire/Pulse's default sink at `name`. Only affects streams
    that follow the default - existing streams may need to be moved too, but
    a freshly launched mpv will pick this up."""
    if not shutil.which("pactl"):
        return False, "pactl not available"
    try:
        out = subprocess.run(
            ["pactl", "set-default-sink", name],
            capture_output=True, text=True, timeout=3,
        )
    except Exception as e:
        return False, str(e)
    if out.returncode != 0:
        return False, out.stderr.strip() or "pactl returned non-zero"
    return True, f"default output set to {name}"


def audio_manual_report(configured_volume_0_256: Optional[int] = None) -> List[DiagnosticResult]:
    """Snapshot of the current audio configuration for the manual audio check
    - what mpv will use when it plays, and what the OS mixer is set to."""
    results: List[DiagnosticResult] = []

    mpv = _find_mpv()
    results.append(
        DiagnosticResult("mpv", "pass", f"found at {mpv}") if mpv
        else DiagnosticResult("mpv", "fail", "not found - playback and this test need it")
    )

    if sys.platform == "win32":
        results.append(DiagnosticResult(
            "OS mixer", "skip", "Windows uses the system mixer directly; use the volume test below"
        ))
    else:
        pactl, wpctl = shutil.which("pactl"), shutil.which("wpctl")
        if not (pactl or wpctl):
            results.append(DiagnosticResult(
                "OS mixer (pactl/wpctl)", "fail",
                "neither found - install with: sudo dnf install pipewire-utils"
            ))
        else:
            results.append(DiagnosticResult(
                "OS mixer (pactl/wpctl)", "pass",
                f"pactl={pactl or 'missing'}, wpctl={wpctl or 'missing'}"
            ))
            default = get_default_output_device()
            if default:
                vol = _pactl("get-sink-volume", "@DEFAULT_SINK@") or "unknown"
                muted = _pactl("get-sink-mute", "@DEFAULT_SINK@") or "unknown"
                vol = " ".join(vol.split()) if vol != "unknown" else vol
                status = "warn" if "yes" in muted else "pass"
                results.append(DiagnosticResult(
                    "Default output", status,
                    f"{default}\n    volume: {vol}\n    {muted}"
                ))
                if "yes" in muted:
                    results.append(DiagnosticResult(
                        "Default output mute", "warn",
                        "the default sink is muted - nothing will be audible until it is unmuted"
                    ))

    if configured_volume_0_256 is not None:
        pct = int(round(max(0, min(256, configured_volume_0_256)) / 256 * 100))
        status = "warn" if pct == 0 else "pass"
        results.append(DiagnosticResult(
            "Bambi Player volume", status,
            f"{pct}% ({configured_volume_0_256}/256) - set in the Bambi Player tab"
        ))

    return results


class AudioTestPlayer:
    """A single windowed mpv instance that plays a test card plus a tone or
    static noise so audio output can be verified by ear.

    Deliberately windowed (never --fullscreen) and free of every gag/lock
    hook so it is safe to run from the settings panel at any time. On
    POSIX it also opens an mpv JSON IPC socket, so volume can be nudged
    live; elsewhere a volume change just relaunches."""

    TONE = "tone"
    NOISE = "noise"
    _WINDOW_SIZE = "640x360"
    _WINDOW_TITLE = "BambiBrowser audio check"

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._ipc_path: Optional[str] = None
        self._kind = self.TONE
        self._volume = 70

    # ----- lifecycle -----
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def volume(self) -> int:
        return self._volume

    def start(self, volume_percent: int = 70, kind: str = TONE) -> Tuple[bool, str]:
        """(Re)launch the test player. Safe to call while already running -
        it stops the old instance first."""
        self.stop()

        mpv = _find_mpv()
        if not mpv:
            return False, "mpv not found"

        self._volume = max(0, min(100, int(volume_percent)))
        self._kind = kind if kind in (self.TONE, self.NOISE) else self.TONE

        if self._kind == self.NOISE:
            audio = "anoisesrc=color=pink:amplitude=0.2:sample_rate=48000[out1]"
            what = "static noise"
        else:
            audio = "sine=frequency=440:sample_rate=48000,volume=-12dB[out1]"
            what = "440 Hz tone"
        graph = f"testsrc=size={self._WINDOW_SIZE}:rate=30[out0];{audio}"

        cmd = [
            mpv,
            f"av://lavfi:{graph}",
            "--no-config",
            "--no-fullscreen",
            "--ontop=no",
            f"--geometry={self._WINDOW_SIZE}",
            f"--autofit={self._WINDOW_SIZE}",
            "--force-window=yes",
            "--keep-open=no",
            "--loop-file=inf",
            "--osc=yes",
            "--no-input-default-bindings",
            f"--title={self._WINDOW_TITLE}",
            f"--volume={self._volume}",
            "--really-quiet",
        ]

        self._ipc_path = None
        if sys.platform != "win32":
            self._ipc_path = os.path.join(
                tempfile.gettempdir(), f"bambi-audiocheck-{os.getpid()}.sock"
            )
            try:
                if os.path.exists(self._ipc_path):
                    os.unlink(self._ipc_path)
            except OSError:
                pass
            cmd.append(f"--input-ipc-server={self._ipc_path}")

        env = os.environ.copy()
        if sys.platform != "win32":
            # Same reason as core/player.py: keep mpv on XWayland so window
            # placement/size behave, rather than a native Wayland surface.
            env.pop("WAYLAND_DISPLAY", None)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                env=env,
            )
        except Exception as e:
            self._proc = None
            return False, f"could not launch mpv: {e}"

        logger.info(f"Audio check: mpv started (PID {self._proc.pid}) - {what} at {self._volume}%")
        return True, f"playing {what} at {self._volume}% in a {self._WINDOW_SIZE} window"

    def set_volume(self, volume_percent: int) -> bool:
        """Change the running player's volume live over mpv IPC. Returns True
        if it was applied; False means the caller should relaunch (via start())
        to apply it - e.g. no IPC socket, or nothing playing."""
        volume_percent = max(0, min(100, int(volume_percent)))
        if not self.is_running() or not self._ipc_path:
            return False
        applied = self._ipc_send({"command": ["set_property", "volume", volume_percent]})
        if applied:
            self._volume = volume_percent
        return applied

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        if self._ipc_path:
            try:
                if os.path.exists(self._ipc_path):
                    os.unlink(self._ipc_path)
            except OSError:
                pass
        self._ipc_path = None

    # ----- internals -----
    def _ipc_send(self, payload: dict) -> bool:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                sock.connect(self._ipc_path)
                sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            return True
        except Exception as e:
            logger.debug(f"Audio check IPC send failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Manual check: keyboard layout
#
# The text replacer reads keyboards raw (evdev) and has to translate physical
# keycodes to characters itself. It normally trusts the layout XWayland
# reports; these helpers back the manual check where Pari sees what was
# detected, previews what each key would type, and forces a different layout
# if the detection is wrong. Everything here is Linux-only - Windows text
# replacement is AutoHotkey, which the OS feeds already-translated characters.
# ---------------------------------------------------------------------------


def keyboard_manual_report() -> List[DiagnosticResult]:
    """What the text replacer's keyboard-layout translation is set to right
    now: xkbcommon availability, what was auto-detected, any manual override,
    and whether the layout it will actually use compiles."""
    if sys.platform == "win32":
        return [DiagnosticResult(
            "Keyboard layout", "skip",
            "Windows text replacement uses AutoHotkey - the OS hands it "
            "already-translated characters, so there is no layout to pick here"
        )]

    from core.linux import linux_keymap

    results: List[DiagnosticResult] = []

    if not linux_keymap.is_available():
        results.append(DiagnosticResult(
            "xkbcommon", "fail",
            f"{linux_keymap.import_error()} - install with: pip install xkbcommon"
        ))
        return results
    results.append(DiagnosticResult("xkbcommon", "pass", "importable"))

    setxkbmap = shutil.which("setxkbmap")
    results.append(
        DiagnosticResult("setxkbmap", "pass", f"found at {setxkbmap}") if setxkbmap
        else DiagnosticResult("setxkbmap", "warn",
                              "not found - auto-detection falls back to US; "
                              "install with: sudo dnf install xorg-x11-server-utils")
    )

    detected = linux_keymap.detect_rmlvo()
    shown = {k: v for k, v in detected.items() if v}
    results.append(DiagnosticResult(
        "Auto-detected layout",
        "pass" if shown else "warn",
        f"{linux_keymap.describe_rmlvo(detected)}"
        + (f"  {shown}" if shown else "  (nothing reported - would fall back to US)")
    ))

    override = linux_keymap.get_layout_override()
    if override:
        results.append(DiagnosticResult(
            "Manual override", "pass",
            f"{linux_keymap.describe_rmlvo(override)} - this wins over auto-detection"
        ))
    else:
        results.append(DiagnosticResult(
            "Manual override", "skip", "none set - using auto-detection"
        ))

    effective = linux_keymap.effective_rmlvo()
    ok, reason = linux_keymap.rmlvo_compiles(effective)
    results.append(DiagnosticResult(
        "Layout in use (text replacer)",
        "pass" if ok else "fail",
        f"{linux_keymap.describe_rmlvo(effective)}"
        + ("" if ok else f" - will NOT compile: {reason}")
    ))

    return results


def list_keyboard_layouts() -> List[Tuple[str, str]]:
    """[(code, description)] of installed XKB layouts."""
    if sys.platform == "win32":
        return []
    from core.linux import linux_keymap
    return linux_keymap.list_layouts()


def list_keyboard_variants(layout: str) -> List[Tuple[str, str]]:
    """[(variant_code, description)] for one layout, starting with ('', 'default')."""
    if sys.platform == "win32":
        return [("", "default")]
    from core.linux import linux_keymap
    return linux_keymap.list_variants(layout)


def get_keyboard_layout_override() -> Optional[dict]:
    if sys.platform == "win32":
        return None
    from core.linux import linux_keymap
    return linux_keymap.get_layout_override()


def keyboard_sample_map(layout: Optional[str] = None,
                        variant: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """(key label, unshifted, shifted) for a set of sample keys under the
    given layout, or under the layout currently in use if `layout` is None."""
    if sys.platform == "win32":
        return []
    from core.linux import linux_keymap
    rmlvo = None
    if layout:
        rmlvo = {"rules": None, "model": None, "layout": layout,
                 "variant": variant or None, "options": None}
    return linux_keymap.sample_key_characters(rmlvo)


def set_keyboard_layout_override(layout: str, variant: str = "") -> Tuple[bool, str]:
    """Force the text replacer onto `layout`. Pass an empty layout to clear
    the override and return to auto-detection. Refuses a layout xkbcommon
    can't compile."""
    if sys.platform == "win32":
        return False, "not applicable on Windows"
    from core.linux import linux_keymap

    layout = (layout or "").strip()
    variant = (variant or "").strip()
    if not layout:
        linux_keymap.clear_layout_override()
        return True, "override cleared - back to auto-detection"

    ok, reason = linux_keymap.rmlvo_compiles(
        {"rules": None, "model": None, "layout": layout,
         "variant": variant or None, "options": None}
    )
    if not ok:
        return False, f"'{layout}' won't compile: {reason}"

    linux_keymap.set_layout_override(layout, variant)
    label = layout + (f" ({variant})" if variant else "")
    return True, f"layout forced to {label}"
