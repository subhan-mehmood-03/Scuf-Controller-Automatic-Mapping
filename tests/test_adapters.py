import ctypes
import sys
from types import SimpleNamespace

import pytest

from scuf_auto_mapping.infrastructure import foreground_win32 as foreground
from scuf_auto_mapping.infrastructure import processes, system


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def test_foreground_mocked_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    closed = []

    def pid(hwnd, output):
        output._obj.value = 42

    def query(handle, flags, buffer, size):
        buffer.value = r"C:\Games\雪.exe"
        return 1

    user = SimpleNamespace(
        GetForegroundWindow=Function(lambda: 12), GetWindowThreadProcessId=Function(pid)
    )
    kernel = SimpleNamespace(
        OpenProcess=Function(lambda access, inherit, pid: 99),
        QueryFullProcessImageNameW=Function(query),
        CloseHandle=Function(closed.append),
    )
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name, **_: user if name == "user32" else kernel, raising=False
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    provider = foreground.WindowsForegroundProvider()
    assert provider.observe().name == "雪.exe"
    assert closed == [99]
    kernel.QueryFullProcessImageNameW.callback = lambda *_: 0
    assert "Path unavailable" in provider.observe().error
    assert closed == [99, 99]
    kernel.OpenProcess.callback = lambda *_: 0
    assert "inaccessible" in provider.observe().error
    user.GetForegroundWindow.callback = lambda: 0
    assert not provider.observe().path
    monkeypatch.setattr(sys, "platform", "linux")
    assert "Windows" in provider.observe().error


def test_registry_adapter(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls = []

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def missing(*_):
        raise FileNotFoundError

    fake = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        REG_SZ=1,
        CreateKey=lambda *_: Key(),
        SetValueEx=lambda *args: calls.append(args),
        DeleteValue=missing,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    registry = system.WindowsRegistry()
    registry.set('"C:\\app.exe"')
    assert calls[0][-1] == '"C:\\app.exe"'
    registry.set(None)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(ValueError):
        registry.set(None)


def test_process_access_denied(monkeypatch):
    class Denied:
        @property
        def info(self):
            raise processes.psutil.AccessDenied(42)

    monkeypatch.setattr(processes.psutil, "process_iter", lambda *_: [Denied()])
    assert processes.running_processes() == []


@pytest.mark.skipif(sys.platform != "win32", reason="Live read-only Win32 query requires Windows")
def test_real_foreground_read_only():
    # No focus manipulation: supports no foreground window / inaccessible desktop in CI.
    observation = foreground.WindowsForegroundProvider().observe()
    assert isinstance(observation.error, str)
    if observation.path:
        assert observation.name.lower().endswith(".exe")
