import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

from .import_export import atomic_write


def data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "SCUFAutomaticMapping"


def configure_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "application.log", maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8"
    )
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )


def redact(value: str) -> str:
    value = re.sub(re.escape(str(Path.home())), "<HOME>", value, flags=re.IGNORECASE)
    return re.sub(r"(?i)([a-z]:[\\/]Users[\\/])[^\\/\s\"']+", r"\1<USER>", value)


def export_diagnostics(path: Path, content: str, raw: bool = False) -> None:
    atomic_write(path, (content if raw else redact(content)).encode("utf-8"))


class Registry(Protocol):
    def set(self, value: str | None) -> None: ...


class WindowsRegistry:
    def set(self, value: str | None) -> None:
        if sys.platform != "win32":
            raise ValueError("Autostart requires Windows")
        import winreg

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            if value is None:
                try:
                    winreg.DeleteValue(key, "SCUFAutomaticMapping")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, "SCUFAutomaticMapping", 0, winreg.REG_SZ, value)


def set_autostart(enabled: bool, registry: Registry, executable: Path, packaged: bool) -> None:
    if enabled:
        if not packaged:
            raise ValueError(
                "Autostart is available only in the packaged EXE; development launch is disabled"
            )
        if (
            not executable.is_absolute()
            or not executable.is_file()
            or executable.suffix.lower() != ".exe"
        ):
            raise ValueError("Autostart requires an existing absolute executable path")
        if '"' in str(executable):
            raise ValueError("Invalid executable path")
        registry.set(f'"{executable}"')
    else:
        registry.set(None)
