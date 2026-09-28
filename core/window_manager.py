"""Window property manipulation (opacity/click-through/topmost), dispatched by platform."""

import sys


def apply_window_properties(pid: int, opacity: int = 100, click_through: bool = False,
                             class_name: str = "mpv") -> bool:
    """Apply opacity/click-through/topmost to the player window owned by pid.

    Returns True if a matching window was found and updated, False if not
    (caller should retry later - the window may not exist yet, or the
    feature may be unavailable on this platform/session).
    """
    if sys.platform == "win32":
        from core.windows.window_manager_windows import apply_window_properties as impl
    else:
        from core.linux.window_manager_linux import apply_window_properties as impl
    return impl(pid, opacity, click_through, class_name)


def keep_window_topmost(pid: int, class_name: str = "mpv") -> bool:
    """Reassert the player window's topmost state when supported."""
    if sys.platform != "win32":
        return False
    from core.windows.window_manager_windows import keep_window_topmost as impl
    return impl(pid, class_name)
