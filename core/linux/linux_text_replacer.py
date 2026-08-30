"""
Linux OS-level text replacement engine.

This is a from-scratch v1, not a port of the Windows AutoHotkey hotstring
engine - AutoHotkey doesn't run natively on Linux. Instead of AHK's hotstring
mechanism, this:

1. Opens keyboard evdev devices in *non-exclusive* read mode (no grab), so
   keystrokes keep flowing to the desktop normally while we also observe them.
2. Tracks a rolling per-word buffer of typed characters.
3. On a word-boundary key (space/enter/tab/punctuation), checks the just
   completed word against the configured rules.
4. On a match, injects backspaces to erase the typed word (via a virtual
   uinput keyboard device), then delivers the replacement text as a single
   clipboard paste (Ctrl+V) rather than typing it character by character -
   Chromium/Electron apps (Discord, browsers) route synthetic keystrokes
   through a much heavier IPC pipeline than a native app and can drop
   characters (especially spaces) from a rapid keystroke sequence, whereas a
   single paste arrives as one atomic unit. The clipboard is simply left
   holding the replacement text afterward (like any normal copy would) -
   there's no save/restore of what was on it before.

This has a smaller reliability envelope than AHK's hotstrings - it can lag
or occasionally desync if keystrokes arrive faster than they're processed,
or in applications with unusual text-input handling. It requires the user to
be able to open /dev/input/event* and /dev/uinput (member of the `input`
group, or an appropriate udev rule).
"""

import logging
import threading
import time
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger("BambiBrowser.LinuxTextReplacer")

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

from core.linux import linux_keymap

_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_PUNCT_NAMES = {
    ".": "DOT", ",": "COMMA", "-": "MINUS", ";": "SEMICOLON",
    "/": "SLASH", "'": "APOSTROPHE",
}
_BOUNDARY_CHARS = " \n\t.,;!?"


def _build_uinput_capabilities():
    """Every key we might need to emit for injection."""
    caps = [uinput.KEY_BACKSPACE, uinput.KEY_LEFTSHIFT, uinput.KEY_LEFTCTRL,
            uinput.KEY_SPACE, uinput.KEY_ENTER, uinput.KEY_TAB]
    for c in _LETTERS:
        caps.append(getattr(uinput, f"KEY_{c.upper()}"))
    for d in "1234567890":
        caps.append(getattr(uinput, f"KEY_{d}"))
    for name in _PUNCT_NAMES.values():
        key = getattr(uinput, f"KEY_{name}", None)
        if key is not None:
            caps.append(key)
    return tuple(caps)


