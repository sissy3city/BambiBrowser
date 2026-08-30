"""
Linux Bambi Gag engine.

Unlike text replacement (which can correct a word after it's typed but
before the next boundary key), gagging has to intercept the Enter key
*before* Discord ever sees it - by the time Enter reaches Discord the
message is already sent, too late to rewrite. That requires an exclusive
evdev grab of the keyboard (like HardLock) plus full keyboard passthrough
via a virtual uinput device, so the system stays fully usable while we
selectively intercept just the Enter key.

Sequence when Enter is pressed while gag is enabled and Discord is focused:
1. Suppress the real Enter (don't forward it).
2. Inject Ctrl+A, Ctrl+C to select and copy the typed message.
3. Read the clipboard via Qt (this class is a QObject living on the main
   thread, so QApplication.clipboard() access here is safe).
4. Transform the text into gag syllables and write it back to the clipboard.
5. Inject Ctrl+A, Ctrl+V to replace the message, then a real Enter to submit.

This is a from-scratch v1, not a port of the AutoHotkey version, and has a
smaller reliability envelope - particularly around focus detection under a
pure Wayland session with no XWayland (see _get_focused_window_class).
"""

import logging
import random
import subprocess
import shutil
from typing import Optional

from PyQt6.QtCore import QObject, QSocketNotifier, QTimer, pyqtSignal, QThread
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger("BambiBrowser.LinuxGagEngine")

try:
    import evdev
    from evdev import InputDevice, list_devices, ecodes
    _EVDEV_AVAILABLE = True
    _EVDEV_IMPORT_ERROR = None
except Exception as e:
    _EVDEV_AVAILABLE = False
    _EVDEV_IMPORT_ERROR = e

try:
    from core.linux._uinput_compat import ensure_distutils_sysconfig_shim
    ensure_distutils_sysconfig_shim()
    import uinput
    _UINPUT_AVAILABLE = True
    _UINPUT_IMPORT_ERROR = None
except Exception as e:
    _UINPUT_AVAILABLE = False
    _UINPUT_IMPORT_ERROR = e

_GAG_SYLLABLES = ["mph", "mmph", "mh", "ph", "mmf", "hmmph"]
_XDOTOOL_AVAILABLE = bool(shutil.which("xdotool"))


def _all_key_capabilities():
    """Every KEY_* the running evdev/uinput both know about - full passthrough."""
    caps = []
    for name in dir(ecodes):
        if name.startswith("KEY_"):
            u = getattr(uinput, name, None)
            if u is not None:
                caps.append(u)
    return tuple(caps)


def _gag_transform(text: str) -> str:
    out = []
    for c in text:
        if c.isalpha():
            out.append(random.choice(_GAG_SYLLABLES))
        else:
            out.append(c)
    return "".join(out)


