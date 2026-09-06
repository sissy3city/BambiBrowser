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
import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# User override
#
# detect_rmlvo() reflects whatever XWayland/the compositor says is active.
# That is right almost always, but the manual keyboard check lets Pari force
# a specific layout when it isn't - e.g. a pure-Wayland session with no
# XWayland to query, or a keyboard whose physical layout differs from the
# desktop setting. The override lives in QSettings so it survives restarts;
# effective_rmlvo() is what the text replacer actually compiles.
# ---------------------------------------------------------------------------

_OVERRIDE_LAYOUT_KEY = "keyboard/override_layout"
_OVERRIDE_VARIANT_KEY = "keyboard/override_variant"


def get_layout_override() -> Optional[Dict[str, Optional[str]]]:
    """The user-forced layout as an rmlvo dict, or None when auto-detection
    should be used."""
    try:
        from PyQt6.QtCore import QSettings
        s = QSettings("BambiBrowser", "Settings")
        layout = (s.value(_OVERRIDE_LAYOUT_KEY, "", type=str) or "").strip()
        variant = (s.value(_OVERRIDE_VARIANT_KEY, "", type=str) or "").strip()
    except Exception as e:
        logger.debug(f"Could not read keyboard override from settings: {e}")
        return None
    if not layout:
        return None
    return {"rules": None, "model": None, "layout": layout,
            "variant": variant or None, "options": None}


def set_layout_override(layout: str, variant: str = "") -> None:
    """Persist a forced layout. Pass an empty layout to clear the override."""
    from PyQt6.QtCore import QSettings
    s = QSettings("BambiBrowser", "Settings")
    s.setValue(_OVERRIDE_LAYOUT_KEY, (layout or "").strip())
    s.setValue(_OVERRIDE_VARIANT_KEY, (variant or "").strip())
    s.sync()
    logger.info(f"Keyboard layout override set to layout={layout!r} variant={variant!r}"
                if layout else "Keyboard layout override cleared")


def clear_layout_override() -> None:
    set_layout_override("", "")


def effective_rmlvo() -> Dict[str, Optional[str]]:
    """The layout the text replacer will actually use: the user override if
    one is set, otherwise live auto-detection."""
    override = get_layout_override()
    if override:
        logger.info(f"Using keyboard-layout override: "
                    f"{override['layout']}"
                    + (f"({override['variant']})" if override.get('variant') else ""))
        return override
    return detect_rmlvo()


def describe_rmlvo(rmlvo: Optional[Dict[str, Optional[str]]]) -> str:
    """Short human string for an rmlvo dict, e.g. 'de (nodeadkeys)' or
    '(default / US)'."""
    if not rmlvo or not rmlvo.get("layout"):
        return "(default / US)"
    text = rmlvo["layout"]
    if rmlvo.get("variant"):
        text += f" ({rmlvo['variant']})"
    return text


# ---------------------------------------------------------------------------
# Layout enumeration + preview (for the manual keyboard check UI)
# ---------------------------------------------------------------------------

_XKB_RULES_LST_CANDIDATES = (
    "/usr/share/X11/xkb/rules/evdev.lst",
    "/usr/share/X11/xkb/rules/base.lst",
)

# evdev keycodes for a handful of keys whose output differs across the
# common Latin layouts (QWERTY / QWERTZ / AZERTY / Dvorak / UK). Enough to
# eyeball whether a chosen layout matches the physical keyboard.
_SAMPLE_KEYS: Tuple[Tuple[str, int], ...] = (
    ("Q", 16), ("W", 17), ("E", 18), ("R", 19), ("T", 20), ("Y", 21),
    ("A", 30), ("S", 31), ("Z", 44), ("X", 45), ("M", 50),
    ("2", 3), ("3", 4), ("6", 7), ("7", 8),
    ("-", 12), ("=", 13), ("[", 26), (";", 39), ("'", 40), ("/", 53),
)
_EVDEV_LEFTSHIFT = 42


def _read_rules_lst() -> Optional[str]:
    for path in _XKB_RULES_LST_CANDIDATES:
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        except OSError:
            continue
    return None


