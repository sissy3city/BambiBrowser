"""Admin elevation and legacy-autostart cleanup, dispatched by platform."""

import sys

if sys.platform == "win32":
    from core.windows.elevation_windows import (
        is_admin,
        request_admin_privileges,
        remove_legacy_autostart_registry_entry,
    )
else:
    from core.linux.elevation_linux import (
        is_admin,
        request_admin_privileges,
        remove_legacy_autostart_registry_entry,
    )

__all__ = [
    "is_admin",
    "request_admin_privileges",
    "remove_legacy_autostart_registry_entry",
]
