"""
Linux keyboard-layout translation for text-replacer keystroke observation.

evdev reports raw physical keycodes (KEY_Y, KEY_Z, ...), not the character
the desktop's configured keymap actually produces - that translation
normally happens inside the compositor's XKB stack, which the text replacer
deliberately bypasses (it reads devices directly, non-exclusive, so normal
typing keeps flowing to the desktop). Without this, keystroke matching
silently assumed a US QWERTY layout - wrong on German QWERTZ, French
AZERTY, or anything else non-US.

This module compiles the user's actual XKB keymap via libxkbcommon
(`xkbcommon` PyPI package - cffi bindings) and drives a live xkb_state from
observed key events, so `KeycodeTranslator.key_event()` returns whatever
character that keymap would actually produce for the current modifier
state - correct for whichever layout, variant, and options the user has
configured, with no per-language table to hand-maintain.
"""

import logging
import shutil
import subprocess
from typing import Dict, Optional

logger = logging.getLogger("BambiBrowser.LinuxKeymap")

try:
    from xkbcommon import xkb
    _XKBCOMMON_AVAILABLE = True
    _XKBCOMMON_IMPORT_ERROR = None
except Exception as e:  # ImportError, or the cffi binding failing to load libxkbcommon
    xkb = None
    _XKBCOMMON_AVAILABLE = False
    _XKBCOMMON_IMPORT_ERROR = e

# XKB keycodes are evdev keycodes offset by 8 - a legacy holdover from X11,
# which reserved the first 8 keycodes and never renumbered when XKB adopted
# the same numbering space.
_EVDEV_TO_XKB_OFFSET = 8


def is_available() -> bool:
    return _XKBCOMMON_AVAILABLE


def import_error() -> Optional[Exception]:
    return _XKBCOMMON_IMPORT_ERROR


def detect_rmlvo() -> Dict[str, Optional[str]]:
    """Best-effort detection of the active keyboard layout via
    `setxkbmap -query` against XWayland. Compositors (KDE/KWin included)
    configure XWayland's keymap to mirror the compositor's own layout
    specifically for legacy X11 app compatibility, so this reflects the
    real active layout - including runtime layout switches - without
    needing a desktop-specific API.

    Returns a dict of Nones (letting xkbcommon fall back to its own
    compiled-in default, effectively "us") if detection isn't possible -
    logged, not fatal, matching this codebase's usual degrade-gracefully
    pattern for XWayland-dependent features.
    """
    empty = {"rules": None, "model": None, "layout": None, "variant": None, "options": None}
    if not shutil.which("setxkbmap"):
        logger.warning("setxkbmap not found - can't detect keyboard layout, defaulting to US")
        return empty

    try:
        out = subprocess.run(
            ["setxkbmap", "-query"], capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            logger.warning(f"setxkbmap -query failed ({out.returncode}): {out.stderr.strip()}")
            return empty

        raw: Dict[str, str] = {}
        for line in out.stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            raw[key.strip()] = value.strip()

        result = {name: (raw.get(name) or None) for name in empty}
        logger.info(f"Detected keyboard layout: {result}")
        return result
    except Exception as e:
        logger.warning(f"Keyboard layout detection failed, defaulting to US: {e}")
        return empty


class KeycodeTranslator:
    """Tracks a live xkb_state from observed evdev key events and translates
    keycodes to characters through the user's actual keymap.

    Feed *every* observed key event through `key_event()` - modifier keys
    (Shift, AltGr, Caps Lock, ...) included, even though the caller usually
    only cares about the characters regular keys produce - so the
    underlying modifier state stays correct for whatever key comes next.
    Only real press/release transitions should be fed in; skip kernel
    autorepeat events (evdev event.value == 2) entirely, since xkb_state's
    press/release tracking isn't designed to receive a second "down" without
    an intervening "up".
    """

    def __init__(self, rmlvo: Optional[Dict[str, Optional[str]]] = None):
        if not _XKBCOMMON_AVAILABLE:
            raise RuntimeError(f"xkbcommon not available: {_XKBCOMMON_IMPORT_ERROR}")
        rmlvo = rmlvo or {}

        self._context = xkb.Context()
        try:
            self._keymap = self._context.keymap_new_from_names(
                rules=rmlvo.get("rules"),
                model=rmlvo.get("model"),
                layout=rmlvo.get("layout"),
                variant=rmlvo.get("variant"),
                options=rmlvo.get("options"),
            )
        except Exception as e:
            logger.warning(f"Failed to compile detected keymap {rmlvo}, falling back to default: {e}")
            self._keymap = self._context.keymap_new_from_names()
        self._state = self._keymap.state_new()

    def key_event(self, evdev_keycode: int, down: bool) -> Optional[str]:
        """Process one real key press/release (not autorepeat). Returns the
        character a press produces, or None on release, on keys that
        produce no text (modifiers, function/arrow keys, a dead-key press
        awaiting its next key, ...), or if translation fails."""
        xkb_keycode = evdev_keycode + _EVDEV_TO_XKB_OFFSET
        char = None
        if down:
            try:
                # Read with the modifier state as it stood *before* this
                # key's own update below - correct for regular keys, and
                # harmless for modifier keys (which produce no text of
                # their own either way).
                char = self._state.key_get_string(xkb_keycode) or None
            except Exception as e:
                logger.debug(f"key_get_string failed for keycode {xkb_keycode}: {e}")
                char = None
        try:
            self._state.update_key(xkb_keycode, xkb.XKB_KEY_DOWN if down else xkb.XKB_KEY_UP)
        except Exception as e:
            logger.debug(f"update_key failed for keycode {xkb_keycode}: {e}")
        return char
