import json
import re

from changelens.schemas import Evidence


EVALUATED_FRAMEWORKS: set[str] = {
    "fastapi",
    "express",
    "@nestjs/core",
}

PYTHON_NAMES = r"fastapi|starlette|flask|django"
NODE_NAMES = {"express", "fastify", "@nestjs/core"}

# Capture a package name and its version constraints, including extras.
PYTHON_DEPENDENCY = re.compile(
    rf"^\s*({PYTHON_NAMES})(?![\w.-])"
    r"(?:\[[^\]\r\n]+\])?"
    r"\s*((?:[<>=!~]=?\s*[^,\s;#\"']+"
    r"(?:\s*,\s*[<>=!~]=?\s*[^,\s;#\"']+)*)?)"
    r"\s*(?:;.*)?$",
    re.IGNORECASE,
)

PARTIAL_NODE_DEPENDENCY = re.compile(
    r'"(express|fastify|@nestjs/core)"\s*:\s*"([^"]*)"',
    re.IGNORECASE,
)


def support_label(frameworks: list[dict]) -> str:
    if any(f["name"] in EVALUATED_FRAMEWORKS for f in frameworks):
        return "evaluated batch"
    return "unevaluated stack, best-effort"


def detect_stack(evidence: Evidence) -> dict | None:
    filename = evidence.path.rsplit("/", 1)[-1].lower()
    frameworks = {}

    def add(name: str, version: str) -> None:
        name = name.lower()
        frameworks[name] = {
            "name": name,
            "version": version,
            "manifest_evidence_id": evidence.id,
        }

    if filename == "requirements.txt":
        for line in evidence.excerpt.splitlines():
            dependency = line.split("#", 1)[0].strip()
            match = PYTHON_DEPENDENCY.fullmatch(dependency)
            if match:
                add(match.group(1), match.group(2) or "")

    elif filename == "pyproject.toml":
        # Read actual TOML dependency fields rather than arbitrary prose.
        import tomllib

        try:
            data = tomllib.loads(evidence.excerpt)
        except tomllib.TOMLDecodeError:
            return None

        project = data.get("project", {})
        dependencies = list(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            dependencies.extend(group)

        for dependency in dependencies:
            if isinstance(dependency, str):
                match = PYTHON_DEPENDENCY.fullmatch(dependency)
                if match:
                    add(match.group(1), match.group(2) or "")

    elif filename == "package.json":
        try:
            data = json.loads(evidence.excerpt)
        except json.JSONDecodeError:
            # Truncated excerpts may contain complete dependency entries.
            # Entries after the excerpt cutoff are missed; never guess them.
            for match in PARTIAL_NODE_DEPENDENCY.finditer(evidence.excerpt):
                add(match.group(1), match.group(2))
        else:
            if not isinstance(data, dict):
                return None

            for section in ("dependencies", "devDependencies"):
                dependencies = data.get(section) or {}
                if not isinstance(dependencies, dict):
                    continue

                for name, version in dependencies.items():
                    if name.lower() in NODE_NAMES and isinstance(version, str):
                        add(name, version)
    else:
        return None

    if not frameworks:
        return None

    items = list(frameworks.values())
    return {
        "frameworks": items,
        "support": support_label(items),
        "url": evidence.url,
    }


def merge_repo_context(
    existing: dict | None,
    detected: dict | None,
) -> dict | None:
    if detected is None:
        return existing

    existing = existing or {}
    if existing.get("url") != detected["url"]:
        existing = {}

    # New entries replace existing entries with the same name.
    frameworks = {
        item["name"]: item
        for item in existing.get("frameworks", [])
    }
    for item in detected["frameworks"]:
        frameworks[item["name"]] = item

    items = list(frameworks.values())
    return {
        **existing,
        "frameworks": items,
        "support": support_label(items),
        "url": detected["url"],
    }