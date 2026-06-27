"""
HardLock – system‑wide input blocking at device level.
Now also suppresses Win key, Alt+Tab, and Ctrl+Esc via a low‑level keyboard hook.
"""
import ctypes
import logging
import time
import atexit
from ctypes import wintypes, byref, POINTER

logger = logging.getLogger("BambiBrowser.HardLock")

# Windows API constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

# KBDLLHOOKSTRUCT structure
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class HardLock:
    def __init__(self):
        self._locked = False
        self._block_input_active = False
        self._keyboard_hook_active = False
        self._mouse_hook_active = False
        self._low_level_hook = None
        self._hook_callback = None
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
        logger.info("🔒 HardLock ENABLED – all input blocked (including Win key, Alt+Tab)")

        # Always install low‑level keyboard hook to catch system keys
        self._install_low_level_hook()

        # Use BlockInput for general input blocking
        if self._windows_api_available:
            try:
                if self._BlockInput(True):
                    self._block_input_active = True
                    logger.info("BlockInput activated")
                else:
                    logger.warning("BlockInput failed – using fallback hooks")
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

        # Uninstall low‑level hook
        self._uninstall_low_level_hook()

        if self._block_input_active:
            try:
                self._BlockInput(False)
            except:
                pass
            self._block_input_active = False

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

    # ------------------ Low‑level keyboard hook ------------------
    def _install_low_level_hook(self) -> None:
        """Install a low‑level keyboard hook that suppresses Win key, Alt+Tab, Ctrl+Esc."""
        if self._low_level_hook is not None:
            return  # already installed

        # Define the callback
        def low_level_handler(nCode, wParam, lParam):
            if nCode >= 0:
                # lParam is a pointer to KBDLLHOOKSTRUCT
                kb = KBDLLHOOKSTRUCT.from_address(lParam)
                vk = kb.vkCode

                # Suppress Windows key (left and right)
                if vk in (VK_LWIN, VK_RWIN):
                    return 1  # block the key

                # Suppress Alt+Tab (Alt down + Tab)
                if vk == VK_TAB:
                    if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
                        return 1

                # Suppress Ctrl+Esc (opens Start menu)
                if vk == VK_ESCAPE:
                    if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                        return 1

            # Pass through to next hook
            return user32.CallNextHookExW(None, nCode, wParam, lParam)

        # Keep a reference to the callback to prevent GC
        from ctypes import CFUNCTYPE, c_int
        self._hook_callback = CFUNCTYPE(c_int, c_int, wintypes.WPARAM, wintypes.LPARAM)(low_level_handler)

        # Install the hook
        self._low_level_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_callback,
            kernel32.GetModuleHandleW(None),
            0
        )

        if self._low_level_hook:
            logger.info("Low‑level keyboard hook installed (blocks Win, Alt+Tab, Ctrl+Esc)")
        else:
            logger.warning("Failed to install low‑level keyboard hook")

    def _uninstall_low_level_hook(self) -> None:
        """Uninstall the low‑level keyboard hook."""
        if self._low_level_hook:
            try:
                user32.UnhookWindowsHookEx(self._low_level_hook)
            except:
                pass
            self._low_level_hook = None
            self._hook_callback = None
            logger.info("Low‑level keyboard hook removed")

    # ------------------ Fallback hooks (keyboard/mouse) ------------------
    def _apply_full_hooks(self) -> None:
        """Apply additional fallback hooks using keyboard/mouse libraries."""
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

    # ------------------ Status ------------------
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
            "low_level_hook_installed": self._low_level_hook is not None,
        }