"""Forceful process termination by PID - Linux, via SIGTERM."""

import os
import signal


def kill_pid(pid: int) -> None:
    """Terminate a process by PID."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # Already gone
