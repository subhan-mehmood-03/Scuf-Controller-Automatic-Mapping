from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from scuf_auto_mapping.domain.models import Profile, Settings, now


class Repository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        try:
            if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Database integrity check failed")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("Database is newer than this application; use a newer app")
            with self.db:
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, message TEXT NOT NULL)"
                )
                self.db.execute("PRAGMA user_version=1")
        except Exception:
            self.db.close()
            raise

    def profiles(self) -> list[Profile]:
        return [
            Profile(**json.loads(row[0]))
            for row in self.db.execute("SELECT data FROM profiles ORDER BY id")
        ]

    def save(self, profile: Profile) -> None:
        self.save_many([profile])

    def save_many(self, profiles: list[Profile]) -> None:
        validated = [Profile(**p.to_dict()) for p in profiles]
        with self.db:
            self.db.executemany(
                "INSERT INTO profiles(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                [(p.id, json.dumps(p.to_dict(), ensure_ascii=False)) for p in validated],
            )

    def delete(self, identity: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM profiles WHERE id=?", (identity,))

    def settings(self) -> Settings:
        row = self.db.execute("SELECT data FROM settings WHERE id=1").fetchone()
        return Settings(**json.loads(row[0])) if row else Settings()

    def save_settings(self, settings: Settings) -> None:
        validated = Settings(**asdict(settings))
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES (1,?)", (json.dumps(asdict(validated)),)
            )

    def event(self, message: str) -> None:
        settings = self.settings()
        with self.db:
            self.db.execute("INSERT INTO events(at,message) VALUES (?,?)", (now(), message[:2000]))
            self.db.execute(
                "DELETE FROM events WHERE julianday(at) < julianday('now') - ?",
                (settings.retention_days,),
            )
            self.db.execute(
                "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (settings.event_limit,),
            )

    def events(self, query: str = "") -> list[tuple[str, str]]:
        return self.db.execute(
            "SELECT at,message FROM events WHERE instr(lower(message),lower(?)) > 0 ORDER BY id DESC",
            (query,),
        ).fetchall()

    def backup(self, destination: Path) -> None:
        if destination.resolve() == self.path.resolve():
            raise ValueError("Backup must have a different destination")
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def close(self) -> None:
        self.db.close()
