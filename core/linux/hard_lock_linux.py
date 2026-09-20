"""
Linux HardLock implementation.

Uses python-evdev to exclusively grab keyboard/mouse input devices at the
kernel evdev layer. This works under both X11 and native Wayland sessions,
since it operates below the display server entirely - the compositor never
sees events from a grabbed device.

Requires the user to be able to open /dev/input/event* for read/write, which
usually means being a member of the `input` group (`sudo usermod -aG input
$USER`, then log out and back in) or having an appropriate udev rule.
"""

import logging
import threading
import time
from typing import List

logger = logging.getLogger("BambiBrowser.HardLock")

try:
    import evdev
    from evdev import InputDevice, list_devices, ecodes
    _EVDEV_IMPORT_ERROR = None
except Exception as e:  # ImportError, or evdev raising on import in odd environments
    evdev = None
    _EVDEV_IMPORT_ERROR = e


class LinuxHardLock:
    """Atomic input lock - exclusively grabs keyboard/mouse evdev devices."""

    def __init__(self):
        self._locked = False
        self._lock_start_time = 0.0
        self._devices: List["InputDevice"] = []
        self._reader_threads: List[threading.Thread] = []
        self._stop_reading = threading.Event()
        self._permission_error = False

        self._evdev_available = evdev is not None
        if not self._evdev_available:
            logger.warning(f"python-evdev not available: {_EVDEV_IMPORT_ERROR}")

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def keyboard_available(self) -> bool:
        return self._evdev_available

    @property
    def mouse_available(self) -> bool:
        return self._evdev_available

    def _find_input_devices(self) -> List["InputDevice"]:
        """Find keyboard and mouse devices via their evdev capabilities."""
        devices = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot open {path}: {e}")
                self._permission_error = True
                continue

            caps = dev.capabilities()
            has_keys = ecodes.EV_KEY in caps
            if has_keys:
                devices.append(dev)
            else:
                dev.close()
        return devices

    def lock(self) -> None:
        """Grab all keyboard/mouse devices exclusively - NO ESCAPE."""
        if self._locked:
            return

        if not self._evdev_available:
            logger.error("Cannot lock: python-evdev is not installed")
            return

        self._locked = True
        self._lock_start_time = time.time()
        self._stop_reading.clear()
        logger.info("HardLock ENABLED - grabbing input devices")

        self._devices = self._find_input_devices()
        if not self._devices and self._permission_error:
            logger.error(
                "HardLock: no input devices could be opened - permission denied. "
                "Add yourself to the 'input' group (sudo usermod -aG input $USER) "
                "and log out/in, or install a udev rule granting access."
            )

        grabbed = []
        for dev in self._devices:
            try:
                dev.grab()
                grabbed.append(dev)
            except (OSError, IOError) as e:
                logger.warning(f"Failed to grab {dev.path}: {e}")

        self._devices = grabbed
        logger.info(f"HardLock: {len(self._devices)} device(s) grabbed")

        for dev in self._devices:
            t = threading.Thread(target=self._drain_device, args=(dev,), daemon=True)
            t.start()
            self._reader_threads.append(t)

    def _drain_device(self, dev: "InputDevice") -> None:
        """Continuously read (and discard) events from a grabbed device so the
        kernel's per-device event queue doesn't fill up while input is locked."""
        try:
            while not self._stop_reading.is_set():
                if dev.read_one() is None:
                    time.sleep(0.01)
        except (OSError, IOError):
            pass

    def unlock(self) -> None:
        """Release all grabbed devices."""
        if not self._locked:
            return
        logger.info("Releasing HardLock...")

        self._stop_reading.set()
        for t in self._reader_threads:
            t.join(timeout=1.0)
        self._reader_threads.clear()

        for dev in self._devices:
            try:
                dev.ungrab()
            except (OSError, IOError):
                pass
            try:
                dev.close()
            except Exception:
                pass
        self._devices.clear()

        self._locked = False
        logger.info("HardLock released - system input restored")

    def force_unlock(self) -> None:
        logger.warning("Emergency unlock triggered")
        self.unlock()

    def get_status(self) -> dict:
        return {
            "locked": self._locked,
            "evdev_available": self._evdev_available,
            "grabbed_device_count": len(self._devices),
            "permission_error": self._permission_error,
            "keyboard_available": self.keyboard_available,
            "mouse_available": self.mouse_available,
            "lock_duration": time.time() - self._lock_start_time if self._locked else 0,
        }
