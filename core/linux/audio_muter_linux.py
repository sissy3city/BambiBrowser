"""
Linux system audio muting via pactl (PipeWire's PulseAudio-compatible layer,
Fedora KDE's default audio stack) - mute all other applications' audio
streams except our own process.
"""

import logging
import os
import re
import shutil
import subprocess
from typing import Iterable, List, Optional

logger = logging.getLogger("BambiBrowser.AudioMuter")

_PACTL_AVAILABLE = shutil.which("pactl") is not None
if not _PACTL_AVAILABLE:
    logger.warning("pactl not found - system audio muting disabled (install pipewire-pulseaudio or pulseaudio-utils)")


def _list_sink_inputs() -> List[dict]:
    """Parse `pactl list sink-inputs` into a list of {index, pid, muted} dicts."""
    try:
        out = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception as e:
        logger.error(f"pactl list sink-inputs failed: {e}")
        return []

    inputs = []
    current: Optional[dict] = None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line)
        if m:
            if current:
                inputs.append(current)
            current = {"index": int(m.group(1)), "pid": None, "muted": False}
            continue
        if current is None:
            continue
        stripped = line.strip()
        pid_match = re.match(r'application\.process\.id\s*=\s*"(\d+)"', stripped)
        if pid_match:
            current["pid"] = int(pid_match.group(1))
        elif stripped.startswith("Mute:"):
            current["muted"] = "yes" in stripped
    if current:
        inputs.append(current)
    return inputs


def mute_other_applications(keep_pids: Optional[Iterable[int]] = None) -> bool:
    """Mute all playback streams except the specified PID(s).

    Defaults to just the current process's PID - but the current process is
    almost never the one making noise here: mpv runs as a separate child
    subprocess (or one per screen, in multi-monitor mode), each with its own
    PID and its own sink input. Callers that want mpv's own audio to survive
    this sweep must pass its PID(s) explicitly, or this mutes the video
    that's supposed to be playing along with everything else.
    """
    if not _PACTL_AVAILABLE:
        logger.warning("pactl not available - cannot mute other applications")
        return False

    keep_pid_set = {os.getpid()} if keep_pids is None else set(keep_pids)

    muted_count = 0
    for stream in _list_sink_inputs():
        if stream["pid"] in keep_pid_set:
            continue
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(stream["index"]), "1"],
                capture_output=True, timeout=2, check=False,
            )
            muted_count += 1
            logger.info(f"Muted sink input #{stream['index']} (pid {stream['pid']})")
        except Exception as e:
            logger.debug(f"Could not mute sink input #{stream['index']}: {e}")

    logger.info(f"Muted {muted_count} audio stream(s) (kept PID(s) {sorted(keep_pid_set)})")
    return True


def unmute_all_applications() -> bool:
    """Unmute all currently-muted playback streams."""
    if not _PACTL_AVAILABLE:
        return False

    unmuted_count = 0
    for stream in _list_sink_inputs():
        if not stream["muted"]:
            continue
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(stream["index"]), "0"],
                capture_output=True, timeout=2, check=False,
            )
            unmuted_count += 1
            logger.info(f"Unmuted sink input #{stream['index']}")
        except Exception as e:
            logger.debug(f"Could not unmute sink input #{stream['index']}: {e}")

    logger.info(f"Unmuted {unmuted_count} audio stream(s)")
    return True


def is_audio_muting_available() -> bool:
    return _PACTL_AVAILABLE
