"""
Linux window manipulation (opacity/click-through/topmost) for the external
mpv process, via XWayland/X11.

This only works if mpv's window ends up as an X11 (or XWayland) surface - a
native Wayland mpv surface cannot be discovered or manipulated by another
client at all, since Wayland's security model deliberately forbids it. If no
matching window can be found, callers should treat this as "feature
unavailable" and keep playback itself working rather than failing.

Uses `xdotool`/`wmctrl` (must be installed - see README) for window discovery
and stacking, and `xprop` for opacity via the _NET_WM_WINDOW_OPACITY EWMH
hint. Click-through uses the X Shape extension via python-xlib, which is the
least certain piece of this module - if python-xlib's shape API doesn't match
what's coded here (it has varied across versions), click-through silently
no-ops rather than raising.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger("BambiBrowser.WindowManager")

AVAILABLE = bool(shutil.which("xdotool")) and bool(shutil.which("wmctrl"))
if not AVAILABLE:
    logger.warning("xdotool/wmctrl not available - opacity/click-through/topmost disabled")


def find_window_by_pid(pid: int, class_name: str = "mpv"):
    """Find an X11 window id owned by pid, falling back to a class-name search."""
    try:
        out = subprocess.run(
            ["xdotool", "search", "--pid", str(pid)],
            capture_output=True, text=True, timeout=2,
        )
        ids = [w for w in out.stdout.split() if w]
        if ids:
            return ids[0]
    except Exception as e:
        logger.debug(f"xdotool search --pid failed: {e}")

    try:
        out = subprocess.run(
            ["xdotool", "search", "--class", class_name],
            capture_output=True, text=True, timeout=2,
        )
        ids = [w for w in out.stdout.split() if w]
        if ids:
            return ids[0]
    except Exception as e:
        logger.debug(f"xdotool search --class failed: {e}")

    return None


def _apply_topmost(window_id: str) -> None:
    subprocess.run(
        ["wmctrl", "-i", "-r", window_id, "-b", "add,above"],
        capture_output=True, timeout=2, check=False,
    )


def _apply_opacity(window_id: str, opacity: int) -> None:
    value = int(opacity * 0xFFFFFFFF / 100)
    subprocess.run(
        ["xprop", "-id", window_id, "-f", "_NET_WM_WINDOW_OPACITY", "32c",
         "-set", "_NET_WM_WINDOW_OPACITY", str(value)],
        capture_output=True, timeout=2, check=False,
    )


def _apply_click_through(window_id: str) -> None:
    """Best-effort: make the window pass mouse input through via the X Shape
    extension's input shape. Requires python-xlib; no-ops if unavailable."""
    try:
        from Xlib import display as xlib_display
        from Xlib.ext import shape

        disp = xlib_display.Display()
        window = disp.create_resource_object("window", int(window_id, 0))
        window.shape_rectangles(shape.SK.Input, shape.SO.Set, 0, 0, [])
        disp.sync()
    except Exception as e:
        logger.debug(f"Click-through (X Shape) unavailable/failed: {e}")


def apply_window_properties(pid: int, opacity: int = 100, click_through: bool = False,
                             class_name: str = "mpv") -> bool:
    """Apply opacity/click-through/topmost to the mpv window owned by pid.

    Returns True if a matching window was found and settings were attempted,
    False if not (caller should retry later, or the session may be pure
    Wayland with no XWayland window to find at all).
    """
    if not AVAILABLE:
        return False

    window_id = find_window_by_pid(pid, class_name)
    if not window_id:
        return False

    try:
        if opacity < 100:
            _apply_opacity(window_id, opacity)
        if click_through:
            _apply_click_through(window_id)
        _apply_topmost(window_id)
        return True
    except Exception as e:
        logger.debug(f"Window properties error: {e}")
        return False
