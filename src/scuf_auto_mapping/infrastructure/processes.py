from dataclasses import dataclass
from typing import Callable, Protocol

import psutil


@dataclass(frozen=True)
class Process:
    name: str
    path: str = ""


def running_processes() -> list[Process]:
    result = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            result.append(Process(process.info["name"] or "", process.info["exe"] or ""))
        except (psutil.Error, OSError):
            continue
    return result


class ICueStatusProvider(Protocol):
    def get_process_status(self) -> str: ...


class ProcessStatusProvider:
    def __init__(
        self, names: list[str], enumerate_processes: Callable[[], list[Process]] = running_processes
    ):
        self.names = {n.strip().casefold() for n in names if n.strip()}
        self.enumerate = enumerate_processes
        self.detected_path = ""

    def get_process_status(self) -> str:
        try:
            processes = self.enumerate()
            matches = [p for p in processes if p.name.casefold() in self.names]
            self.detected_path = next((p.path for p in matches if p.path), "")
            return "detected" if matches else "not detected"
        except Exception:
            self.detected_path = ""
            return "unknown"
