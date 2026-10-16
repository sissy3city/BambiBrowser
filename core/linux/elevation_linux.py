"""Administrator elevation and legacy autostart cleanup - Linux stub.

Linux has no Administrator/UAC concept to mirror: HardLock and the
text-replacement engine rely on evdev/uinput group permissions (see
core/linux/hard_lock_linux.py) rather than process elevation, and there is
no registry to clean up after. These stand in for core.windows.elevation_windows
so core/elevation.py has a Linux-side implementation to dispatch to; fill
them in if a real need (e.g. polkit/pkexec) shows up later.
"""


def is_admin() -> bool:
    """Always False - Linux doesn't have an elevated-admin flag to report."""
    return False


def request_admin_privileges() -> bool:
    """No-op - BambiBrowser never needs to relaunch itself elevated on Linux."""
    return False


def remove_legacy_autostart_registry_entry() -> None:
    """No-op - there is no Windows registry on Linux."""
    pass
