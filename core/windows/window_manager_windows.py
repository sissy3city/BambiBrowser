"""Windows window manipulation (opacity/click-through/topmost) via win32gui."""

import logging

logger = logging.getLogger("BambiBrowser.WindowManager")

try:
    import win32gui
    import win32con
    import win32process
    AVAILABLE = True
except ImportError:
    AVAILABLE = False
    logger.warning("pywin32 not available - opacity/click-through disabled")


def find_window_by_pid(pid: int, class_name: str = "mpv"):
    """Find a visible top-level window with the given class name owned by pid."""
    if not AVAILABLE:
        return None

    def enum_callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == class_name:
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid == pid:
                windows.append(hwnd)
        return True

    windows = []
    win32gui.EnumWindows(enum_callback, windows)
    return windows[0] if windows else None


def apply_window_properties(pid: int, opacity: int = 100, click_through: bool = False,
                             class_name: str = "mpv") -> bool:
    """Apply opacity/click-through/topmost to the mpv window owned by pid.

    Returns True if a matching window was found and updated, False if not
    (caller should retry later - the window may not exist yet).
    """
    if not AVAILABLE:
        return False
    try:
        hwnd = find_window_by_pid(pid, class_name)
        if not hwnd:
            return False

        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if opacity < 100:
            alpha = int(opacity * 255 / 100)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, alpha, win32con.LWA_ALPHA)
        if click_through:
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                    style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                               win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        return True
    except Exception as e:
        logger.debug(f"Window properties error: {e}")
        return False
