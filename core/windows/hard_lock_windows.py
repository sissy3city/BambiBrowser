"""
Windows HardLock implementation.

Combines two lockdown mechanisms:
- KeyboardDeviceDisabler: disables keyboard device nodes at the driver level
  (CM_Disable_DevNode), which blocks all input from the hardware including the
  Secure Attention Sequence (Ctrl+Alt+Del), since the kernel never receives
  events from a disabled device node. Requires Administrator.
- A WH_KEYBOARD_LL low-level hook that suppresses the Win key, Alt+Tab, and
  Ctrl+Esc, as a lighter-weight layer that works even without admin rights.
Falls back to BlockInput, and then to the keyboard/mouse hook libraries, if
the above are unavailable.
"""

import atexit
import ctypes
import logging
import time
from ctypes import wintypes, byref, sizeof, c_ulong, c_bool, POINTER, CFUNCTYPE, c_int
from typing import List

logger = logging.getLogger("BambiBrowser.HardLock")

# Windows API constants
WH_KEYBOARD_LL = 13
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", _GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


# {4D36E96B-E325-11CE-BFC1-08002BE10318} — Keyboard device class
_KEYBOARD_CLASS_GUID = _GUID(
    Data1=0x4D36E96B,
    Data2=0xE325,
    Data3=0x11CE,
    Data4=(ctypes.c_ubyte * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18),
)

