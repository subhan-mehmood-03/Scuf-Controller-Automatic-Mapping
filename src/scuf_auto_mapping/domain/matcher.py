from dataclasses import dataclass

from .models import Foreground, Profile, normalized


@dataclass(frozen=True)
class Match:
    profile: Profile | None = None
    conflict: bool = False


def match(foreground: Foreground, profiles: list[Profile]) -> Match:
    enabled = [p for p in profiles if p.enabled]
    exact = [
        p
        for p in enabled
        if foreground.path
        and p.executable_path
        and normalized(p.executable_path) == normalized(foreground.path)
    ]
    candidates = exact or [
        p
        for p in enabled
        if foreground.name and p.executable_name.casefold() == foreground.name.casefold()
    ]
    return Match(candidates[0] if len(candidates) == 1 else None, len(candidates) > 1)


def warnings(profiles: list[Profile]) -> list[str]:
    result = []
    for index, p in enumerate(profiles):
        for other in profiles[index + 1 :]:
            if p.executable_name.casefold() == other.executable_name.casefold():
                result.append(
                    f"{p.game_name} / {other.game_name}: duplicate basename; fallback ambiguous"
                )
            if p.executable_path and normalized(p.executable_path) == normalized(
                other.executable_path
            ):
                result.append(
                    f"{p.game_name} / {other.game_name}: duplicate path; exact match conflict"
                )
    return result
