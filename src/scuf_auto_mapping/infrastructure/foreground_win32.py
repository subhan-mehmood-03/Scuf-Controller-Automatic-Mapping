"""Query-only Win32 adapter; no hooks, process memory, or elevation."""

import ctypes
import ntpath
import sys
from ctypes import wintypes

from scuf_auto_mapping.domain.models import Foreground


class WindowsForegroundProvider:
    def observe(self) -> Foreground:
        if sys.platform != "win32":
            return Foreground(error="Foreground detection requires Windows")
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        hwnd = user.GetForegroundWindow()
        if not hwnd:
            return Foreground()
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return Foreground(error=f"Process inaccessible (Win32 {ctypes.get_last_error()})")
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return Foreground(error=f"Path unavailable (Win32 {ctypes.get_last_error()})")
            return Foreground(buffer.value, ntpath.basename(buffer.value))
        finally:
            kernel.CloseHandle(handle)
