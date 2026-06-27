"""System audio muting – mute all audio sessions except our own process."""

import logging
import os
import time
from typing import Optional, List

logger = logging.getLogger("BambiBrowser.AudioMuter")

# Try to import pycaw – if missing, fallback to no operation
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    PYCAA_AVAILABLE = True
except ImportError:
    PYCAA_AVAILABLE = False
    logger.warning("pycaw not installed – system audio muting disabled")
    logger.warning("Install with: pip install pycaw")


def get_current_process_pid() -> int:
    """Return the PID of the current process."""
    return os.getpid()


def mute_other_applications(keep_pid: Optional[int] = None) -> bool:
    """
    Mute all audio sessions except the specified PID.
    If no PID given, uses current process.
    Returns True if successful.
    """
    if not PYCAA_AVAILABLE:
        logger.warning("pycaw not available – cannot mute other applications")
        return False

    if keep_pid is None:
        keep_pid = get_current_process_pid()

    try:
        sessions = AudioUtilities.GetAllSessions()
        muted_count = 0

        for session in sessions:
            if session.Process:
                pid = session.Process.pid
                if pid == keep_pid:
                    continue  # Keep our own process
                # Mute this session
                try:
                    volume = session.SimpleAudioVolume
                    volume.SetMute(True, None)
                    muted_count += 1
                    logger.info(f"Muted audio for PID {pid} ({session.Process.name()})")
                except Exception as e:
                    logger.debug(f"Could not mute PID {pid}: {e}")
            else:
                # System sounds – mute them too
                try:
                    volume = session.SimpleAudioVolume
                    volume.SetMute(True, None)
                    muted_count += 1
                    logger.info("Muted system sounds")
                except:
                    pass

        logger.info(f"Muted {muted_count} audio sessions (kept PID {keep_pid})")
        return True
    except Exception as e:
        logger.error(f"Failed to mute other applications: {e}")
        return False


def unmute_all_applications() -> bool:
    """Unmute all audio sessions."""
    if not PYCAA_AVAILABLE:
        return False

    try:
        sessions = AudioUtilities.GetAllSessions()
        unmuted_count = 0
        for session in sessions:
            try:
                volume = session.SimpleAudioVolume
                # Only unmute if currently muted
                if volume.GetMute():
                    volume.SetMute(False, None)
                    unmuted_count += 1
                    if session.Process:
                        logger.info(f"Unmuted PID {session.Process.pid} ({session.Process.name()})")
                    else:
                        logger.info("Unmuted system sounds")
            except:
                pass
        logger.info(f"Unmuted {unmuted_count} audio sessions")
        return True
    except Exception as e:
        logger.error(f"Failed to unmute applications: {e}")
        return False


def is_audio_muting_available() -> bool:
    """Check if system audio muting is available."""
    return PYCAA_AVAILABLE