"""Leftover-process cleanup from previous runs, dispatched by platform."""

import sys

if sys.platform == "win32":
    from core.windows.ahk_manager import cleanup_leftover_processes
else:
    from core.linux.process_cleanup_linux import cleanup_leftover_processes

__all__ = ["cleanup_leftover_processes"]
