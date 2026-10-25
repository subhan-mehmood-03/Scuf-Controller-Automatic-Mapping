import json
import os
import tempfile
from pathlib import Path

from scuf_auto_mapping.domain.models import Profile, normalized

MAX_BYTES = 5 * 1024 * 1024
MAX_PROFILES = 10000


def atomic_write(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def export_profiles(path: Path, profiles: list[Profile]) -> None:
    data = json.dumps(
        {"schema_version": 1, "profiles": [p.to_dict() for p in profiles]},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    if len(data) > MAX_BYTES or len(profiles) > MAX_PROFILES:
        raise ValueError("Export exceeds supported import limits; export smaller groups")
    atomic_write(path, data)


def load_profiles(path: Path) -> list[Profile]:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("JSON exceeds 5 MB")
    try:
        value = json.loads(data)
        if not isinstance(value, dict) or set(value) != {"schema_version", "profiles"}:
            raise ValueError("Expected schema_version and profiles")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported schema_version")
        rows = value["profiles"]
        if not isinstance(rows, list) or len(rows) > MAX_PROFILES:
            raise ValueError("Expected at most 10000 profiles")
        profiles = [Profile(**row) for row in rows]
        if len({p.id for p in profiles}) != len(profiles):
            raise ValueError("Duplicate IDs within import; resolve before importing")
        return profiles
    except (TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"Invalid profile JSON: {exc}") from exc


def preview(incoming: list[Profile], existing: list[Profile]) -> str:
    ids = {p.id for p in existing}
    paths = {normalized(p.executable_path) for p in existing if p.executable_path}
    return (
        f"{len(incoming)} records; {sum(p.id in ids for p in incoming)} existing IDs. "
        f"{sum(bool(p.executable_path) and normalized(p.executable_path) in paths for p in incoming)} "
        "existing executable paths. Choose Replace IDs, Skip IDs, or Cancel. "
        "Different IDs with identical paths remain conflicts and will not be guessed."
    )
