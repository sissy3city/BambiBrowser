"""Core functionality modules for BambiBrowser."""

from core.hard_lock import HardLock
from core.player import VideoPlayer
from core.server import BambiServer
from core.text_replacer import TextReplacer
from core.utils import get_base_dir, setup_logging
from core.settings_manager import SettingsManager
from core.auto_updater import AutoUpdater
from core.gag_manager import GagManager

__all__ = [
    'HardLock',
    'VideoPlayer',
    'BambiServer',
    'TextReplacer',
    'get_base_dir',
    'setup_logging',
    'SettingsManager',
    'AutoUpdater',
    'GagManager',
]