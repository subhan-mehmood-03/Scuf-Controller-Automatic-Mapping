from __future__ import annotations

import ntpath
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path)) if path else ""


def text(value: object, name: str, limit: int = 256, empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError(f"{name} must be text without NUL characters")
    value = value.strip()
    if len(value) > limit or (not value and not empty):
        raise ValueError(f"{name}: required, maximum {limit} characters")
    return value


@dataclass
class Profile:
    game_name: str
    executable_name: str
    icue_profile_name: str
    executable_path: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    enabled: bool = True
    linked_app_attested_at: str | None = None
    mapping_test_attested_at: str | None = None
    notes: str = ""
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    def __post_init__(self) -> None:
        self.game_name = text(self.game_name, "Game name")
        self.icue_profile_name = text(self.icue_profile_name, "Profile name")
        self.executable_name = text(self.executable_name, "Executable name")
        if ntpath.basename(
            self.executable_name
        ) != self.executable_name or not self.executable_name.lower().endswith(".exe"):
            raise ValueError("Executable name must be a basename ending in .exe")
        self.executable_path = text(self.executable_path, "Executable path", 32767, True)
        if self.executable_path:
            drive, tail = ntpath.splitdrive(self.executable_path)
            if not drive or not tail.startswith(("\\", "/")):
                raise ValueError("Executable path must be absolute")
            if normalized(ntpath.basename(self.executable_path)) != normalized(
                self.executable_name
            ):
                raise ValueError("Executable path and name disagree")
        if not isinstance(self.id, str):
            raise ValueError("ID must be a UUID string")
        UUID(self.id)
        if type(self.enabled) is not bool:
            raise ValueError("Enabled must be a boolean")
        self.notes = text(self.notes, "Notes", 10000, True)
        for name in (
            "created_at",
            "updated_at",
            "linked_app_attested_at",
            "mapping_test_attested_at",
        ):
            stamp = getattr(self, name)
            if stamp is None and name.endswith("attested_at"):
                continue
            if not isinstance(stamp, str) or datetime.fromisoformat(stamp).tzinfo is None:
                raise ValueError(f"{name} must be an ISO timestamp with timezone")
        if self.mapping_test_attested_at and not self.linked_app_attested_at:
            raise ValueError("Confirm the Linked App before confirming hardware testing")

    @property
    def state(self) -> str:
        if self.mapping_test_attested_at:
            return "User confirmed tested"
        return "User confirmed linked" if self.linked_app_attested_at else "Not configured"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Foreground:
    path: str = ""
    name: str = ""
    error: str = ""


@dataclass(frozen=True)
class ProfileActivationEvidence:
    expected_profile: str | None = None
    active_in_icue: str = "unknown"
    source: str = "iCUE native Linked App; user attestation only"


@dataclass
class Settings:
    interval_ms: int = 1000
    notifications: bool = False
    minimize_to_tray: bool = False
    autostart: bool = False
    retention_days: int = 30
    event_limit: int = 5000
    default_profile: str = ""
    icue_names: str = "icue.exe,corsair.icue.exe"
    exclusions: str = "idle,system,explorer.exe,searchhost.exe,startmenuexperiencehost.exe"
    onboarding_complete: bool = False

    def __post_init__(self) -> None:
        for name, low, high in (
            ("interval_ms", 250, 10000),
            ("retention_days", 1, 30),
            ("event_limit", 100, 5000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        for name in ("notifications", "minimize_to_tray", "autostart", "onboarding_complete"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        self.default_profile = text(self.default_profile, "Default profile", 256, True)
        for name in ("icue_names", "exclusions"):
            value = text(getattr(self, name), name, 2048, True)
            if any(ntpath.basename(n.strip()) != n.strip() for n in value.split(",")):
                raise ValueError("Process lists accept basenames only")
            setattr(self, name, value)
