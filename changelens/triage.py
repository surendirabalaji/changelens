import re

from changelens.state import ChangeLensState


REPO_REQUEST = re.compile(
    r"https?://github\.com/"
    r"(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)"
    r"(?:/commit/(?P<commit_sha>\b[0-9a-f]{7,40}\b)"
    r"|/tree/(?P<ref>[^\s?#<>\"']+)"
    r"|/?\s+(?:at|@)\s*(?P<sha>\b[0-9a-f]{7,40}\b))?",
    re.IGNORECASE,
)


def parse_repo_request(query: str) -> dict:
    """Extract a GitHub repository URL and optional revision."""
    general = {"intent": "general", "repo_url": "", "revision": ""}

    if not isinstance(query, str):
        return general

    m = REPO_REQUEST.search(query)
    if m is None:
        return general

    owner = m.group("owner")
    repo = m.group("repo").rstrip(".")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]

    if not repo:
        return general

    revision = (
        m.group("commit_sha")
        or m.group("ref")
        or m.group("sha")
        or ""
    ).rstrip(".,;:!)]}")

    return {
        "intent": "repo_review",
        "repo_url": f"https://github.com/{owner}/{repo}",
        "revision": revision,
    }


async def triage(state: ChangeLensState) -> dict:
    return parse_repo_request(state["query"])