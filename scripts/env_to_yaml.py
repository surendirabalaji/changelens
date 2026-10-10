#!/usr/bin/env python3
"""Convert a restricted, single-line .env format to Cloud Run YAML."""

import argparse
import json
import os
from pathlib import Path
import sys

ALLOWED = {
    "LLM_API_KEY", "GITHUB_PAT", "TAVILY_API_KEY", "CONTEXT7_API_KEY",
    "TYPESAFE_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "TRIAGE_BACKEND",
}
OPTIONAL_KEYS = {"GITHUB_PAT", "TAVILY_API_KEY", "CONTEXT7_API_KEY", "TYPESAFE_API_KEY"}


def parse_value(raw: str, line_number: int) -> str:
    value = raw.lstrip()
    if not value.startswith(("'", '"')):
        for index, char in enumerate(value):
            if char == "#" and (index == 0 or value[index - 1].isspace()):
                value = value[:index]
                break
        return value.rstrip()

    quote = value[0]
    result = []
    index = 1
    # Single quotes are literal. Double quotes support these escapes only.
    escapes = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
    while index < len(value):
        char = value[index]
        if char == quote:
            trailing = value[index + 1:].strip()
            if trailing and not trailing.startswith("#"):
                raise ValueError(f"Unexpected text after quote on line {line_number}")
            return "".join(result)
        if quote == '"' and char == "\\":
            index += 1
            if index >= len(value) or value[index] not in escapes:
                raise ValueError(f"Unsupported escape on line {line_number}")
            char = escapes[value[index]]
        result.append(char)
        index += 1
    raise ValueError(f"Unclosed quote on line {line_number}")


def read_values(path: Path) -> dict[str, str]:
    values = {}
    with path.open(encoding="utf-8-sig") as source:
        for number, raw in enumerate(source, 1):
            line = raw.rstrip("\r\n").lstrip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, separator, raw_value = line.partition("=")
            name = name.strip()
            if name not in ALLOWED:
                continue
            if not separator:
                raise ValueError(f"Missing equals sign on line {number}")
            value = parse_value(raw_value, number)
            # Last assignment wins, including an empty assignment.
            values.pop(name, None)
            if value:
                values[name] = value
    if "LLM_API_KEY" not in values:
        raise ValueError("LLM_API_KEY is missing or empty")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, default=Path("runtime-env.yaml"))
    args = parser.parse_args()
    try:
        values = read_values(args.input)
        payload = "".join(f"{name}: {json.dumps(values[name])}\n" for name in sorted(values))
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("Error: cannot read input or create output; output must not already exist.", file=sys.stderr)
        return 1
    missing = OPTIONAL_KEYS - values.keys()
    if missing:
        print("Warning: optional credentials missing or empty: " + ", ".join(sorted(missing)), file=sys.stderr)
    print(f"Wrote {len(values)} variables: " + ", ".join(sorted(values)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
