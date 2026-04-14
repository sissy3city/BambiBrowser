"""HardLock - Keyboard and mouse input blocking at device level."""

import logging
import ctypes
from ctypes import wintypes, byref, sizeof, c_ulong, c_bool, POINTER
from typing import Optional, List
import time

logger = logging.getLogger("BambiBrowser.HardLock")

# Windows API structures and constants
class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [
        ("hDevice", wintypes.HANDLE),
        ("dwType", wintypes.DWORD),
    ]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]

# Device types
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID = 2

# Flags
RIDEV_REMOVE = 0x00000001
RIDEV_EXCLUDE = 0x00000010

# BlockInput function
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class HardLock:
    """Atomic input lock - completely blocks keyboard and mouse at device level."""
    
    def __init__(self):
        self._locked = False
        self._block_input_active = False
        self._keyboard_hook_active = False
        self._mouse_hook_active = False
        self._lock_start_time = 0.0
        
        # Try to load Windows API functions
        try:
            self._BlockInput = user32.BlockInput
            self._BlockInput.argtypes = [c_bool]
            self._BlockInput.restype = c_bool
            
            self._GetRawInputDeviceList = user32.GetRawInputDeviceList
            self._GetRawInputDeviceList.argtypes = [POINTER(RAWINPUTDEVICELIST), POINTER(wintypes.UINT), wintypes.UINT]
            self._GetRawInputDeviceList.restype = wintypes.UINT
            
            self._RegisterRawInputDevices = user32.RegisterRawInputDevices
            self._RegisterRawInputDevices.argtypes = [POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
            self._RegisterRawInputDevices.restype = c_bool
            
            self._windows_api_available = True
            logger.info("Windows BlockInput API available")
        except Exception as e:
            logger.warning(f"Windows BlockInput API not available: {e}")
            self._windows_api_available = False
        
        # Fallback to Python libraries
        try:
            import keyboard
            self.keyboard = keyboard
            self._keyboard_available = True
            logger.info("Keyboard module loaded (fallback)")
        except ImportError:
            self._keyboard_available = False
            self.keyboard = None
        
        try:
            import mouse
            self.mouse = mouse
            self._mouse_available = True
            logger.info("Mouse module loaded (fallback)")
        except ImportError:
            self._mouse_available = False
            self.mouse = None
    
    @property
    def is_locked(self) -> bool:
        return self._locked
    
    @property
    def keyboard_available(self) -> bool:
        return self._windows_api_available or self._keyboard_available
    
    @property
    def mouse_available(self) -> bool:
        return self._windows_api_available or self._mouse_available
    
    def lock(self):
        """Enable atomic input lock - NO ESCAPE."""
        if self._locked:
            return
        
        self._locked = True
        self._lock_start_time = time.time()
        logger.info("🔒 HardLock enabled - NO ESCAPE, system input COMPLETELY BLOCKED")
        
        if self._windows_api_available:
            try:
                result = self._BlockInput(True)
                if result:
                    self._block_input_active = True
                    logger.info("BlockInput activated")
                else:
                    logger.warning("BlockInput failed - might need admin rights")
                    self._apply_full_hooks()
            except Exception as e:
                logger.error(f"BlockInput error: {e}")
                self._apply_full_hooks()
        else:
            self._apply_full_hooks()
    
    def _apply_full_hooks(self):
        """Apply hooks that block EVERYTHING including Escape, Ctrl+Alt+Del, Win key."""
        logger.info("Applying FULL input lockdown - blocking ALL input")
        
        # Block ALL keyboard input including Escape and system keys
        if self._keyboard_available and self.keyboard:
            try:
                # Block ALL keys without exception
                self.keyboard.hook(lambda e: False, suppress=True)
                self._keyboard_hook_active = True
                logger.info("Full keyboard hook active - ALL keys blocked (including Escape)")
            except Exception as e:
                logger.error(f"Keyboard hook failed: {e}")
        
        # Block ALL mouse input
        if self._mouse_available and self.mouse:
            try:
                self.mouse.hook(lambda e: False)
                self._mouse_hook_active = True
                logger.info("Mouse hook active - ALL mouse input blocked")
            except Exception as e:
                logger.error(f"Mouse hook failed: {e}")
        
        # Disable system keys (Windows key, Alt+Tab, Ctrl+Alt+Del)
        try:
            # Disable Windows key and system hotkeys
            ctypes.windll.user32.SystemParametersInfoW(0x97, 1, 0, 0)  # SPI_SETSCREENSAVERRUNNING
            logger.info("System keys disabled")
        except:
            pass
        
        # Additional: Block Alt+Tab and other system combos via low-level hook
        try:
            from ctypes import wintypes, CFUNCTYPE, c_int
            
            WH_KEYBOARD_LL = 13
            LLKHF_ALTDOWN = 0x20
            
            self._low_level_hook = None
            
            def low_level_keyboard_handler(nCode, wParam, lParam):
                if nCode >= 0:
                    # Block all keys - no exceptions
                    return 1  # Block the key
                return ctypes.windll.user32.CallNextHookExW(None, nCode, wParam, lParam)
            
            self._low_level_keyboard_callback = CFUNCTYPE(c_int, c_int, wintypes.WPARAM, wintypes.LPARAM)(
                low_level_keyboard_handler
            )
            
            self._low_level_hook = ctypes.windll.user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._low_level_keyboard_callback,
                kernel32.GetModuleHandleW(None),
                0
            )
            
            if self._low_level_hook:
                logger.info("Low-level keyboard hook active - system hotkeys blocked")
        except Exception as e:
            logger.warning(f"Low-level hook failed: {e}")
    
    def unlock(self):
        """Disable atomic input lock."""
        if not self._locked:
            return
        
        logger.info("Releasing HardLock...")
        
        # Release BlockInput
        if self._block_input_active:
            try:
                self._BlockInput(False)
                self._block_input_active = False
                logger.info("BlockInput released")
            except Exception as e:
                logger.error(f"Failed to release BlockInput: {e}")
        
        # Re-enable Windows key and system keys
        try:
            ctypes.windll.user32.SystemParametersInfoW(0x97, 0, 0, 0)
            logger.info("System keys restored")
        except:
            pass
        
        # Remove low-level keyboard hook
        if hasattr(self, '_low_level_hook') and self._low_level_hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._low_level_hook)
                self._low_level_hook = None
                logger.info("Low-level keyboard hook removed")
            except Exception as e:
                logger.error(f"Failed to remove low-level hook: {e}")
        
        # Remove keyboard hooks
        if self._keyboard_hook_active and self.keyboard:
            try:
                self.keyboard.unhook_all()
                self._keyboard_hook_active = False
                logger.info("Keyboard hooks removed")
            except Exception as e:
                logger.error(f"Failed to remove keyboard hooks: {e}")
        
        # Remove mouse hooks
        if self._mouse_hook_active and self.mouse:
            try:
                self.mouse.unhook_all()
                self._mouse_hook_active = False
                logger.info("Mouse hooks removed")
            except Exception as e:
                logger.error(f"Failed to remove mouse hooks: {e}")
        
        self._locked = False
        logger.info("HardLock disabled - system input restored")
    
    def force_unlock(self):
        """Emergency unlock - for internal use only."""
        logger.warning("Emergency unlock triggered")
        self.unlock()
    
    def get_status(self) -> dict:
        """Get current status."""
        return {
            "locked": self._locked,
            "block_input_active": self._block_input_active,
            "keyboard_hook_active": self._keyboard_hook_active,
            "mouse_hook_active": self._mouse_hook_active,
            "keyboard_available": self.keyboard_available,
            "mouse_available": self.mouse_available,
            "windows_api": self._windows_api_available,
            "lock_duration": time.time() - self._lock_start_time if self._locked else 0,
        }