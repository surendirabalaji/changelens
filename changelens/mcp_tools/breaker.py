import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from changelens.config import get_settings
from changelens.errors import TRANSIENT_KINDS, FailureKind


@dataclass
class _ServerState:
    failures: int = 0
    opened_at: float | None = None
    probe_in_flight: bool = False


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        cooldown_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be non-negative")

        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._servers: dict[str, _ServerState] = {}

    def _state_for(self, server: str) -> _ServerState:
        if server not in self._servers:
            self._servers[server] = _ServerState()
        return self._servers[server]

    def allow(self, server: str) -> bool:
        state = self._state_for(server)

        # Closed: allow normal requests.
        if state.opened_at is None:
            return True

        # Half-open: only one probe may run.
        if state.probe_in_flight:
            return False

        # Open: wait until the cooldown has passed.
        elapsed = self._clock() - state.opened_at
        if elapsed < self._cooldown_s:
            return False

        # Reserve the single half-open probe.
        state.probe_in_flight = True
        return True

    def record_success(self, server: str) -> None:
        state = self._state_for(server)
        state.failures = 0
        state.opened_at = None
        state.probe_in_flight = False

    def record_failure(self, server: str, kind: FailureKind) -> None:
        state = self._state_for(server)

        # Ignore late failures while open; preserve the original cooldown.
        if state.opened_at is not None and not state.probe_in_flight:
            return

        if kind not in TRANSIENT_KINDS:
            if state.probe_in_flight:
                # A non-transient reply proves the server is reachable.
                self.record_success(server)
            return

        state.failures += 1

        if (
            state.probe_in_flight
            or state.failures >= self._failure_threshold
        ):
            state.opened_at = self._clock()
            state.probe_in_flight = False
    def release_probe(self, server: str) -> None:
        # Frees a reserved probe without counting a failure or a success.
        self._state_for(server).probe_in_flight = False
@lru_cache(maxsize=1)
def get_breaker() -> CircuitBreaker:
    settings = get_settings()
    return CircuitBreaker(
        failure_threshold=settings.breaker_failure_threshold,
        cooldown_s=settings.breaker_cooldown_s,
    )