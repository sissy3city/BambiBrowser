# core/settings_manager.py
import json
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

from PyQt6.QtCore import QObject, pyqtSignal, QSettings

logger = logging.getLogger("BambiBrowser.SettingsManager")

@dataclass
class PlaybackSettings:
    input_lock: bool = True
    click_through: bool = False
    opacity: int = 100
    multi_monitor: bool = False
    selected_monitors: List[int] = field(default_factory=list)
    volume: int = 256
    mute_other_audio: bool = False

@dataclass
class SafetySettings:
    max_video_length_enabled: bool = False
    max_video_length_minutes: int = 10
    max_video_length_action: str = "Block & Show Warning"
    max_queue_duration_enabled: bool = False
    max_queue_duration_minutes: int = 60
    max_queue_duration_action: str = "Reject New Videos"

@dataclass
class TextReplacerSettings:
    enabled: bool = False
    use_prefix: bool = False
    prefix_char: str = ";"
    rules: Dict[str, str] = field(default_factory=dict)

@dataclass
class GagSettings:
    enabled: bool = False
    remote_url: str = ""
    local_toggle: bool = False

class SettingsManager(QObject):
    lock_state_changed = pyqtSignal(bool)
    playback_settings_changed = pyqtSignal(object)
    safety_settings_changed = pyqtSignal(object)
    text_replacer_settings_changed = pyqtSignal(object)
    gag_settings_changed = pyqtSignal(object)
    all_settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qsettings = QSettings("BambiBrowser", "Settings")
        self._locked = False

        self._playback = PlaybackSettings()
        self._safety = SafetySettings()
        self._text_replacer = TextReplacerSettings()
        self._gag = GagSettings()

        self._text_replacer.rules = {
            "i": "Bambi", "me": "Bambi", "my": "Bambi's", "mine": "Bambi's",
            "myself": "Bambi", "im": "Bambi is", "ive": "Bambi has",
            "id": "Bambi would", "ill": "Bambi will", "we": "Bambi and friends",
            "our": "Bambi's", "ours": "Bambi's", "weve": "Bambi and friends have",
            "were": "Bambi and friends are", "well": "Bambi and friends will",
            "am": "is", "us": "Bambi",
        }
        self._load_all()

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def playback(self) -> PlaybackSettings:
        return self._playback

    @property
    def safety(self) -> SafetySettings:
        return self._safety

    @property
    def text_replacer(self) -> TextReplacerSettings:
        return self._text_replacer

    @property
    def gag(self) -> GagSettings:
        return self._gag

    def get_stored_otp_hash(self) -> Optional[str]:
        hash_val = self._qsettings.value("otp_hash", "")
        return hash_val if hash_val else None

    def is_otp_set(self) -> bool:
        return bool(self.get_stored_otp_hash())

    def verify_otp(self, otp: str) -> bool:
        stored_hash = self.get_stored_otp_hash()
        if not stored_hash:
            return False
        entered_hash = hashlib.sha256(otp.encode()).hexdigest()
        return entered_hash == stored_hash

    def generate_new_otp(self) -> str:
        return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

    def lock_with_otp(self, otp: str) -> bool:
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        self._qsettings.setValue("otp_hash", otp_hash)
        self._save_all()
        self._locked = True
        self.lock_state_changed.emit(True)
        logger.info("Settings locked with OTP")
        return True

    def unlock_with_otp(self, otp: str) -> bool:
        if not self.verify_otp(otp):
            logger.warning("OTP verification failed")
            return False
        self._qsettings.remove("otp_hash")
        self._locked = False
        self.lock_state_changed.emit(False)
        logger.info("Settings unlocked")
        return True

    def force_unlock(self):
        self._qsettings.remove("otp_hash")
        self._locked = False
        self.lock_state_changed.emit(False)
        logger.warning("Settings force unlocked")

    def _check_locked(self) -> bool:
        if self._locked:
            logger.warning("Attempted to modify locked settings")
            return True
        return False

    def update_playback(self, **kwargs) -> bool:
        if self._check_locked():
            return False
        for key, value in kwargs.items():
            if hasattr(self._playback, key):
                setattr(self._playback, key, value)
        self._save_playback()
        self.playback_settings_changed.emit(self._playback)
        self.all_settings_changed.emit()
        return True

    def update_safety(self, **kwargs) -> bool:
        if self._check_locked():
            return False
        for key, value in kwargs.items():
            if hasattr(self._safety, key):
                setattr(self._safety, key, value)
        self._save_safety()
        self.safety_settings_changed.emit(self._safety)
        self.all_settings_changed.emit()
        return True

    def update_text_replacer(self, **kwargs) -> bool:
        if self._check_locked():
            return False
        for key, value in kwargs.items():
            if hasattr(self._text_replacer, key):
                setattr(self._text_replacer, key, value)
        self._save_text_replacer()
        self.text_replacer_settings_changed.emit(self._text_replacer)
        self.all_settings_changed.emit()
        return True

    def set_text_replacer_rules(self, rules: Dict[str, str]) -> bool:
        if self._check_locked():
            return False
        self._text_replacer.rules = rules.copy()
        self._save_text_replacer()
        self.text_replacer_settings_changed.emit(self._text_replacer)
        self.all_settings_changed.emit()
        return True

    def reset_text_replacer_to_default(self) -> bool:
        if self._check_locked():
            return False
        self._text_replacer.rules = {
            "i": "Bambi", "me": "Bambi", "my": "Bambi's", "mine": "Bambi's",
            "myself": "Bambi", "im": "Bambi is", "ive": "Bambi has",
            "id": "Bambi would", "ill": "Bambi will", "we": "Bambi and friends",
            "our": "Bambi's", "ours": "Bambi's", "weve": "Bambi and friends have",
            "were": "Bambi and friends are", "well": "Bambi and friends will",
            "am": "is", "us": "Bambi",
        }
        self._save_text_replacer()
        self.text_replacer_settings_changed.emit(self._text_replacer)
        self.all_settings_changed.emit()
        return True

    def update_gag(self, **kwargs) -> bool:
        if self._check_locked():
            return False
        for key, value in kwargs.items():
            if hasattr(self._gag, key):
                setattr(self._gag, key, value)
        self._save_gag()
        self.gag_settings_changed.emit(self._gag)
        self.all_settings_changed.emit()
        return True

    def get_gag_settings(self) -> GagSettings:
        return self._gag

    def _load_all(self):
        saved_hash = self._qsettings.value("otp_hash", "")
        self._locked = bool(saved_hash and saved_hash.strip() != "")

        self._playback.input_lock = self._qsettings.value("playback/input_lock", True, type=bool)
        self._playback.click_through = self._qsettings.value("playback/click_through", False, type=bool)
        self._playback.opacity = self._qsettings.value("playback/opacity", 100, type=int)
        self._playback.multi_monitor = self._qsettings.value("playback/multi_monitor", False, type=bool)
        self._playback.selected_monitors = self._qsettings.value("playback/selected_monitors", [], type=list)
        self._playback.volume = self._qsettings.value("playback/volume", 256, type=int)
        self._playback.mute_other_audio = self._qsettings.value("playback/mute_other_audio", False, type=bool)

        self._safety.max_video_length_enabled = self._qsettings.value("safety/max_video_length_enabled", False, type=bool)
        self._safety.max_video_length_minutes = self._qsettings.value("safety/max_video_length_minutes", 10, type=int)
        self._safety.max_video_length_action = self._qsettings.value("safety/max_video_length_action", "Block & Show Warning", type=str)
        self._safety.max_queue_duration_enabled = self._qsettings.value("safety/max_queue_duration_enabled", False, type=bool)
        self._safety.max_queue_duration_minutes = self._qsettings.value("safety/max_queue_duration_minutes", 60, type=int)
        self._safety.max_queue_duration_action = self._qsettings.value("safety/max_queue_duration_action", "Reject New Videos", type=str)

        self._text_replacer.enabled = self._qsettings.value("text_replacer/enabled", False, type=bool)
        self._text_replacer.use_prefix = self._qsettings.value("text_replacer/use_prefix", False, type=bool)
        self._text_replacer.prefix_char = self._qsettings.value("text_replacer/prefix_char", ";", type=str)
        rules_json = self._qsettings.value("text_replacer/rules", "")
        if rules_json:
            try:
                self._text_replacer.rules = json.loads(rules_json)
            except:
                pass

        self._gag.enabled = self._qsettings.value("gag/enabled", False, type=bool)
        self._gag.remote_url = self._qsettings.value("gag/remote_url", "", type=str)
        self._gag.local_toggle = self._qsettings.value("gag/local_toggle", False, type=bool)

        logger.info(f"Settings loaded - Locked: {self._locked}")

    def _save_all(self):
        self._save_playback()
        self._save_safety()
        self._save_text_replacer()
        self._save_gag()
        self._qsettings.sync()
        logger.info("All settings saved")

    def _save_playback(self):
        self._qsettings.setValue("playback/input_lock", self._playback.input_lock)
        self._qsettings.setValue("playback/click_through", self._playback.click_through)
        self._qsettings.setValue("playback/opacity", self._playback.opacity)
        self._qsettings.setValue("playback/multi_monitor", self._playback.multi_monitor)
        self._qsettings.setValue("playback/selected_monitors", self._playback.selected_monitors)
        self._qsettings.setValue("playback/volume", self._playback.volume)
        self._qsettings.setValue("playback/mute_other_audio", self._playback.mute_other_audio)

    def _save_safety(self):
        self._qsettings.setValue("safety/max_video_length_enabled", self._safety.max_video_length_enabled)
        self._qsettings.setValue("safety/max_video_length_minutes", self._safety.max_video_length_minutes)
        self._qsettings.setValue("safety/max_video_length_action", self._safety.max_video_length_action)
        self._qsettings.setValue("safety/max_queue_duration_enabled", self._safety.max_queue_duration_enabled)
        self._qsettings.setValue("safety/max_queue_duration_minutes", self._safety.max_queue_duration_minutes)
        self._qsettings.setValue("safety/max_queue_duration_action", self._safety.max_queue_duration_action)

    def _save_text_replacer(self):
        self._qsettings.setValue("text_replacer/enabled", self._text_replacer.enabled)
        self._qsettings.setValue("text_replacer/use_prefix", self._text_replacer.use_prefix)
        self._qsettings.setValue("text_replacer/prefix_char", self._text_replacer.prefix_char)
        self._qsettings.setValue("text_replacer/rules", json.dumps(self._text_replacer.rules))

    def _save_gag(self):
        self._qsettings.setValue("gag/enabled", self._gag.enabled)
        self._qsettings.setValue("gag/remote_url", self._gag.remote_url)
        self._qsettings.setValue("gag/local_toggle", self._gag.local_toggle)

    def get_player_settings_dict(self) -> Dict[str, Any]:
        return {
            "input_lock": self._playback.input_lock,
            "click_through": self._playback.click_through,
            "opacity": self._playback.opacity,
            "multi_monitor": self._playback.multi_monitor,
            "selected_monitors": self._playback.selected_monitors.copy(),
            "volume": self._playback.volume,
            "mute_other_audio": self._playback.mute_other_audio,
            "max_video_length_enabled": self._safety.max_video_length_enabled,
            "max_video_length_minutes": self._safety.max_video_length_minutes,
            "max_video_length_action": self._safety.max_video_length_action,
            "max_queue_duration_enabled": self._safety.max_queue_duration_enabled,
            "max_queue_duration_minutes": self._safety.max_queue_duration_minutes,
            "max_queue_duration_action": self._safety.max_queue_duration_action,
        }