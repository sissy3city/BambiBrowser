"""Windows system audio muting via pycaw - mute all audio sessions except our own process."""

import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger("BambiBrowser.AudioMuter")

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    logger.warning("pycaw not installed - system audio muting disabled")
    logger.warning("Install with: pip install pycaw")


def mute_other_applications(keep_pids: Optional[Iterable[int]] = None) -> bool:
    """Mute all audio sessions except the specified PID(s).

    Defaults to just the current process's PID - but the current process is
    almost never the one making noise here: mpv runs as a separate child
    subprocess (or one per screen, in multi-monitor mode), each with its own
    PID and its own audio session. Callers that want mpv's own audio to
    survive this sweep must pass its PID(s) explicitly, or this mutes the
    video that's supposed to be playing along with everything else.
    """
    if not PYCAW_AVAILABLE:
        logger.warning("pycaw not available - cannot mute other applications")
        return False

    keep_pid_set = {os.getpid()} if keep_pids is None else set(keep_pids)

    try:
        sessions = AudioUtilities.GetAllSessions()
        muted_count = 0

        for session in sessions:
            if session.Process:
                pid = session.Process.pid
                if pid in keep_pid_set:
                    continue  # Keep our own process
                try:
                    volume = session.SimpleAudioVolume
                    volume.SetMute(True, None)
                    muted_count += 1
                    logger.info(f"Muted audio for PID {pid} ({session.Process.name()})")
                except Exception as e:
                    logger.debug(f"Could not mute PID {pid}: {e}")
            else:
                # System sounds - mute them too
                try:
                    volume = session.SimpleAudioVolume
                    volume.SetMute(True, None)
                    muted_count += 1
                    logger.info("Muted system sounds")
                except Exception:
                    pass

        logger.info(f"Muted {muted_count} audio sessions (kept PID(s) {sorted(keep_pid_set)})")
        return True
    except Exception as e:
        logger.error(f"Failed to mute other applications: {e}")
        return False


def unmute_all_applications() -> bool:
    """Unmute all audio sessions."""
    if not PYCAW_AVAILABLE:
        return False

    try:
        sessions = AudioUtilities.GetAllSessions()
        unmuted_count = 0
        for session in sessions:
            try:
                volume = session.SimpleAudioVolume
                if volume.GetMute():
                    volume.SetMute(False, None)
                    unmuted_count += 1
                    if session.Process:
                        logger.info(f"Unmuted PID {session.Process.pid} ({session.Process.name()})")
                    else:
                        logger.info("Unmuted system sounds")
            except Exception:
                pass
        logger.info(f"Unmuted {unmuted_count} audio sessions")
        return True
    except Exception as e:
        logger.error(f"Failed to unmute applications: {e}")
        return False


def is_audio_muting_available() -> bool:
    return PYCAW_AVAILABLE
