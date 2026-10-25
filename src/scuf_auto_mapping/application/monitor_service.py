from typing import Protocol

from scuf_auto_mapping.domain.matcher import Match, match
from scuf_auto_mapping.domain.models import Foreground, Profile


class ForegroundProvider(Protocol):
    def observe(self) -> Foreground: ...


class MonitorService:
    """Pure two-observation debounce. Worker owns this instance; UI receives snapshots."""

    def __init__(self, provider: ForegroundProvider) -> None:
        self.provider = provider
        self.paused = False
        self.candidate: Foreground | None = None
        self.count = 0
        self.current = Foreground()
        self.result = Match()
        self.last_key: tuple = ()

    def pause(self, value: bool) -> None:
        self.paused = value
        self.candidate = None
        self.count = 0

    def poll(self, profiles: list[Profile]) -> tuple[Foreground, Match, bool]:
        if self.paused:
            return self.current, self.result, False
        try:
            observed = self.provider.observe()
        except Exception:
            observed = Foreground(error="Foreground query failed; process may be inaccessible")
        if observed == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = observed, 1
        if self.count < 2:
            return self.current, self.result, False
        self.current = observed
        self.result = match(observed, profiles)
        key = (
            self.result.profile.id if self.result.profile else None,
            self.result.conflict,
            observed.error,
        )
        changed = key != self.last_key
        self.last_key = key
        return observed, self.result, changed
