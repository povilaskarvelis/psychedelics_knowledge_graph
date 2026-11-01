"""One append-only file of reviewed source-identity decisions.

Each line of ``data/curated/source_identity_decisions.jsonl`` is one decision
about one paper:

- whether a specific text (an abstract or a full text) belongs to it;
- whether its bibliographic record was corrected because provider values
  belong to another work;
- whether it is withheld until its source is resolved.

A decision names its evidence and reviewer. Decisions are never edited in
place: a later decision lists the ids it supersedes. Pipeline runs read this
file and never write it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from pipeline.ingest.candidate_status import clean, normalize_doi
from pipeline.identity.works import WORK_RELATIONS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DECISIONS_PATH = ROOT / "data" / "curated" / "source_identity_decisions.jsonl"

VERDICTS = {
    "verified": "the text belongs to the paper",
    "version_of": "the text is a related version of the same work and is accepted for the paper; `relation` says which",
    "not_this_work": "the text belongs to another work",
    "wrong_kind": "the text is not the article itself, for example a supplement, a data statement or a collection",
    "record_corrected": "bibliographic fields were replaced or cleared because provider values belong to another work",
    "wrong_doi": "the record's DOI belongs to another work",
    "hold": "the paper is withheld from extraction and the graph until its source is resolved",
}
TARGET_VERDICTS = {
    "record": frozenset({"record_corrected", "wrong_doi", "hold"}),
    "abstract": frozenset({"verified", "version_of", "not_this_work", "wrong_kind"}),
    "fulltext": frozenset({"verified", "version_of", "not_this_work", "wrong_kind"}),
}
# A text decision must say which text it is about.
TARGET_IDENTITY_FIELDS = {
    "record": (),
    "abstract": ("sha256", "provider"),
    "fulltext": ("sha256", "pdf_sha256", "document_doi", "source_url"),
}
KEY_ORDER = (
    "decision_id",
    "doi",
    "target",
    "verdict",
    "relation",
    "related_doi",
    "fields",
    "clear_fields",
    "basis",
    "evidence",
    "reviewer",
    "decided_at",
    "supersedes",
    "origin",
    "legacy",
)
DECISION_ID_RE = re.compile(r"^sid-[0-9a-f]{20}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ][0-9:.+\-Z]+)?$")


def decision_id(*parts: object) -> str:
    """Return a stable id from the parts that identify one decision."""
    digest = hashlib.sha256("\x1f".join(clean(part) for part in parts).encode("utf-8")).hexdigest()
    return f"sid-{digest[:20]}"


def normalize_decision(raw: dict) -> dict:
    """Return the decision with normalized DOIs and keys in the file's order."""
    decision = dict(raw)
    decision["doi"] = normalize_doi(decision.get("doi", ""))
    if clean(decision.get("related_doi", "")):
        decision["related_doi"] = normalize_doi(decision["related_doi"])
    target = dict(decision.get("target") or {})
    if clean(target.get("document_doi", "")):
        target["document_doi"] = normalize_doi(target["document_doi"])
    for key in ("sha256", "pdf_sha256"):
        if clean(target.get(key, "")):
            target[key] = clean(target[key]).casefold()
    decision["target"] = target
    decision.setdefault("evidence", [])
    decision.setdefault("supersedes", [])
    ordered = {key: decision[key] for key in KEY_ORDER if key in decision}
    ordered.update({key: value for key, value in decision.items() if key not in ordered})
    return ordered


