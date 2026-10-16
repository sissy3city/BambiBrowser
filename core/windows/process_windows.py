"""Forceful process termination by PID - Windows, via taskkill."""

import subprocess


def kill_pid(pid: int) -> None:
    """Forcefully kill a process (and its children) by PID."""
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
