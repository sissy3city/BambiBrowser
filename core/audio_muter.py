"""System audio muting, dispatched by platform."""

import sys
from typing import Optional

if sys.platform == "win32":
    from core.windows.audio_muter_windows import (
        mute_other_applications,
        unmute_all_applications,
        is_audio_muting_available,
    )
else:
    from core.linux.audio_muter_linux import (
        mute_other_applications,
        unmute_all_applications,
        is_audio_muting_available,
    )

__all__ = ["mute_other_applications", "unmute_all_applications", "is_audio_muting_available"]