def _get_focused_window_class() -> Optional[str]:
    """Best-effort focused-window class lookup (X11/XWayland via xdotool,
    with a KDE/KWin D-Bus fallback for pure-Wayland sessions)."""
    if _XDOTOOL_AVAILABLE:
        try:
            out = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowclassname"],
                capture_output=True, text=True, timeout=1,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except Exception as e:
            logger.debug(f"xdotool focus check failed: {e}")

    # KWin D-Bus fallback - best-effort, KWin's scripting API varies by version.
    try:
        out = subprocess.run(
            ["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.activeWindow"],
            capture_output=True, text=True, timeout=1,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception as e:
        logger.debug(f"KWin D-Bus focus check failed: {e}")

    return None


class _RemoteTogglePoller(QThread):
    """Polls a remote URL for ON/OFF text every 5s, mirroring the AHK version's
    notepad.cc-style <pre> tag extraction."""

    state_changed = pyqtSignal(bool)

    def __init__(self, url: str):
        super().__init__()
        self._url = url
        self._stop = False

    def stop(self):
        self._stop = True
        self.wait(1000)

    def run(self):
        import urllib.request
        import re as _re
        while not self._stop:
            try:
                with urllib.request.urlopen(self._url, timeout=5) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                pre_match = _re.search(r"<pre[^>]*>(.*?)</pre>", raw, _re.S)
                content = pre_match.group(1) if pre_match else raw
                content = _re.sub(r"<[^>]*>", "", content)
                content = _re.sub(r"[\r\n\t ]", "", content)
                if content == "ON":
                    self.state_changed.emit(True)
                elif content == "OFF":
                    self.state_changed.emit(False)
            except Exception as e:
                logger.debug(f"Remote gag toggle check failed: {e}")
            self.msleep(5000)


class LinuxGagEngine(QObject):
    """Drop-in engine for GagManager, Linux-native (evdev grab + uinput passthrough)."""

    status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._devices = []
        self._notifiers = []
        self._uinput_device = None
        self._gag_active = False
        self._poller: Optional[_RemoteTogglePoller] = None
        self._ctrl_down = False
        self._gag_sequence_active = False

        self._available = _EVDEV_AVAILABLE and _UINPUT_AVAILABLE
        if not _EVDEV_AVAILABLE:
            logger.warning(f"python-evdev not available: {_EVDEV_IMPORT_ERROR}")
        if not _UINPUT_AVAILABLE:
            logger.warning(f"python-uinput not available: {_UINPUT_IMPORT_ERROR}")

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_state(self) -> bool:
        return self._gag_active

    def start(self, settings) -> bool:
        if not self._available:
            self.error_occurred.emit("evdev/uinput not available for Bambi Gag")
            return False
        self.stop()

        remote_url = (settings.remote_url or "").strip()
        if remote_url:
            self._poller = _RemoteTogglePoller(remote_url)
            self._poller.state_changed.connect(self._set_gag_state)
            self._poller.start()
        else:
            self._gag_active = bool(getattr(settings, "local_toggle", False))
            self.status_changed.emit(self._gag_active)

        try:
            self._devices = self._find_keyboards()
        except Exception as e:
            self.error_occurred.emit(f"Failed to open keyboard devices: {e}")
            return False
        if not self._devices:
            self.error_occurred.emit(
                "No keyboard devices could be grabbed - check 'input' group membership"
            )
            return False

        try:
            self._uinput_device = uinput.Device(_all_key_capabilities())
        except Exception as e:
            self.error_occurred.emit(f"Failed to create uinput passthrough device: {e}")
            self._release_devices()
            return False

        for dev in self._devices:
            try:
                dev.grab()
            except (OSError, IOError) as e:
                logger.warning(f"Failed to grab {dev.path}: {e}")
                continue
            notifier = QSocketNotifier(dev.fd, QSocketNotifier.Type.Read, self)
            notifier.activated.connect(lambda _, d=dev: self._on_device_readable(d))
            self._notifiers.append(notifier)

        self._running = True
        logger.info("Bambi Gag (Linux) started")
        return True

    def stop(self) -> None:
        for notifier in self._notifiers:
            notifier.setEnabled(False)
        self._notifiers.clear()

        self._release_devices()

        if self._uinput_device:
            try:
                self._uinput_device.destroy()
            except Exception:
                pass
            self._uinput_device = None

        if self._poller:
            self._poller.stop()
            self._poller = None

        self._running = False

    def _release_devices(self):
        for dev in self._devices:
            try:
                dev.ungrab()
            except Exception:
                pass
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []

    def reload(self, settings) -> bool:
        return self.start(settings)

    def _set_gag_state(self, enabled: bool):
        if enabled != self._gag_active:
            self._gag_active = enabled
            self.status_changed.emit(enabled)

    def _find_keyboards(self):
        devices = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except (PermissionError, OSError):
                continue
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                devices.append(dev)
            else:
                dev.close()
        return devices

    def _on_device_readable(self, dev):
        try:
            for event in dev.read():
                self._handle_event(event)
        except (OSError, IOError):
            pass

    def _handle_event(self, event):
        if event.type != ecodes.EV_KEY:
            self._forward(event.type, event.code, event.value)
            return

        if event.code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
            self._ctrl_down = event.value != 0
            self._forward(event.type, event.code, event.value)
            return

        is_enter = event.code in (ecodes.KEY_ENTER, getattr(ecodes, "KEY_KPENTER", -1))
        if is_enter and event.value == 1 and self._gag_active and not self._gag_sequence_active:
            focused = _get_focused_window_class()
            if focused and "discord" in focused.lower():
                self._gag_sequence_active = True
                self._do_gag_sequence()
                return  # suppress the real Enter - the sequence sends its own

        self._forward(event.type, event.code, event.value)

    def _forward(self, ev_type: int, code: int, value: int):
        if self._uinput_device is None:
            return
        try:
            self._uinput_device.emit((ev_type, code), value)
        except Exception as e:
            logger.debug(f"Forward failed for ({ev_type}, {code}): {e}")

    def _tap(self, key):
        self._uinput_device.emit_click(key)

    def _do_gag_sequence(self):
        """
        Runs as a chain of QTimer.singleShot steps rather than a single
        blocking function. This has to stay non-blocking: it runs on the
        Qt main thread (from the QSocketNotifier callback), and both
        establishing X11 clipboard ownership (QClipboard.setText) and
        forwarding every other grabbed keystroke depend on that same event
        loop actually getting to spin between steps. A blocking time.sleep()
        here previously froze the whole loop, which both broke the clipboard
        handoff ("Cannot set X11 selection owner") and stalled all other
        keyboard input for the duration.
        """
        try:
            # Select all + copy the typed message.
            self._uinput_device.emit(uinput.KEY_LEFTCTRL, 1, syn=False)
            self._tap(uinput.KEY_A)
            self._tap(uinput.KEY_C)
            self._uinput_device.emit(uinput.KEY_LEFTCTRL, 0)
            QTimer.singleShot(120, self._gag_step_transform)  # let the target app populate the clipboard
        except Exception as e:
            logger.error(f"Gag sequence (copy) failed: {e}")
            self._gag_sequence_active = False

    def _gag_step_transform(self):
        try:
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            gagged = _gag_transform(text) if text else ""
            clipboard.setText(gagged)
            QTimer.singleShot(30, self._gag_step_paste)
        except Exception as e:
            logger.error(f"Gag sequence (clipboard transform) failed: {e}")
            self._gag_sequence_active = False

    def _gag_step_paste(self):
        try:
            self._uinput_device.emit(uinput.KEY_LEFTCTRL, 1, syn=False)
            self._tap(uinput.KEY_A)
            self._tap(uinput.KEY_V)
            self._uinput_device.emit(uinput.KEY_LEFTCTRL, 0)
            QTimer.singleShot(120, self._gag_step_submit)
        except Exception as e:
            logger.error(f"Gag sequence (paste) failed: {e}")
            self._gag_sequence_active = False

    def _gag_step_submit(self):
        try:
            self._tap(uinput.KEY_ENTER)
        except Exception as e:
            logger.error(f"Gag sequence (submit) failed: {e}")
        finally:
            self._gag_sequence_active = False
