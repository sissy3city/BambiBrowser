"""Bambi ScreenLock - Linux stub.

core.windows.screenlock_windows keeps the desktop wallpaper and the
Windows lock screen in sync via a scheduled task + PowerShell helper and
lock-screen policy registry keys - all Windows-only concepts. Linux has
no single equivalent (lock screen behavior is up to the desktop
environment/display manager - GDM, SDDM, swaylock, etc.), so this stands
in as an always-unsupported Linux-side implementation for core.screenlock
to dispatch to until a real per-DE implementation is written.
"""


def is_supported() -> bool:
    """Always False - Bambi ScreenLock has no Linux implementation yet."""
    return False


def is_admin() -> bool:
    return False


def is_enabled() -> bool:
    return False


def enable() -> tuple[bool, str]:
    return False, "Bambi ScreenLock is only available on Windows."


def disable() -> tuple[bool, str]:
    return False, "Bambi ScreenLock is only available on Windows."
