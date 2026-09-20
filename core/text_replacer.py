"""OS-level text replacement - AutoHotkey on Windows, a native evdev/uinput engine on Linux."""

import logging
import sys
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("BambiBrowser.TextReplacer")


class TextReplacer(QObject):
    replacements_updated = pyqtSignal(dict)
    replacement_triggered = pyqtSignal(str, str)
    status_changed = pyqtSignal(bool)

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._enabled = False
        self._use_prefix = False
        self._prefix_char = ";"
        self._replacement_rules: Dict[str, str] = {}
        if sys.platform == "win32":
            from core.windows.ahk_manager import AHKManager
            self._ahk = AHKManager()
        else:
            from core.linux.linux_text_replacer import LinuxTextReplacerEngine
            self._ahk = LinuxTextReplacerEngine()

        # Load from settings manager
        self._load_from_settings()

        # Connect to settings changes
        if self._settings_manager:
            self._settings_manager.text_replacer_settings_changed.connect(self._on_settings_changed)

    def _load_from_settings(self):
        """Load rules and mode from settings manager."""
        if not self._settings_manager:
            return
        tr = self._settings_manager.text_replacer
        self._replacement_rules = tr.rules.copy()
        self._use_prefix = tr.use_prefix
        self._prefix_char = tr.prefix_char or ";"
        self._enabled = tr.enabled
        # If enabled and AHK available, start automatically
        if self._enabled and self._ahk.is_available:
            self._ahk.start(self._replacement_rules, self._use_prefix, self._prefix_char)

    def _on_settings_changed(self, settings):
        """React to settings changes from manager."""
        self._replacement_rules = settings.rules.copy()
        self._use_prefix = settings.use_prefix
        self._prefix_char = settings.prefix_char or ";"
        if settings.enabled and not self._enabled:
            self.start()
        elif not settings.enabled and self._enabled:
            self.stop()
        elif self._enabled:
            # Reload with new rules
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        self.replacements_updated.emit(self.rules)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_locked(self) -> bool:
        return self._settings_manager.is_locked if self._settings_manager else False

    @property
    def rules(self) -> dict:
        return self._replacement_rules.copy()

    @property
    def use_prefix(self) -> bool:
        return self._use_prefix

    @use_prefix.setter
    def use_prefix(self, value: bool):
        if self.is_locked:
            logger.warning("Cannot change mode - settings are locked")
            return
        self._use_prefix = value
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        # Update settings manager
        if self._settings_manager:
            self._settings_manager.update_text_replacer(use_prefix=value)

    @property
    def prefix_char(self) -> str:
        return self._prefix_char

    @prefix_char.setter
    def prefix_char(self, value: str):
        if self.is_locked:
            logger.warning("Cannot change prefix - settings are locked")
            return
        self._prefix_char = value
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        if self._settings_manager:
            self._settings_manager.update_text_replacer(prefix_char=value)

    @property
    def ahk_available(self) -> bool:
        return self._ahk.is_available

    @property
    def ahk_path(self) -> Optional[str]:
        return self._ahk._ahk_exe

    def set_rules(self, rules: Dict[str, str]):
        if self.is_locked:
            logger.warning("Cannot modify rules - settings are locked")
            return
        new_rules = {}
        for orig, repl in rules.items():
            if orig and repl:
                new_rules[orig.lower()] = repl
        if new_rules == self._replacement_rules:
            return
        self._replacement_rules = new_rules
        logger.info(f"Rules updated: {len(self._replacement_rules)} rules")
        self.replacements_updated.emit(self.rules)
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        # Save to settings manager
        if self._settings_manager:
            self._settings_manager.set_text_replacer_rules(new_rules)

    def add_rule(self, original: str, replacement: str):
        if self.is_locked:
            logger.warning("Cannot add rule - settings are locked")
            return
        if original and replacement:
            self._replacement_rules[original.lower()] = replacement
            self.replacements_updated.emit(self.rules)
            if self._enabled:
                self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
            if self._settings_manager:
                self._settings_manager.set_text_replacer_rules(self._replacement_rules)
            logger.info(f"Added rule: '{original}' → '{replacement}'")

    def remove_rule(self, original: str):
        if self.is_locked:
            logger.warning("Cannot remove rule - settings are locked")
            return
        key = original.lower()
        if key in self._replacement_rules:
            del self._replacement_rules[key]
            self.replacements_updated.emit(self.rules)
            if self._enabled:
                self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
            if self._settings_manager:
                self._settings_manager.set_text_replacer_rules(self._replacement_rules)
            logger.info(f"Removed rule: '{original}'")

    def clear_rules(self):
        if self.is_locked:
            logger.warning("Cannot clear rules - settings are locked")
            return
        self._replacement_rules.clear()
        self.replacements_updated.emit(self.rules)
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        if self._settings_manager:
            self._settings_manager.set_text_replacer_rules({})
        logger.info("All rules cleared")

    def reset_to_default(self):
        if self.is_locked:
            logger.warning("Cannot reset - settings are locked")
            return
        self._load_default_rules()
        self.replacements_updated.emit(self.rules)
        if self._enabled:
            self._ahk.reload(self._replacement_rules, self._use_prefix, self._prefix_char)
        if self._settings_manager:
            self._settings_manager.reset_text_replacer_to_default()
        logger.info("Reset to default rules")

    def _load_default_rules(self):
        defaults = {
            "i": "Bambi", "me": "Bambi", "my": "Bambi's", "mine": "Bambi's",
            "myself": "Bambi", "im": "Bambi is", "ive": "Bambi has",
            "id": "Bambi would", "ill": "Bambi will", "we": "Bambi and friends",
            "our": "Bambi's", "ours": "Bambi's", "weve": "Bambi and friends have",
            "were": "Bambi and friends are", "well": "Bambi and friends will",
            "am": "is", "us": "Bambi",
        }
        self._replacement_rules = defaults.copy()
        logger.info(f"Loaded {len(self._replacement_rules)} default rules")

    def start(self) -> bool:
        if self._enabled:
            return True
        if not self._ahk.is_available:
            logger.error("AutoHotkey not available even after download attempt")
            return False
        success = self._ahk.start(self._replacement_rules, self._use_prefix, self._prefix_char)
        if success:
            self._enabled = True
            self.status_changed.emit(True)
            # Update settings manager
            if self._settings_manager:
                self._settings_manager.update_text_replacer(enabled=True)
            if self._use_prefix:
                logger.info(f"🔄 Text replacement STARTED - Type '{self._prefix_char}i' for Bambi")
            else:
                logger.info("🔄 Text replacement STARTED (Auto-replace mode)")
        return success

    def stop(self):
        if not self._enabled:
            return
        self._ahk.stop()
        self._enabled = False
        self.status_changed.emit(False)
        if self._settings_manager:
            self._settings_manager.update_text_replacer(enabled=False)
        logger.info("Text replacement stopped")

    def toggle(self) -> bool:
        if self._enabled:
            self.stop()
        else:
            self.start()
        return self._enabled

    def get_status(self) -> dict:
        return {
            "enabled": self._enabled,
            "locked": self.is_locked,
            "rule_count": len(self._replacement_rules),
            "use_prefix": self._use_prefix,
            "prefix_char": self._prefix_char,
            "ahk_available": self._ahk.is_available,
            "ahk_running": self._ahk.is_running,
            "ahk_path": self._ahk._ahk_exe,
        }

    def get_script_preview(self) -> str:
        return self._ahk.get_script_preview(
            self._replacement_rules,
            self._use_prefix,
            self._prefix_char
        )
