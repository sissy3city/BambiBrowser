"""
Compatibility shim for the `uinput` package on Python 3.12+ (and on Python
builds where `get_config_var` returns None for the key it wants).

distutils was removed from the standard library in Python 3.12 (PEP 632),
but the unmaintained `python-uinput` package still does
`import distutils.sysconfig as sysconfig` at module load time, purely to
call `sysconfig.get_config_var(...)` to locate its compiled extension, then
string-concatenates the result onto a filename. That function still exists
in the stdlib `sysconfig` module - it just moved - so this installs a
minimal stand-in module before `uinput` is imported, rather than requiring
a real (and increasingly unavailable) distutils installation.

Two failure modes land here, not just the missing-module one:

1. Python 3.12+ with no `distutils` at all -> `import distutils.sysconfig`
   raises `ModuleNotFoundError`. Straightforward: install our shim module.

2. `import distutils.sysconfig` *succeeds* - e.g. setuptools' `_distutils_hack`
   transparently substitutes its own vendored copy on 3.12+ - but on some
   Python builds (observed on a Bazzite/Fedora-atomic uinput install)
   `get_config_var("EXT_SUFFIX")` (or the legacy alias "SO" some `uinput`
   releases use) returns None anyway, and `uinput` crashes with
   `TypeError: can only concatenate str (not "NoneType") to str` instead of
   an ImportError. A "did the import succeed" check can't catch this, so we
   always wrap `get_config_var` to be defensive regardless of which
   `distutils.sysconfig` (real, vendored, or stdlib) is actually present.
"""

import sys
import sysconfig as _stdlib_sysconfig
import types

# Sane fallback for the compiled-extension suffix if the underlying
# sysconfig can't tell us - every supported platform here is Linux, so this
# is correct even when the real value is unavailable.
_FALLBACK_EXT_SUFFIX = ".so"


def _safe_get_config_var(name):
    # Older `uinput` releases ask for the legacy distutils name "SO";
    # newer sysconfig only knows "EXT_SUFFIX".
    if name == "SO":
        name = "EXT_SUFFIX"
    value = _stdlib_sysconfig.get_config_var(name)
    return value if value is not None else _FALLBACK_EXT_SUFFIX


def ensure_distutils_sysconfig_shim() -> None:
    module = sys.modules.get("distutils.sysconfig")
    if module is None:
        try:
            import distutils.sysconfig as module  # noqa: F401 - real/vendored distutils present
        except ModuleNotFoundError:
            module = None

    if module is not None:
        # Real (or setuptools-vendored) distutils.sysconfig is present, but
        # its get_config_var can still return None on some builds - wrap it
        # defensively rather than trusting a successful import alone.
        module.get_config_var = _safe_get_config_var
        return

    distutils_pkg = sys.modules.get("distutils") or types.ModuleType("distutils")
    shim = types.ModuleType("distutils.sysconfig")
    shim.get_config_var = _safe_get_config_var
    distutils_pkg.sysconfig = shim
    sys.modules.setdefault("distutils", distutils_pkg)
    sys.modules["distutils.sysconfig"] = shim
