
"""Unit tests for build_connections. All keys are FAKE; nothing touches the network."""
import pytest

from changelens.config import Settings
from changelens.mcp_tools.connections import ALLOWED_TOOLS, build_connections

CLEARED_ENV_VARS = (
    "GITHUB_PAT", "TAVILY_API_KEY", "CONTEXT7_API_KEY",
    "GITHUB_MCP_URL", "CONTEXT7_MCP_URL", "TAVILY_MCP_URL", "MCP_CONNECTION_TIMEOUT",
)
ALL_FAKE_KEYS = {
    "github_pat": "fake-github-key",
    "tavily_api_key": "fake-tavily-key",
    "context7_api_key": "fake-context7-key",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop real keys or URL overrides in your shell from changing the results."""
    for name in CLEARED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_no_keys_gives_no_connections():
    assert build_connections(make_settings()) == {}


def test_three_fake_keys_give_one_connection_per_known_server():
    settings = make_settings(**ALL_FAKE_KEYS)
    connections = build_connections(settings)
    assert set(connections) == set(ALLOWED_TOOLS)
    for connection in connections.values():
        assert connection["transport"] == "streamable_http"
        assert connection["timeout"] == settings.mcp_connection_timeout


def test_github_connection_is_read_only():
    connection = build_connections(make_settings(github_pat="fake-github-key"))["github"]
    assert connection["headers"]["X-MCP-Readonly"] == "true"
    assert connection["headers"]["Authorization"] == "Bearer fake-github-key"


def test_tavily_and_context7_headers():
    connections = build_connections(make_settings(**ALL_FAKE_KEYS))
    assert connections["tavily"]["headers"] == {"Authorization": "Bearer fake-tavily-key"}
    assert connections["context7"]["headers"] == {"CONTEXT7_API_KEY": "fake-context7-key"}


def test_missing_key_skips_only_that_server():
    settings = make_settings(github_pat="fake-github-key", context7_api_key="fake-context7-key")
    assert set(build_connections(settings)) == {"github", "context7"}


def test_default_urls_are_the_real_servers():
    """Would have caught a leftover test URL (such as a black-hole address) in config.py."""
    connections = build_connections(make_settings(**ALL_FAKE_KEYS))
    assert connections["github"]["url"] == "https://api.githubcopilot.com/mcp/"
    assert connections["context7"]["url"] == "https://mcp.context7.com/mcp"
    assert connections["tavily"]["url"] == "https://mcp.tavily.com/mcp/"


def test_no_key_appears_in_any_url():
    connections = build_connections(make_settings(**ALL_FAKE_KEYS))
    for connection in connections.values():
        assert "fake" not in connection["url"]
