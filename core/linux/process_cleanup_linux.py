"""Leftover-process cleanup - Linux stub.

Linux's text replacement and Bambi Gag use the native evdev/uinput engine
(core/linux/linux_text_replacer.py, core/linux/linux_gag_engine.py) rather
than spawning an external AutoHotkey-style helper process, so there is
nothing analogous to clean up yet. This stands in for
core.windows.ahk_manager.cleanup_leftover_processes() so
core/process_cleanup.py has a Linux-side implementation to dispatch to.
"""


def cleanup_leftover_processes() -> None:
    """No-op - nothing to clean up on Linux yet."""
    pass