class LinuxTextReplacerEngine(QObject):
    """Drop-in replacement for AHKManager's interface, Linux-native."""

    # Emitted from the background reader thread, connected with a
    # BlockingQueuedConnection so clipboard access happens safely on the Qt
    # main thread while the emitting thread waits for it to finish.
    _paste_requested = pyqtSignal(str)
    _peek_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._rules: Dict[str, str] = {}
        self._use_prefix = False
        self._prefix_char = ";"
        self._uinput_device = None
        self._devices = []
        self._peek_result = ""
        self._translator = None

        self._paste_requested.connect(
            self._set_clipboard, Qt.ConnectionType.BlockingQueuedConnection
        )
        self._peek_requested.connect(
            self._read_clipboard_now, Qt.ConnectionType.BlockingQueuedConnection
        )

        self._available = _EVDEV_AVAILABLE and _UINPUT_AVAILABLE and linux_keymap.is_available()
        # Mirrors AHKManager._ahk_exe so callers (e.g. TextReplacer.ahk_path,
        # get_status()) can display something meaningful without special-casing.
        self._ahk_exe = "evdev+uinput (Linux)" if self._available else None
        if not _EVDEV_AVAILABLE:
            logger.warning(f"python-evdev not available: {_EVDEV_IMPORT_ERROR}")
        if not _UINPUT_AVAILABLE:
            logger.warning(f"python-uinput not available: {_UINPUT_IMPORT_ERROR}")
        if not linux_keymap.is_available():
            logger.warning(f"xkbcommon not available: {linux_keymap.import_error()}")

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        if not self._available:
            logger.error("Linux text replacer unavailable (missing python-evdev/python-uinput)")
            return False
        self.stop()
        self._rules = {k.lower(): v for k, v in rules.items()}
        self._use_prefix = use_prefix
        self._prefix_char = prefix_char

        try:
            self._devices = self._find_keyboards()
        except Exception as e:
            logger.error(f"Failed to open keyboard devices: {e}")
            return False
        if not self._devices:
            logger.error(
                "No keyboard devices could be opened - add yourself to the 'input' "
                "group (sudo usermod -aG input $USER) and log out/in."
            )
            return False

        try:
            self._uinput_device = uinput.Device(_build_uinput_capabilities())
        except Exception as e:
            logger.error(f"Failed to create uinput device (check /dev/uinput permissions): {e}")
            for dev in self._devices:
                dev.close()
            self._devices = []
            return False

        try:
            rmlvo = linux_keymap.detect_rmlvo()
            self._translator = linux_keymap.KeycodeTranslator(rmlvo)
        except Exception as e:
            logger.error(f"Failed to set up keyboard layout translation: {e}")
            for dev in self._devices:
                dev.close()
            self._devices = []
            self._uinput_device.destroy()
            self._uinput_device = None
            return False

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Linux text replacer started with {len(self._rules)} rules")
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []
        if self._uinput_device:
            try:
                self._uinput_device.destroy()
            except Exception:
                pass
            self._uinput_device = None
        self._translator = None
        self._running = False

    def reload(self, rules: Dict[str, str], use_prefix: bool = False, prefix_char: str = ";") -> bool:
        return self.start(rules, use_prefix, prefix_char)

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

    def _run(self):
        import selectors
        buffer = ""

        sel = selectors.DefaultSelector()
        for dev in self._devices:
            sel.register(dev, selectors.EVENT_READ)

        try:
            while not self._stop_event.is_set():
                for key, _ in sel.select(timeout=0.2):
                    dev = key.fileobj
                    try:
                        for event in dev.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            if event.value not in (0, 1):
                                # Ignore kernel autorepeat (value == 2) - the
                                # translator's xkb_state tracks real
                                # press/release transitions only, and our
                                # buffer logic doesn't want held keys
                                # spamming replacements either.
                                continue
                            keycode = event.code
                            down = event.value == 1

                            # Feed every key through the translator - even
                            # ones we handle specially below - so its live
                            # xkb_state (shift/altgr/capslock/...) stays
                            # correct for whatever key comes next.
                            char = self._translator.key_event(keycode, down)

                            if not down:
                                continue

                            if keycode == ecodes.KEY_BACKSPACE:
                                buffer = buffer[:-1]
                                continue

                            # Space/Enter/Tab are handled by physical key
                            # regardless of layout - they're boundaries
                            # everywhere, and hardcoding them here sidesteps
                            # any ambiguity in what a translated keymap
                            # would produce for them (e.g. CR vs LF).
                            if keycode == ecodes.KEY_SPACE:
                                self._check_and_replace(buffer, " ")
                                buffer = ""
                                continue
                            if keycode in (ecodes.KEY_ENTER, getattr(ecodes, "KEY_KPENTER", -1)):
                                self._check_and_replace(buffer, "\n")
                                buffer = ""
                                continue
                            if keycode == ecodes.KEY_TAB:
                                self._check_and_replace(buffer, "\t")
                                buffer = ""
                                continue

                            if char is None:
                                # Non-text key (modifier, arrow, function
                                # key, dead-key press awaiting its next key,
                                # etc.) - reset buffer
                                buffer = ""
                                continue

                            if char in _BOUNDARY_CHARS:
                                self._check_and_replace(buffer, char)
                                buffer = ""
                            else:
                                buffer = (buffer + char)[-64:]
                    except (OSError, IOError):
                        pass
        finally:
            sel.close()

    def _check_and_replace(self, word: str, boundary_char: str):
        if not word:
            return
        lookup = word.lower()
        if self._use_prefix:
            if not lookup.startswith(self._prefix_char):
                return
            lookup = lookup[len(self._prefix_char):]

        replacement = self._rules.get(lookup)
        if replacement is None:
            return

        typed_len = len(word) + 1  # + the boundary char itself
        try:
            # Give the target app a moment to finish processing the real
            # keystrokes it just received before we start correcting them -
            # without this, our backspace count can race the app's own
            # (slower) input processing and land wrong.
            time.sleep(0.06)
            self._backspace(typed_len) 
            self._paste(replacement + boundary_char)
            logger.info(f"Replaced '{word}' -> '{replacement}'")
        except Exception as e:
            logger.warning(f"Replacement injection failed: {e}")

    def _backspace(self, count: int):
        for _ in range(count):
            # A real keypress has a hold duration between press and release,
            # which emit_click() skips - and Chromium/Electron apps (Discord,
            # browsers) route input through a much heavier IPC pipeline than
            # a native app, with their own event coalescing, so they also
            # need a small gap between distinct keys, not just a hold.
            self._uinput_device.emit(uinput.KEY_BACKSPACE, 1)
            time.sleep(0.003)
            self._uinput_device.emit(uinput.KEY_BACKSPACE, 0)
            time.sleep(0.005)

    def _paste(self, text: str):
        """Deliver text as a single clipboard paste rather than typing it
        character by character - one atomic unit instead of a keystroke
        sequence that Chromium/Electron's input pipeline can drop parts of.

        Setting the clipboard and reading it back isn't quite enough on its
        own: a clipboard-history manager (e.g. KDE's Klipper) can notice an
        external clipboard change (the user's own manual copy) and grab
        ownership back for itself moments later, silently overwriting what we
        just set before the target app ever reads it. So this doesn't just
        check once - it re-asserts the text and re-checks until it actually
        sticks, and only then sends the paste keystroke."""
        actual = None
        for attempt in range(5):
            self._paste_requested.emit(text)  # blocks until clipboard is set (main thread)
            time.sleep(0.02)  # tiny settle before reading back
            actual = self._peek_clipboard()
            if actual == text:
                if attempt:
                    logger.debug(f"Clipboard confirmed correct on retry {attempt}: {actual!r}")
                break
            logger.warning(
                f"Clipboard mismatch before paste (attempt {attempt + 1}/5) - "
                f"something else grabbed it: wanted={text!r} actual={actual!r}"
            )
        else:
            logger.error(f"Clipboard still wrong after retries, pasting anyway: wanted={text!r} actual={actual!r}")
        self._uinput_device.emit(uinput.KEY_LEFTCTRL, 1, syn=False)
        self._uinput_device.emit(uinput.KEY_V, 1)
        time.sleep(0.003)
        self._uinput_device.emit(uinput.KEY_V, 0)
        self._uinput_device.emit(uinput.KEY_LEFTCTRL, 0)

    def _peek_clipboard(self) -> str:
        """Read the clipboard from the background thread, safely, via the
        same blocking cross-thread pattern used for setting it."""
        self._peek_requested.emit()
        return self._peek_result

    def _read_clipboard_now(self):
        """Runs on the Qt main thread (via BlockingQueuedConnection)."""
        self._peek_result = QApplication.clipboard().text()

    def _set_clipboard(self, text: str):
        """Runs on the Qt main thread (via BlockingQueuedConnection). Just
        sets the clipboard to the replacement text and leaves it there - like
        any normal copy, no save/restore of whatever was on it before."""
        QApplication.clipboard().setText(text)
        logger.debug(f"Clipboard set to: {text!r}")
