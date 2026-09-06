"""HardLock - keyboard and mouse input blocking, dispatched by platform."""

import sys
import logging

logger = logging.getLogger("BambiBrowser.HardLock")


class HardLock:
    """Facade that picks a platform-specific HardLock implementation."""

    def __init__(self):
        if sys.platform == "win32":
            from core.windows.hard_lock_windows import WindowsHardLock
            self._impl = WindowsHardLock()
        else:
            from core.linux.hard_lock_linux import LinuxHardLock
            self._impl = LinuxHardLock()

    @property
    def is_locked(self) -> bool:
        return self._impl.is_locked

    @property
    def keyboard_available(self) -> bool:
        return self._impl.keyboard_available

    @property
    def mouse_available(self) -> bool:
        return self._impl.mouse_available

    def lock(self) -> None:
        self._impl.lock()

    def unlock(self) -> None:
        self._impl.unlock()

    def force_unlock(self) -> None:
        self._impl.force_unlock()

    def get_status(self) -> dict:
        return self._impl.get_status()