def _parse_lst_section(text: str, header: str) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("! "):
            in_section = line.strip() == header
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        code, _, desc = stripped.partition(" ")
        entries.append((code.strip(), desc.strip()))
    return entries


def list_layouts() -> List[Tuple[str, str]]:
    """[(code, description)] for every installed XKB layout, sorted by
    description. Falls back to a small built-in list if the rules file
    can't be read."""
    text = _read_rules_lst()
    if text:
        layouts = _parse_lst_section(text, "! layout")
        if layouts:
            return sorted(layouts, key=lambda pair: pair[1].lower())
    return sorted([
        ("us", "English (US)"), ("gb", "English (UK)"), ("de", "German"),
        ("fr", "French"), ("es", "Spanish"), ("it", "Italian"),
        ("pt", "Portuguese"), ("se", "Swedish"), ("no", "Norwegian"),
        ("dk", "Danish"), ("fi", "Finnish"), ("pl", "Polish"),
        ("cz", "Czech"), ("ru", "Russian"), ("ch", "German (Switzerland)"),
    ], key=lambda pair: pair[1].lower())


def list_variants(layout: str) -> List[Tuple[str, str]]:
    """[(variant_code, description)] for one layout, always starting with
    ('', 'default'). Empty extra entries if none/unknown."""
    result = [("", "default")]
    if not layout:
        return result
    text = _read_rules_lst()
    if not text:
        return result
    for code, desc in _parse_lst_section(text, "! variant"):
        # variant descriptions read "  nodeadkeys      de: German (no dead keys)"
        owner, _, _ = desc.partition(":")
        if owner.strip() == layout:
            result.append((code, desc.split(":", 1)[1].strip() if ":" in desc else desc))
    return result


def sample_key_characters(
    rmlvo: Optional[Dict[str, Optional[str]]] = None,
) -> List[Tuple[str, str, str]]:
    """For each sample key, return (key label, unshifted char, shifted char)
    that the given layout (or the effective one) would actually produce.
    Returns [] if xkbcommon is unavailable or the keymap won't compile."""
    if not _XKBCOMMON_AVAILABLE:
        return []
    rmlvo = rmlvo or effective_rmlvo()
    try:
        context = xkb.Context()
        keymap = context.keymap_new_from_names(
            rules=rmlvo.get("rules"), model=rmlvo.get("model"),
            layout=rmlvo.get("layout"), variant=rmlvo.get("variant"),
            options=rmlvo.get("options"),
        )
        state = keymap.state_new()
    except Exception as e:
        logger.warning(f"sample_key_characters: keymap {rmlvo} won't compile: {e}")
        return []

    def _pretty(s: Optional[str]) -> str:
        if not s:
            return "·"
        if s == " ":
            return "space"
        if s in ("\t", "\n", "\r"):
            return {"\t": "tab", "\n": "enter", "\r": "enter"}[s]
        return s

    shift_xkb = _EVDEV_LEFTSHIFT + _EVDEV_TO_XKB_OFFSET
    rows: List[Tuple[str, str, str]] = []
    for label, evdev_code in _SAMPLE_KEYS:
        xkb_code = evdev_code + _EVDEV_TO_XKB_OFFSET
        try:
            base = state.key_get_string(xkb_code)
            state.update_key(shift_xkb, xkb.XKB_KEY_DOWN)
            shifted = state.key_get_string(xkb_code)
            state.update_key(shift_xkb, xkb.XKB_KEY_UP)
        except Exception:
            base = shifted = None
        rows.append((label, _pretty(base), _pretty(shifted)))
    return rows


def rmlvo_compiles(rmlvo: Dict[str, Optional[str]]) -> Tuple[bool, str]:
    """Whether xkbcommon can build this layout. (False, reason) if not."""
    if not _XKBCOMMON_AVAILABLE:
        return False, f"xkbcommon not available: {_XKBCOMMON_IMPORT_ERROR}"
    try:
        context = xkb.Context()
        context.keymap_new_from_names(
            rules=rmlvo.get("rules"), model=rmlvo.get("model"),
            layout=rmlvo.get("layout"), variant=rmlvo.get("variant"),
            options=rmlvo.get("options"),
        )
        return True, "ok"
    except Exception as e:
        return False, str(e)


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
