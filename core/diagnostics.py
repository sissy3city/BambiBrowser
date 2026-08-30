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

import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
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
        rmlvo = linux_keymap.detect_rmlvo()
        detected = {k: v for k, v in rmlvo.items() if v}
        if detected:
            results.append(DiagnosticResult("Keyboard layout (xkbcommon)", "pass", f"detected {detected} - text replacer will match against this layout"))
        else:
            results.append(DiagnosticResult("Keyboard layout (xkbcommon)", "warn", "couldn't detect layout via setxkbmap - falling back to US"))
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
