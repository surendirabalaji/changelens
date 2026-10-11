import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from changelens import graph
from changelens.config import Settings
from changelens.mcp_tools import session
from changelens.mcp_tools.breaker import CircuitBreaker
from changelens.mcp_tools.connections import ALLOWED_TOOLS


STUB_PATH = Path(__file__).with_name("stub_server.py")

STUB_TOOLS = frozenset({
    "stub_ok",
    "stub_slow",
    "stub_tool_error",
    "stub_malformed",
    "stub_die",
})


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class StubHandle:
    def __init__(
        self,
        port: int,
        http_fault: int | None = None,
    ) -> None:
        self.port = port
        self.http_fault = http_fault
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        if self.process is not None:
            raise RuntimeError("Stop the existing process before starting")

        command = [
            sys.executable,
            str(STUB_PATH),
            "--port",
            str(self.port),
        ]

        if self.http_fault is not None:
            command.extend(["--http-fault", str(self.http_fault)])

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + 10.0

        while time.monotonic() < deadline:
            exit_code = self.process.poll()

            if exit_code is not None:
                raise RuntimeError(
                    f"Stub exited during startup with code {exit_code}"
                )

            try:
                with socket.create_connection(
                    ("127.0.0.1", self.port),
                    timeout=0.1,
                ):
                    return
            except OSError:
                time.sleep(0.05)

        raise TimeoutError("Stub did not start within 10 seconds")

    def stop(self) -> None:
        if self.process is None:
            return

        process = self.process

        if process.poll() is None:
            process.terminate()

        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)

        self.process = None

    def restart(self) -> None:
        # Wait for the old process to exit before reusing its port.
        self.stop()
        self.start()


@pytest.fixture
def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def start_stub(request):
    def factory(
        port: int,
        http_fault: int | None = None,
    ) -> StubHandle:
        handle = StubHandle(port, http_fault)

        # Register before readiness polling so a failed start is cleaned up.
        request.addfinalizer(handle.stop)
        handle.start()

        return handle

    return factory


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def breaker(fake_clock, monkeypatch) -> CircuitBreaker:
    instance = CircuitBreaker(
        failure_threshold=2,
        cooldown_s=30.0,
        clock=fake_clock,
    )

    monkeypatch.setattr(session, "get_breaker", lambda: instance)
    monkeypatch.setattr(graph, "get_breaker", lambda: instance)

    return instance


@pytest.fixture
def use_stub(monkeypatch, breaker):
    settings = Settings(
        _env_file=None,
        mcp_connect_deadline_s=3.0,
        mcp_open_budget_s=20.0,
        mcp_retry_jitter_s=0.0,
        tool_call_timeout_s=0.5,
        tool_loop_stop_s=30.0,
    )

    monkeypatch.setattr(session, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "get_settings", lambda: settings)

    # Only the stub participates in these tests.
    # Mutate the shared dictionary rather than replacing its reference.
    # Pytest restores every entry afterward.
    for server in tuple(ALLOWED_TOOLS):
        monkeypatch.delitem(ALLOWED_TOOLS, server)

    monkeypatch.setitem(ALLOWED_TOOLS, "stub", STUB_TOOLS)

    def configure(url: str) -> None:
        monkeypatch.setattr(
            session,
            "build_connections",
            lambda settings: {
                "stub": {
                    "transport": "streamable_http",
                    "url": url,
                }
            },
        )

    return configure


@pytest.fixture
def connect_attempts(monkeypatch):
    """Count attempts while forwarding to the real connection helper."""
    calls: list[str] = []
    original = session._connect_once

    async def counted(client, stack, server, deadline_s):
        calls.append(server)
        return await original(client, stack, server, deadline_s)

    monkeypatch.setattr(session, "_connect_once", counted)
    return calls


@pytest.fixture
def tool_attempts(monkeypatch):
    """Count attempts while forwarding to real tool execution."""
    calls: list[str] = []
    original = graph._invoke_once

    async def counted(tool, call, timeout_s):
        calls.append(call["name"])
        return await original(tool, call, timeout_s)

    monkeypatch.setattr(graph, "_invoke_once", counted)
    return calls

@pytest.fixture(autouse=True)
def resilience_evidence(request, monkeypatch, breaker):
    if request.node.get_closest_marker("resilience") is None:
        yield
        return

    started = time.monotonic()
    connection_calls: list[str] = []
    tool_calls: list[str] = []
    failure_kinds = []
    returned_kinds = []

    original_connect = session._connect_once
    original_invoke = graph._invoke_once
    original_failure = breaker.record_failure
    original_result_kind = graph.kind_from_result

    async def counted_connect(client, stack, server, deadline_s):
        connection_calls.append(server)
        return await original_connect(
            client,
            stack,
            server,
            deadline_s,
        )

    async def counted_invoke(tool, call, timeout_s):
        tool_calls.append(call["name"])
        return await original_invoke(tool, call, timeout_s)

    def counted_failure(server, kind):
        failure_kinds.append(kind)
        original_failure(server, kind)

    def counted_result_kind(text):
        kind = original_result_kind(text)
        returned_kinds.append(kind)
        return kind

    monkeypatch.setattr(session, "_connect_once", counted_connect)
    monkeypatch.setattr(graph, "_invoke_once", counted_invoke)
    monkeypatch.setattr(breaker, "record_failure", counted_failure)
    monkeypatch.setattr(graph, "kind_from_result", counted_result_kind)

    try:
        yield
    finally:
        elapsed = time.monotonic() - started

        # Prefer returned-error categories over deliberately seeded
        # breaker failures in tests such as malformed/tool_error.
        if returned_kinds:
            kind = returned_kinds[-1].value
        elif failure_kinds:
            kind = failure_kinds[-1].value
        else:
            kind = "none"

        # Read state without calling allow(), which could reserve a probe.
        state = breaker._servers.get("stub")

        if state is None:
            breaker_state = "unused"
        elif state.probe_in_flight:
            breaker_state = "half_open"
        elif state.opened_at is not None:
            breaker_state = "open"
        else:
            breaker_state = "closed"

        if tool_calls:
            attempts = len(tool_calls)
            scope = "tool"
        else:
            attempts = len(connection_calls)
            scope = "connect"

        print(
            f"\nRESILIENCE {request.node.name} "
            f"kind={kind} "
            f"attempts={attempts} "
            f"elapsed={elapsed:.3f}s "
            f"breaker={breaker_state} "
            f"scope={scope} "
            f"connect_attempts={len(connection_calls)}",
            flush=True,
        )