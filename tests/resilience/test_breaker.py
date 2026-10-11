from changelens.mcp_tools.breaker import CircuitBreaker
from changelens.errors import FailureKind


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_two_transport_failures_open_breaker() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    assert breaker.allow("github") is False


def test_non_transient_failures_leave_breaker_closed() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    for _ in range(10):
        for kind in (
            FailureKind.NOT_FOUND,
            FailureKind.AUTH,
            FailureKind.INVALID_ARGUMENTS,
        ):
            breaker.record_failure("github", kind)
            assert breaker.allow("github") is True


def test_open_breaker_blocks_before_cooldown() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    clock.now += 29

    assert breaker.allow("github") is False


def test_only_one_probe_allowed_after_cooldown() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    clock.now += 31

    assert breaker.allow("github") is True
    assert breaker.allow("github") is False


def test_successful_probe_closes_breaker() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    clock.now += 31
    assert breaker.allow("github") is True

    breaker.record_success("github")

    for _ in range(5):
        assert breaker.allow("github") is True


def test_failed_probe_restarts_cooldown() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    clock.now += 31
    assert breaker.allow("github") is True

    breaker.record_failure("github", FailureKind.TRANSPORT)
    assert breaker.allow("github") is False

    clock.now += 29
    assert breaker.allow("github") is False

    clock.now += 2
    assert breaker.allow("github") is True


def test_servers_have_independent_breakers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_failure("github", FailureKind.TRANSPORT)

    assert breaker.allow("github") is False
    assert breaker.allow("tavily") is True


def test_success_resets_consecutive_failure_count() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(2, 30.0, clock)

    breaker.record_failure("github", FailureKind.TRANSPORT)
    breaker.record_success("github")
    breaker.record_failure("github", FailureKind.TRANSPORT)

    assert breaker.allow("github") is True