def decision_errors(decision: dict) -> list[str]:
    """Return every problem with one decision; an empty list means it is valid."""
    errors: list[str] = []
    if not DECISION_ID_RE.fullmatch(clean(decision.get("decision_id", ""))):
        errors.append("decision_id must look like sid-<20 hex characters>")
    if not normalize_doi(decision.get("doi", "")):
        errors.append("doi is missing")
    target = decision.get("target")
    kind = clean(target.get("kind", "")) if isinstance(target, dict) else ""
    verdict = clean(decision.get("verdict", ""))
    if kind not in TARGET_VERDICTS:
        errors.append(f"target.kind must be one of {sorted(TARGET_VERDICTS)}")
    else:
        if verdict not in TARGET_VERDICTS[kind]:
            errors.append(f"verdict {verdict!r} is not allowed for a {kind} target")
        identity_fields = TARGET_IDENTITY_FIELDS[kind]
        if identity_fields and not any(clean(target.get(field, "")) for field in identity_fields):
            errors.append(f"a {kind} target needs one of {list(identity_fields)}")
        for key in ("sha256", "pdf_sha256"):
            if clean(target.get(key, "")) and not re.fullmatch(r"[0-9a-f]{64}", clean(target[key])):
                errors.append(f"target.{key} must be a SHA-256 hex digest")
    if verdict == "version_of":
        if clean(decision.get("relation", "")) not in WORK_RELATIONS:
            errors.append(f"version_of needs a relation from {sorted(WORK_RELATIONS)}")
        if not normalize_doi(decision.get("related_doi", "")):
            errors.append("version_of needs related_doi")
    if verdict == "record_corrected":
        fields = decision.get("fields") or {}
        clear_fields = decision.get("clear_fields") or []
        if not isinstance(fields, dict) or not isinstance(clear_fields, list):
            errors.append("fields must be an object and clear_fields a list")
        elif not fields and not clear_fields:
            errors.append("record_corrected needs fields or clear_fields")
        elif set(fields) & set(clear_fields):
            errors.append(f"fields set and cleared at once: {sorted(set(fields) & set(clear_fields))}")
    if not clean(decision.get("basis", "")):
        errors.append("basis is missing")
    if not clean(decision.get("reviewer", "")):
        errors.append("reviewer is missing")
    if not isinstance(decision.get("evidence", []), list):
        errors.append("evidence must be a list")
    if clean(decision.get("decided_at", "")) and not DATE_RE.fullmatch(clean(decision["decided_at"])):
        errors.append("decided_at must be an ISO date or date-time")
    elif not clean(decision.get("decided_at", "")) and not decision.get("origin"):
        errors.append("decided_at is missing")
    if not isinstance(decision.get("supersedes", []), list):
        errors.append("supersedes must be a list of decision ids")
    return errors


def validate_decisions(decisions: list[dict]) -> None:
    """Raise ValueError listing every invalid decision, duplicate id and dangling reference."""
    problems: list[str] = []
    for index, decision in enumerate(decisions, start=1):
        for error in decision_errors(decision):
            problems.append(f"decision {index} ({clean(decision.get('decision_id', ''))}): {error}")
    ids = Counter(clean(decision.get("decision_id", "")) for decision in decisions)
    problems.extend(f"duplicate decision_id {value}" for value, count in ids.items() if count > 1)
    for decision in decisions:
        for superseded in decision.get("supersedes", []) or []:
            if superseded == decision.get("decision_id") or superseded not in ids:
                problems.append(f"{decision.get('decision_id')} supersedes unknown decision {superseded}")
    if problems:
        raise ValueError("Invalid source-identity decisions:\n" + "\n".join(problems))


def serialize_decision(decision: dict) -> str:
    return json.dumps(normalize_decision(decision), ensure_ascii=False)


def read_decision_lines(path: Path = DEFAULT_DECISIONS_PATH) -> list[tuple[str, dict]]:
    """Return each non-blank line verbatim with its parsed decision."""
    path = Path(path)
    if not path.exists():
        return []
    out: list[tuple[str, dict]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            decision = json.loads(line)
        except json.JSONDecodeError as err:
            raise ValueError(f"{path}:{number}: not valid JSON: {err}") from err
        if not isinstance(decision, dict):
            raise ValueError(f"{path}:{number}: a decision must be a JSON object")
        out.append((line, decision))
    return out


def read_decisions(path: Path = DEFAULT_DECISIONS_PATH) -> list[dict]:
    decisions = [decision for _line, decision in read_decision_lines(path)]
    validate_decisions(decisions)
    return decisions


def current_decisions(decisions: Iterable[dict]) -> list[dict]:
    """Drop decisions that a later decision supersedes."""
    decisions = list(decisions)
    superseded = {value for decision in decisions for value in decision.get("supersedes", []) or []}
    return [decision for decision in decisions if decision.get("decision_id") not in superseded]


def write_decision_lines(path: Path, lines: list[str]) -> None:
    """Replace the file atomically with the given lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write("".join(f"{line}\n" for line in lines))
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def append_decisions(new_decisions: Iterable[dict], path: Path = DEFAULT_DECISIONS_PATH) -> list[dict]:
    """Validate and append decisions; earlier lines are kept byte for byte."""
    existing = read_decision_lines(path)
    added = [normalize_decision(decision) for decision in new_decisions]
    validate_decisions([decision for _line, decision in existing] + added)
    write_decision_lines(path, [line for line, _decision in existing] + [serialize_decision(d) for d in added])
    return added
