import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from scuf_auto_mapping.application.monitor_service import MonitorService
from scuf_auto_mapping.domain.matcher import match, warnings
from scuf_auto_mapping.domain.models import Foreground, Profile, Settings, now
from scuf_auto_mapping.infrastructure import import_export as exchange
from scuf_auto_mapping.infrastructure.processes import (
    Process,
    ProcessStatusProvider,
    running_processes,
)
from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.infrastructure.system import (
    configure_logging,
    data_directory,
    export_diagnostics,
    redact,
    set_autostart,
)


@pytest.fixture
def profile():
    return Profile("Game 雪", "game.exe", "Competitive", r"C:\Games\game.exe")


def test_matching(profile):
    other = replace(
        profile, id="00000000-0000-0000-0000-000000000001", executable_path=r"D:\game.exe"
    )
    assert match(Foreground(r"c:/GAMES/game.EXE", "game.exe"), [profile, other]).profile == profile
    assert match(Foreground(name="GAME.EXE"), [profile]).profile == profile
    assert match(Foreground(name="game.exe"), [profile, other]).conflict
    assert match(
        Foreground(profile.executable_path, "game.exe"),
        [profile, replace(other, executable_path=profile.executable_path)],
    ).conflict
    assert match(Foreground(name="game.exe"), [replace(profile, enabled=False)]).profile is None
    assert match(Foreground(name="mygame.exe"), [profile]).profile is None
    assert match(Foreground(), [profile]).profile is None
    assert len(warnings([profile, replace(other, executable_path=profile.executable_path)])) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("game_name", " "),
        ("icue_profile_name", ""),
        ("executable_name", "a/game.exe"),
        ("executable_name", "game.bat"),
        ("executable_path", "game.exe"),
        ("executable_path", r"C:\other.exe"),
        ("enabled", 1),
        ("id", "bad"),
        ("notes", "x" * 10001),
        ("game_name", None),
        ("created_at", "2026-01-01"),
        ("mapping_test_attested_at", "2026-01-01T00:00:00+00:00"),
        ("game_name", "bad\x00name"),
    ],
)
def test_validation(profile, field, value):
    with pytest.raises((ValueError, TypeError)):
        replace(profile, **{field: value})


def test_attestation(profile):
    assert profile.state == "Not configured"
    profile = replace(profile, linked_app_attested_at=now())
    assert profile.state == "User confirmed linked"
    assert replace(profile, mapping_test_attested_at=now()).state == "User confirmed tested"


