"""
HardLock – system‑wide input blocking at device level.
"""
import ctypes
import logging
import time
import atexit
from ctypes import wintypes, byref, POINTER

logger = logging.getLogger("BambiBrowser.HardLock")

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT),
                ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD),
                ("hwndTarget", wintypes.HWND)]

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class HardLock:
    def __init__(self):
        self._locked = False
        self._block_input_active = False
        self._keyboard_hook_active = False
        self._mouse_hook_active = False
        self._low_level_hook = None
        self._lock_start_time = 0.0
        try:
            self._BlockInput = user32.BlockInput
            self._BlockInput.argtypes = [ctypes.c_bool]
            self._BlockInput.restype = ctypes.c_bool
            self._windows_api_available = True
        except Exception:
            self._windows_api_available = False
            logger.warning("BlockInput API not available")
        self._keyboard_available = False
        self._mouse_available = False
        try:
            import keyboard
            self.keyboard = keyboard
            self._keyboard_available = True
        except ImportError:
            pass
        try:
            import mouse
            self.mouse = mouse
            self._mouse_available = True
        except ImportError:
            pass
        atexit.register(self.unlock)

    @property
    def is_locked(self) -> bool:
        return self._locked

    def lock(self) -> None:
        if self._locked:
            return
        self._locked = True
        self._lock_start_time = time.time()
        logger.info("🔒 HardLock ENABLED – all input blocked")
        if self._windows_api_available:
            try:
                if self._BlockInput(True):
                    self._block_input_active = True
                    logger.info("BlockInput activated")
                else:
                    logger.warning("BlockInput failed – using hooks")
                    self._apply_full_hooks()
            except Exception as e:
                logger.error(f"BlockInput error: {e}")
                self._apply_full_hooks()
        else:
            self._apply_full_hooks()

    def unlock(self) -> None:
        if not self._locked:
            return
        logger.info("Releasing HardLock...")
        if self._block_input_active:
            try:
                self._BlockInput(False)
            except:
                pass
            self._block_input_active = False
        if self._low_level_hook:
            try:
                user32.UnhookWindowsHookEx(self._low_level_hook)
            except:
                pass
            self._low_level_hook = None
        if self._keyboard_hook_active and hasattr(self, 'keyboard'):
            try:
                self.keyboard.unhook_all()
            except:
                pass
            self._keyboard_hook_active = False
        if self._mouse_hook_active and hasattr(self, 'mouse'):
            try:
                self.mouse.unhook_all()
            except:
                pass
            self._mouse_hook_active = False
        try:
            user32.SystemParametersInfoW(0x97, 0, 0, 0)  # SPI_SETSCREENSAVERRUNNING
        except:
            pass
        self._locked = False
        logger.info("🔓 HardLock released – input restored")

    def force_unlock(self) -> None:
        logger.warning("Emergency unlock triggered")
        self.unlock()

    def _apply_full_hooks(self) -> None:
        logger.info("Applying fallback hooks – full input lockdown")
        if self._keyboard_available and hasattr(self, 'keyboard'):
            try:
                self.keyboard.hook(lambda e: False, suppress=True)
                self._keyboard_hook_active = True
                logger.info("Keyboard hook active")
            except Exception as e:
                logger.error(f"Keyboard hook failed: {e}")
        if self._mouse_available and hasattr(self, 'mouse'):
            try:
                self.mouse.hook(lambda e: False)
                self._mouse_hook_active = True
                logger.info("Mouse hook active")
            except Exception as e:
                logger.error(f"Mouse hook failed: {e}")
        try:
            WH_KEYBOARD_LL = 13
            LLKHF_ALTDOWN = 0x20
            def low_level_handler(nCode, wParam, lParam):
                return 1 if nCode >= 0 else user32.CallNextHookExW(None, nCode, wParam, lParam)
            from ctypes import CFUNCTYPE, c_int
            callback = CFUNCTYPE(c_int, c_int, wintypes.WPARAM, wintypes.LPARAM)(low_level_handler)
            self._low_level_hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                callback,
                kernel32.GetModuleHandleW(None),
                0
            )
            if self._low_level_hook:
                logger.info("Low‑level keyboard hook active")
        except Exception as e:
            logger.warning(f"Low‑level hook failed: {e}")

    def get_status(self) -> dict:
        return {
            "locked": self._locked,
            "block_input_active": self._block_input_active,
            "keyboard_hook_active": self._keyboard_hook_active,
            "mouse_hook_active": self._mouse_hook_active,
            "keyboard_available": self._keyboard_available,
            "mouse_available": self._mouse_available,
            "windows_api": self._windows_api_available,
            "lock_duration": time.time() - self._lock_start_time if self._locked else 0,
        }