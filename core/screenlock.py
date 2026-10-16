"""Bambi ScreenLock - wallpaper-to-lock-screen synchronization, dispatched by platform."""

import sys

if sys.platform == "win32":
    from core.windows.screenlock_windows import (
        is_supported,
        is_admin,
        is_enabled,
        enable,
        disable,
    )
else:
    from core.linux.screenlock_linux import (
        is_supported,
        is_admin,
        is_enabled,
        enable,
        disable,
    )

__all__ = [
    "is_supported",
    "is_admin",
    "is_enabled",
    "enable",
    "disable",
]
