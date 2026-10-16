"""Cross-platform process utilities, dispatched by platform."""

import sys

if sys.platform == "win32":
    from core.windows.process_windows import kill_pid
else:
    from core.linux.process_linux import kill_pid

__all__ = ["kill_pid"]