class FakeForeground:
    value = Foreground(name="game.exe")

    def observe(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_monitor(profile):
    provider = FakeForeground()
    monitor = MonitorService(provider)
    assert not monitor.poll([profile])[2]
    assert monitor.poll([profile])[2]
    assert not monitor.poll([profile])[2]
    provider.value = Foreground(name="desktop.exe")
    assert monitor.poll([profile])[1].profile == profile
    provider.value = Foreground(name="game.exe")
    monitor.poll([profile])
    assert not monitor.poll([profile])[2]
    monitor.pause(True)
    provider.value = Foreground()
    assert not monitor.poll([profile])[2]
    monitor.pause(False)
    assert not monitor.poll([profile])[2]
    assert monitor.poll([profile])[2]
    provider.value = RuntimeError("gone")
    monitor.poll([profile])
    assert monitor.poll([profile])[0].error


def test_repository(tmp_path, profile):
    path = tmp_path / "db.sqlite"
    repo = Repository(path)
    assert repo.settings() == Settings()
    repo.save(profile)
    repo.save(replace(profile, notes="updated"))
    assert len(repo.profiles()) == 1
    assert repo.profiles()[0].notes == "updated"
    repo.save_settings(Settings(event_limit=100, retention_days=1))
    for i in range(105):
        repo.event(f"Event {i}")
    assert len(repo.events()) == 100
    assert len(repo.events("104")) == 1
    repo.db.execute("INSERT INTO events(at,message) VALUES ('2000-01-01','old')")
    repo.event("new")
    assert not repo.events("old")
    invalid = replace(profile)
    invalid.game_name = ""
    with pytest.raises(ValueError):
        repo.save_many([replace(profile, notes="should rollback"), invalid])
    assert repo.profiles()[0].notes == "updated"
    with pytest.raises(ValueError):
        repo.backup(path)
    repo.backup(tmp_path / "backup.db")
    repo.close()
    reopened = Repository(path)
    assert reopened.settings().event_limit == 100
    assert reopened.profiles()[0].id == profile.id
    reopened.delete(profile.id)
    assert not reopened.profiles()
    reopened.close()
    backup = Repository(tmp_path / "backup.db")
    assert backup.profiles()
    backup.close()


def test_corruption_and_future_schema(tmp_path):
    path = tmp_path / "bad.db"
    path.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        Repository(path)
    assert path.read_bytes() == b"not sqlite"
    future = tmp_path / "future.db"
    connection = sqlite3.connect(future)
    with connection:
        connection.execute("PRAGMA user_version=99")
    connection.close()
    with pytest.raises(ValueError):
        Repository(future)


def test_json(tmp_path, profile, monkeypatch):
    path = tmp_path / "profiles.json"
    exchange.export_profiles(path, [profile])
    assert exchange.load_profiles(path) == [profile]
    assert "1 existing IDs" in exchange.preview([profile], [profile])
    minimal = profile.to_dict()
    for field in ("created_at", "updated_at", "linked_app_attested_at", "mapping_test_attested_at"):
        minimal.pop(field)
    path.write_text(json.dumps({"schema_version": 1, "profiles": [minimal]}), encoding="utf-8")
    assert exchange.load_profiles(path)[0].linked_app_attested_at is None
    monkeypatch.setattr(exchange.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    before = path.read_bytes()
    with pytest.raises(OSError):
        exchange.export_profiles(path, [profile])
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"schema_version": True, "profiles": []},
        {"schema_version": 2, "profiles": []},
        {"schema_version": 1, "profiles": {}},
        {"schema_version": 1, "profiles": [{}]},
        {"schema_version": 1, "profiles": [3]},
    ],
)
def test_invalid_json(tmp_path, value):
    path = tmp_path / "x.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        exchange.load_profiles(path)


def test_limits_and_duplicates(tmp_path, profile, monkeypatch):
    path = tmp_path / "x.json"
    path.write_text("{")
    with pytest.raises(ValueError):
        exchange.load_profiles(path)
    exchange.export_profiles(path, [profile, profile])
    with pytest.raises(ValueError, match="Duplicate"):
        exchange.load_profiles(path)
    monkeypatch.setattr(exchange, "MAX_BYTES", 2)
    with pytest.raises(ValueError):
        exchange.load_profiles(path)
    with pytest.raises(ValueError):
        exchange.export_profiles(path, [profile])


def test_presence():
    detected = ProcessStatusProvider(["iCUE.exe"], lambda: [Process("ICUE.EXE", r"C:\iCUE.exe")])
    assert detected.get_process_status() == "detected"
    assert detected.detected_path
    assert ProcessStatusProvider(["icue.exe"], lambda: []).get_process_status() == "not detected"

    def fail():
        raise OSError("denied")

    assert ProcessStatusProvider([], fail).get_process_status() == "unknown"
    assert isinstance(running_processes(), list)


@pytest.mark.parametrize(
    "values",
    [
        {"interval_ms": 1},
        {"event_limit": 5001},
        {"retention_days": 31},
        {"autostart": 1},
        {"notifications": "true"},
        {"icue_names": r"C:\bad.exe"},
    ],
)
def test_settings(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_autostart_privacy(tmp_path, monkeypatch):
    class Registry:
        value = None

        def set(self, value):
            self.value = value

    registry = Registry()
    exe = tmp_path / "app.exe"
    exe.touch()
    set_autostart(True, registry, exe, True)
    assert registry.value == f'"{exe}"'
    set_autostart(False, registry, exe, True)
    assert registry.value is None
    for path, packaged in (
        (exe, False),
        (Path("relative.exe"), True),
        (tmp_path / "missing.exe", True),
    ):
        with pytest.raises(ValueError):
            set_autostart(True, registry, path, packaged)
    content = str(Path.home()) + r" C:\Users\Someone\Games\game.exe"
    assert "Someone" not in redact(content)
    assert str(Path.home()) not in redact(content)
    target = tmp_path / "diagnostics.txt"
    export_diagnostics(target, content)
    assert "Someone" not in target.read_text()
    export_diagnostics(target, content, True)
    assert target.read_text() == content
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert data_directory() == tmp_path / "SCUFAutomaticMapping"
    configure_logging(tmp_path)