_DIGCF_PRESENT = 0x00000002
_CR_SUCCESS = 0x00000000

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class KeyboardDeviceDisabler:
    """Disables every keyboard device node at the driver level via CM_Disable_DevNode."""

    _INVALID_HANDLE = ctypes.c_size_t(-1).value

    def __init__(self):
        self._disabled: List[int] = []
        self.available = False

        try:
            _setupapi = ctypes.WinDLL("setupapi.dll")
            _cfgmgr32 = ctypes.WinDLL("cfgmgr32.dll")

            self._GetClassDevs = _setupapi.SetupDiGetClassDevsW
            self._GetClassDevs.argtypes = [
                POINTER(_GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
            ]
            self._GetClassDevs.restype = ctypes.c_void_p

            self._EnumDeviceInfo = _setupapi.SetupDiEnumDeviceInfo
            self._EnumDeviceInfo.argtypes = [
                ctypes.c_void_p, wintypes.DWORD, POINTER(_SP_DEVINFO_DATA),
            ]
            self._EnumDeviceInfo.restype = wintypes.BOOL

            self._DestroyDeviceInfoList = _setupapi.SetupDiDestroyDeviceInfoList
            self._DestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
            self._DestroyDeviceInfoList.restype = wintypes.BOOL

            self._GetDeviceID = _cfgmgr32.CM_Get_Device_IDW
            self._GetDeviceID.argtypes = [
                wintypes.DWORD, wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG,
            ]
            self._GetDeviceID.restype = wintypes.DWORD

            self._Disable = _cfgmgr32.CM_Disable_DevNode
            self._Disable.argtypes = [wintypes.DWORD, wintypes.ULONG]
            self._Disable.restype = wintypes.DWORD

            self._Enable = _cfgmgr32.CM_Enable_DevNode
            self._Enable.argtypes = [wintypes.DWORD, wintypes.ULONG]
            self._Enable.restype = wintypes.DWORD

            self.available = True
            logger.info("KeyboardDeviceDisabler: driver-level API ready")

        except Exception as e:
            logger.warning(f"KeyboardDeviceDisabler: API unavailable - {e}")

        atexit.register(self._atexit_restore)

    def _enumerate(self) -> List[int]:
        """Return DevInst handles for all present keyboard device nodes."""
        devs: List[int] = []
        h = self._GetClassDevs(
            byref(_KEYBOARD_CLASS_GUID), None, None, _DIGCF_PRESENT,
        )
        if h is None or ctypes.c_size_t(h).value == self._INVALID_HANDLE:
            logger.error("KeyboardDeviceDisabler: SetupDiGetClassDevs failed")
            return devs
        try:
            i = 0
            while True:
                info = _SP_DEVINFO_DATA()
                info.cbSize = sizeof(_SP_DEVINFO_DATA)
                if not self._EnumDeviceInfo(h, i, byref(info)):
                    break
                buf = ctypes.create_unicode_buffer(256)
                if self._GetDeviceID(info.DevInst, buf, 256, 0) == _CR_SUCCESS:
                    logger.info(f"  keyboard device: {buf.value}")
                devs.append(info.DevInst)
                i += 1
        finally:
            self._DestroyDeviceInfoList(h)
        return devs

    def disable(self) -> bool:
        """Disable all keyboard devices at driver level. Returns True if any succeeded."""
        if not self.available:
            return False
        self._disabled = []
        keyboards = self._enumerate()
        if not keyboards:
            logger.warning("KeyboardDeviceDisabler: no keyboard devices found")
            return False
        for devinst in keyboards:
            ret = self._Disable(devinst, 0)
            if ret == _CR_SUCCESS:
                self._disabled.append(devinst)
                logger.info(f"KeyboardDeviceDisabler: device {devinst:#x} disabled")
            else:
                logger.warning(
                    f"KeyboardDeviceDisabler: CM_Disable_DevNode({devinst:#x}) = {ret:#x}"
                )
        logger.info(
            f"KeyboardDeviceDisabler: {len(self._disabled)}/{len(keyboards)} device(s) disabled"
        )
        return bool(self._disabled)

    def enable(self):
        """Re-enable all previously disabled keyboard devices."""
        for devinst in self._disabled:
            ret = self._Enable(devinst, 0)
            if ret == _CR_SUCCESS:
                logger.info(f"KeyboardDeviceDisabler: device {devinst:#x} re-enabled")
            else:
                logger.warning(
                    f"KeyboardDeviceDisabler: CM_Enable_DevNode({devinst:#x}) = {ret:#x}"
                )
        self._disabled.clear()

    def _atexit_restore(self):
        if self._disabled:
            logger.warning("KeyboardDeviceDisabler: atexit safety net - re-enabling keyboards")
            self.enable()


class WindowsHardLock:
    """Atomic input lock - blocks keyboard/mouse via device disable + BlockInput + low-level hook."""

    def __init__(self):
        self._locked = False
        self._block_input_active = False
        self._keyboard_hook_active = False
        self._mouse_hook_active = False
        self._kbd_disable_active = False
        self._low_level_hook = None
        self._hook_callback = None
        self._lock_start_time = 0.0

        self._kbd_disabler = KeyboardDeviceDisabler()

        try:
            self._BlockInput = user32.BlockInput
            self._BlockInput.argtypes = [c_bool]
            self._BlockInput.restype = c_bool
            self._windows_api_available = True
            logger.info("Windows BlockInput API available")
        except Exception as e:
            logger.warning(f"Windows BlockInput API not available: {e}")
            self._windows_api_available = False

        self._keyboard_available = False
        self._mouse_available = False
        try:
            import keyboard
            self.keyboard = keyboard
            self._keyboard_available = True
            logger.info("Keyboard module loaded (fallback)")
        except ImportError:
            self.keyboard = None
        try:
            import mouse
            self.mouse = mouse
            self._mouse_available = True
            logger.info("Mouse module loaded (fallback)")
        except ImportError:
            self.mouse = None

        atexit.register(self.unlock)

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def keyboard_available(self) -> bool:
        return self._windows_api_available or self._keyboard_available

    @property
    def mouse_available(self) -> bool:
        return self._windows_api_available or self._mouse_available

    def lock(self) -> None:
        """Enable atomic input lock - NO ESCAPE."""
        if self._locked:
            return
        self._locked = True
        self._lock_start_time = time.time()
        logger.info("HardLock ENABLED - all input blocked (including Win key, Alt+Tab)")

        # Disable keyboard at driver level first - this stops Ctrl+Alt+Del too.
        if self._kbd_disabler.disable():
            self._kbd_disable_active = True

        # Always install the low-level hook to catch system keys.
        self._install_low_level_hook()

        if self._windows_api_available:
            try:
                if self._BlockInput(True):
                    self._block_input_active = True
                    logger.info("BlockInput activated")
                else:
                    logger.warning("BlockInput failed - might need admin rights, using fallback hooks")
                    self._apply_full_hooks()
            except Exception as e:
                logger.error(f"BlockInput error: {e}")
                self._apply_full_hooks()
        else:
            self._apply_full_hooks()

    def unlock(self) -> None:
        """Disable atomic input lock."""
        if not self._locked:
            return
        logger.info("Releasing HardLock...")

        # Re-enable keyboard devices first so the user can type again.
        if self._kbd_disable_active:
            self._kbd_disabler.enable()
            self._kbd_disable_active = False

        self._uninstall_low_level_hook()

        if self._block_input_active:
            try:
                self._BlockInput(False)
            except Exception as e:
                logger.error(f"Failed to release BlockInput: {e}")
            self._block_input_active = False

        if self._keyboard_hook_active and self.keyboard:
            try:
                self.keyboard.unhook_all()
            except Exception as e:
                logger.error(f"Failed to remove keyboard hooks: {e}")
            self._keyboard_hook_active = False

        if self._mouse_hook_active and self.mouse:
            try:
                self.mouse.unhook_all()
            except Exception as e:
                logger.error(f"Failed to remove mouse hooks: {e}")
            self._mouse_hook_active = False

        try:
            user32.SystemParametersInfoW(0x97, 0, 0, 0)  # SPI_SETSCREENSAVERRUNNING
        except Exception:
            pass

        self._locked = False
        logger.info("HardLock released - system input restored")

    def force_unlock(self) -> None:
        """Emergency unlock - for internal use only."""
        logger.warning("Emergency unlock triggered")
        self.unlock()

    def _install_low_level_hook(self) -> None:
        """Install a low-level keyboard hook that suppresses Win key, Alt+Tab, Ctrl+Esc."""
        if self._low_level_hook is not None:
            return

        def low_level_handler(nCode, wParam, lParam):
            if nCode >= 0:
                kb = KBDLLHOOKSTRUCT.from_address(lParam)
                vk = kb.vkCode

                if vk in (VK_LWIN, VK_RWIN):
                    return 1
                if vk == VK_TAB and user32.GetAsyncKeyState(VK_MENU) & 0x8000:
                    return 1
                if vk == VK_ESCAPE and user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                    return 1

            return user32.CallNextHookExW(None, nCode, wParam, lParam)

        self._hook_callback = CFUNCTYPE(c_int, c_int, wintypes.WPARAM, wintypes.LPARAM)(low_level_handler)
        self._low_level_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_callback, kernel32.GetModuleHandleW(None), 0
        )

        if self._low_level_hook:
            logger.info("Low-level keyboard hook installed (blocks Win, Alt+Tab, Ctrl+Esc)")
        else:
            logger.warning("Failed to install low-level keyboard hook")

    def _uninstall_low_level_hook(self) -> None:
        if self._low_level_hook:
            try:
                user32.UnhookWindowsHookEx(self._low_level_hook)
            except Exception:
                pass
            self._low_level_hook = None
            self._hook_callback = None
            logger.info("Low-level keyboard hook removed")

    def _apply_full_hooks(self) -> None:
        """Fallback hooks using the keyboard/mouse libraries, blocking everything including Escape."""
        logger.info("Applying FULL input lockdown - blocking ALL input")

        if self._keyboard_available and self.keyboard:
            try:
                self.keyboard.hook(lambda e: False, suppress=True)
                self._keyboard_hook_active = True
                logger.info("Full keyboard hook active - ALL keys blocked (including Escape)")
            except Exception as e:
                logger.error(f"Keyboard hook failed: {e}")

        if self._mouse_available and self.mouse:
            try:
                self.mouse.hook(lambda e: False)
                self._mouse_hook_active = True
                logger.info("Mouse hook active - ALL mouse input blocked")
            except Exception as e:
                logger.error(f"Mouse hook failed: {e}")

    def get_status(self) -> dict:
        return {
            "locked": self._locked,
            "block_input_active": self._block_input_active,
            "keyboard_hook_active": self._keyboard_hook_active,
            "mouse_hook_active": self._mouse_hook_active,
            "kbd_device_disabled": self._kbd_disable_active,
            "kbd_device_api_available": self._kbd_disabler.available,
            "keyboard_available": self.keyboard_available,
            "mouse_available": self.mouse_available,
            "windows_api": self._windows_api_available,
            "low_level_hook_installed": self._low_level_hook is not None,
            "lock_duration": time.time() - self._lock_start_time if self._locked else 0,
        }
