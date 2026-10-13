from pydantic.fields import Field
import hashlib
from typing import Literal

from pydantic import BaseModel


class Evidence(BaseModel):
    url : str
    path: str
    lines: str
    # 4,000 for source files, 6,000 for manifests (see changelens/evidence.py).
    excerpt: str = Field(max_length=6000)
    excerpt_sha256: str
    extraction_method: str
    trust: Literal["untrusted_data"]
    id: str
    revision: str

class Assumption(BaseModel):
    id: str
    text: str
    evidence_ids: list[str]
    quote: str = ""
    status: Literal[
        "unverified",
        "supported",
        "weakened",
        "contradicted",
        "unaffected",
    ]
    grounded: bool = False
    grounding_note: str = ""


class AssumptionDraft(BaseModel):
    text: str
    evidence_id: str
    quote: str = ""


class TestDraft(BaseModel):
    setup: str
    action: str
    expected: str
    assumption_number: int


class SynthesisOutput(BaseModel):
    proposed_change: str
    assumptions: list[AssumptionDraft] = Field(
        default_factory=list,
        max_length=4,
    )
    tests: list[TestDraft] = Field(
        default_factory=list,
        max_length=4,
    )


class TestScenario(BaseModel):
    setup: str
    action: str
    expected: str
    tests_assumption_id: str
    execution_status: Literal["not_executed"] = "not_executed"

class DecisionRecord(BaseModel):
    id: str
    proposed_change: str
    assumptions: list[Assumption] = Field(default_factory=list)
    tests: list[TestScenario] = Field(default_factory=list)
    acceptance : Literal["proposed","user_accepted"] = "proposed"
    revision_history: list[dict] = Field(default_factory=list)

def make_evidence_id(url: str, revision: str, path: str, lines: str) -> str:

    # 1. Combine the inputs using a delimiter to prevent boundary collisions
    # Example: "url|revision|path|lines"
    combined_string = f"{url}|{revision}|{path}|{lines}"
    
    # 2. Convert the string to bytes and generate a SHA-256 hash
    hash_object = hashlib.sha256(combined_string.encode('utf-8'))
    
    # 3. Return the hash as a clean, readable hexadecimal string
    return hash_object.hexdigest()[:16]