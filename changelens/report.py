from changelens.schemas import Assumption, DecisionRecord, Evidence

MAX_QUOTE_CHARS = 200

NO_STACK_TEXT = "stack not detected from a manifest, best-effort"


def _short(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= MAX_QUOTE_CHARS:
        return flat
    return flat[:MAX_QUOTE_CHARS] + "..."


def _format_assumption(
    assumption: Assumption,
    evidence: dict[str, Evidence],
) -> str:
    if not assumption.grounded:
        return (
            f"- {assumption.id}: {assumption.text}\n"
            f"  NOT VERIFIED ({assumption.grounding_note})"
        )

    sources = []
    for evidence_id in assumption.evidence_ids:
        item = evidence.get(evidence_id)
        if item is not None:
            sources.append(f"{item.path}@{item.revision} [{evidence_id}]")

    return (
        f"- {assumption.id}: {assumption.text}\n"
        f"  Quote: \"{_short(assumption.quote)}\"\n"
        f"  Source: {', '.join(sources)}"
    )


def format_decision(
    record: DecisionRecord,
    repo_context: dict | None,
    evidence: dict[str, Evidence],
) -> str:
    """Render a checked decision as plain markdown text."""
    repo_context = repo_context or {}
    frameworks = ", ".join(
        f"{item['name']} {item['version']}".strip()
        for item in repo_context.get("frameworks", [])
    )
    support = repo_context.get("support") or NO_STACK_TEXT

    lines = [
        "## Decision review (proposed, not accepted)",
        f"Proposed change: {record.proposed_change}",
        f"Stack: {frameworks or 'none detected'} - {support}",
        "",
        "### Assumptions",
    ]

    if record.assumptions:
        lines.extend(
            _format_assumption(item, evidence)
            for item in record.assumptions
        )
    else:
        lines.append("- None could be tied to the files that were read.")

    verified = sum(1 for item in record.assumptions if item.grounded)
    lines.append(
        f"\n{verified} of {len(record.assumptions)} assumptions have a "
        "quote that matches the saved file text. A matching quote shows "
        "the citation is real, not that the assumption is true."
    )

    if record.tests:
        lines.append("\n### Suggested tests (not executed)")
        for test in record.tests:
            lines.append(
                f"- For {test.tests_assumption_id}: {test.setup} -> "
                f"{test.action} -> expect {test.expected}"
            )

    return "\n".join(lines)
