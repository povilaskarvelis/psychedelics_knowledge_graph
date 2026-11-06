"""Append reviewed source-identity decisions: ``python -m pipeline.identity decide``.

Decisions come from rows of an audit's review queue, from a CSV with the
decision file's fields, or one at a time. Every decision is checked before
anything is written:

- the text it names exists now: the stored full text or its PDF has the
  SHA-256 given, or the record's abstract does;
- the verdict fits the target, and a version names a relation and the DOI of
  a work (a preprint without a DOI of its own names none);
- a basis and a reviewer are given.

A decision identical to a current one is skipped, so recording a batch again
changes nothing. A decision about a text supersedes the current decision about
the same text, and a record decision supersedes the current one of the same
verdict; earlier lines are never edited. A version under a relation that counts
two DOIs as one report is also entered in the work registry, so that
deduplication counts the report once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import csv
import datetime as dt
import json
from pathlib import Path

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.fulltext.source_identity import file_sha256
from pipeline.identity.evidence import NOT_A_WORK_DOI_KINDS, VERSION_DOI_KINDS, doi_kind, text_sha256
from pipeline.identity.register import (
    DEFAULT_DECISIONS_PATH,
    append_decisions,
    current_decisions,
    decision_errors,
    decision_id,
    normalize_decision,
    read_decisions,
)
from pipeline.identity.works import DEDUPLICATED_RELATIONS, DEFAULT_WORK_REGISTRY, work_relation_index
from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_LEDGER = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DECISION_FIELDS = ("verdict", "relation", "related_doi", "fields", "clear_fields")
# Record verdicts of which a paper has one current decision at a time.
SINGLE_RECORD_VERDICTS = frozenset({"hold", "wrong_doi"})


def today() -> str:
    return dt.date.today().isoformat()


def relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


# --- Texts that decisions name --------------------------------------------


class Texts:
    """Identifiers of the texts each paper has now, read on demand."""

    def __init__(
        self,
        artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
        ledger_path: Path = DEFAULT_LEDGER,
        decisions_path: Path = DEFAULT_DECISIONS_PATH,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.ledger_path = Path(ledger_path)
        self.decisions_path = Path(decisions_path)
        self._fulltexts: dict[str, dict[str, set[str]]] = {}
        self._ledger = None

    def fulltext_ids(self, doi: str) -> dict[str, set[str]]:
        """SHA-256 of the stored full text and of its PDF."""
        if doi not in self._fulltexts:
            ids: dict[str, set[str]] = {}
            path = self.artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if normalize_doi(artifact.get("study_doi", "")) == doi:
                ids["sha256"] = {file_sha256(path)}
                pdf_value = clean(artifact.get("pdf_local_path", ""))
                if pdf_value and Path(pdf_value).expanduser().is_file():
                    ids["pdf_sha256"] = {file_sha256(Path(pdf_value).expanduser())}
            self._fulltexts[doi] = ids
        return self._fulltexts[doi]

    @property
    def ledger(self):
        """The ledger with the current record corrections applied, as the audit checks it."""
        if self._ledger is None:
            # Imported here: the ledger is read only for record and abstract decisions.
            from pipeline.identity.audit import apply_record_corrections, decisions_by_doi, load_ledger

            self._ledger = load_ledger(self.ledger_path)
            apply_record_corrections(self._ledger, decisions_by_doi(self.decisions_path))
        return self._ledger

    def abstract_ids(self, doi: str) -> dict[str, set[str]]:
        if doi not in self.ledger.index:
            return {}
        abstract = clean(self.ledger.at[doi, "abstract"])
        return {"sha256": {text_sha256(abstract)}} if abstract else {}

    def has_record(self, doi: str) -> bool:
        return doi in self.ledger.index


def target_ids(target: dict) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    for key in ("sha256", "pdf_sha256", "provider", "source_url"):
        if clean(target.get(key, "")):
            ids[key] = {clean(target[key]).casefold()}
    if normalize_doi(target.get("document_doi", "")):
        ids["document_doi"] = {normalize_doi(target["document_doi"])}
    return ids


def names_same_text(target: dict, ids: dict[str, set[str]]) -> bool:
    """True when the target and the identifiers share one value."""
    own = target_ids(target)
    return any(own.get(key, set()) & {value.casefold() for value in values} for key, values in ids.items())


def text_problem(decision: dict, texts: Texts) -> str:
    """Why the text or record a decision names cannot be found now; ``""`` when it can."""
    doi = decision["doi"]
    target = decision["target"]
    kind = clean(target.get("kind", ""))
    if kind == "record":
        return "" if texts.has_record(doi) else "the DOI has no record in the ledger"
    current = texts.fulltext_ids(doi) if kind == "fulltext" else texts.abstract_ids(doi)
    if not current:
        return f"the paper has no stored {'full text' if kind == 'fulltext' else 'abstract'}"
    hashes = {key: value for key, value in target_ids(target).items() if key in {"sha256", "pdf_sha256"}}
    if hashes and not names_same_text(target, {key: current.get(key, set()) for key in hashes}):
        return f"the {kind} the decision names by SHA-256 is no longer stored for this paper"
    return ""


def related_doi_problem(decision: dict) -> str:
    related = normalize_doi(decision.get("related_doi", ""))
    if not related:
        return ""
    if related == decision["doi"]:
        return "related_doi is the paper's own DOI"
    kind = doi_kind(related)
    if kind in NOT_A_WORK_DOI_KINDS or kind == "component":
        return f"related_doi {related} is a {kind} DOI, not the DOI of a work"
    return ""


# --- Building decisions -----------------------------------------------------


def make_decision(
    *,
    doi: str,
    target: dict,
    verdict: str,
    basis: str,
    reviewer: str,
    relation: str = "",
    related_doi: str = "",
    fields: dict | None = None,
    clear_fields: Iterable[str] = (),
    evidence: Iterable[str] = (),
    decided_at: str = "",
) -> dict:
    decision = {
        "doi": normalize_doi(doi),
        "target": dict(target),
        "verdict": clean(verdict),
        "basis": clean(basis),
        "evidence": [clean(value) for value in evidence if clean(value)],
        "reviewer": clean(reviewer),
        "decided_at": clean(decided_at) or today(),
        "supersedes": [],
    }
    if clean(relation):
        decision["relation"] = clean(relation)
    if normalize_doi(related_doi):
        decision["related_doi"] = normalize_doi(related_doi)
    if decision["verdict"] == "record_corrected":
        decision["fields"] = dict(fields or {})
        decision["clear_fields"] = sorted({clean(field) for field in clear_fields if clean(field)})
    decision = normalize_decision(decision)
    decision["decision_id"] = decision_id(
        decision["doi"],
        json.dumps(decision["target"], sort_keys=True),
        *(json.dumps(decision.get(key, ""), sort_keys=True) for key in DECISION_FIELDS),
        decision["basis"],
        decision["decided_at"],
    )
    return normalize_decision(decision)


def queue_rows(queue: Path, where: Iterable[str] = ()) -> tuple[str, list[dict]]:
    """Rows of a review queue that meet every ``COLUMN=VALUE`` or ``COLUMN!=VALUE`` condition."""
    path = Path(queue)
    if path.is_dir():
        path = path / "review_queue.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    conditions = []
    for condition in where:
        negate = "!=" in condition
        column, _, value = condition.partition("!=" if negate else "=")
        if not column or (rows and column not in rows[0]):
            raise ValueError(f"--where {condition!r}: the queue has no column {column!r}")
        conditions.append((column, value, negate))
    selected = [
        row for row in rows if all((row[column] == value) != negate for column, value, negate in conditions)
    ]
    return path.parent.name, selected


def decisions_from_queue(
    queue: Path,
    where: Iterable[str] = (),
    *,
    basis: str,
    reviewer: str,
    verdict: str = "",
    relation: str = "",
    related_doi: str = "",
    evidence: Iterable[str] = (),
    decided_at: str = "",
) -> tuple[list[dict], Counter]:
    """One decision per selected queue item: the given verdict, or else the item's suggestion.

    The suggested relation, related DOI and fields are kept when the verdict is
    the suggested one and the caller gives none.
    """
    audit_id, rows = queue_rows(queue, where)
    counts: Counter = Counter(selected=len(rows))
    decisions = []
    for row in rows:
        chosen = clean(verdict) or clean(row["suggested_verdict"])
        if not chosen:
            counts["skipped_without_suggestion"] += 1
            continue
        suggested = chosen == clean(row["suggested_verdict"])
        decisions.append(
            make_decision(
                doi=row["doi"],
                target=json.loads(row["target"]),
                verdict=chosen,
                relation=clean(relation) or (row["suggested_relation"] if suggested else ""),
                related_doi=clean(related_doi) or (row["suggested_related_doi"] if suggested else ""),
                fields=json.loads(row["suggested_fields"]) if suggested and clean(row["suggested_fields"]) else None,
                basis=basis,
                reviewer=reviewer,
                evidence=[
                    f"audit {audit_id}, item {row['item_id']} ({row['check']}, {row['rule']}): {row['suggestion_basis']}",
                    *evidence,
                ],
                decided_at=decided_at,
            )
        )
    return decisions, counts


def json_cell(value: str, default):
    return json.loads(value) if clean(value) else default


def decisions_from_csv(path: Path, *, basis: str = "", reviewer: str = "", decided_at: str = "") -> list[dict]:
    """Decisions from a CSV with the decision file's fields.

    ``target``, ``fields``, ``clear_fields`` and ``evidence`` hold JSON. A blank
    ``basis``, ``reviewer`` or ``decided_at`` takes the value given for the batch.
    """
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        make_decision(
            doi=row.get("doi", ""),
            target=json_cell(row.get("target", ""), {}),
            verdict=row.get("verdict", ""),
            relation=row.get("relation", ""),
            related_doi=row.get("related_doi", ""),
            fields=json_cell(row.get("fields", ""), {}),
            clear_fields=json_cell(row.get("clear_fields", ""), []),
            evidence=json_cell(row.get("evidence", ""), []),
            basis=clean(row.get("basis", "")) or basis,
            reviewer=clean(row.get("reviewer", "")) or reviewer,
            decided_at=clean(row.get("decided_at", "")) or decided_at,
        )
        for row in rows
    ]


# --- Recording --------------------------------------------------------------


def decision_content(decision: dict) -> tuple:
    """What a decision says and why, without its id, evidence, reviewer and date."""
    decision = normalize_decision(decision)
    return (
        decision["doi"],
        json.dumps(decision.get("target") or {}, sort_keys=True),
        clean(decision.get("verdict", "")),
        clean(decision.get("relation", "")),
        normalize_doi(decision.get("related_doi", "")),
        json.dumps(decision.get("fields") or {}, sort_keys=True),
        json.dumps(sorted(decision.get("clear_fields") or [])),
        clean(decision.get("basis", "")),
    )


def changed_fields(decision: dict) -> set[str]:
    return set(decision.get("fields") or {}) | set(decision.get("clear_fields") or [])


def superseded(decision: dict, current: list[dict]) -> list[str]:
    """Ids of current decisions that the new decision replaces."""
    kind = decision["target"]["kind"]
    out = []
    for other in current:
        if other["doi"] != decision["doi"] or other["target"].get("kind") != kind:
            continue
        if kind != "record":
            if names_same_text(other["target"], target_ids(decision["target"])):
                out.append(other["decision_id"])
        elif other["verdict"] != decision["verdict"]:
            continue
        elif decision["verdict"] in SINGLE_RECORD_VERDICTS or changed_fields(other) <= changed_fields(decision):
            out.append(other["decision_id"])
    return out


def registry_pair(decision: dict) -> tuple[str, str]:
    """``(alias, canonical)`` for a version decision.

    A preprint or repository DOI is the alias of an article DOI. Otherwise the
    DOI the decision keeps is canonical: the paper, for its full text, and the
    DOI whose abstract it is, for a shared abstract.
    """
    doi, related = decision["doi"], decision["related_doi"]
    version = {value for value in (doi, related) if doi_kind(value) in VERSION_DOI_KINDS}
    if len(version) == 1:
        alias = version.pop()
        return alias, related if alias == doi else doi
    if decision["target"]["kind"] == "abstract":
        return doi, related
    return related, doi


def registry_additions(decisions: list[dict], registry_path: Path) -> tuple[list[dict], list[str]]:
    """Work-registry records for versions that count as one report, and conflicts left out."""
    payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    registered = work_relation_index(registry_path)
    alias_of = {
        normalize_doi(record.get("alias_doi", "")): normalize_doi(record.get("canonical_doi", ""))
        for record in payload.get("records", [])
    }
    additions: list[dict] = []
    conflicts: list[str] = []
    for decision in decisions:
        if decision["verdict"] != "version_of" or decision.get("relation") not in DEDUPLICATED_RELATIONS:
            continue
        if not decision.get("related_doi"):
            continue
        alias, canonical = registry_pair(decision)
        if frozenset((alias, canonical)) in registered:
            continue
        if alias in alias_of or canonical in alias_of:
            conflicts.append(
                f"{alias} -> {canonical}: {alias if alias in alias_of else canonical} is already an alias of "
                f"{alias_of.get(alias) or alias_of.get(canonical)}"
            )
            continue
        alias_of[alias] = canonical
        registered[frozenset((alias, canonical))] = decision["relation"]
        additions.append(
            {
                "alias_doi": alias,
                "canonical_doi": canonical,
                "relationship_type": decision["relation"],
                "evidence_basis": decision["basis"],
                "source_artifact": f"data/curated/source_identity_decisions.jsonl#{decision['decision_id']}",
                "reviewed_at_utc": decision["decided_at"],
            }
        )
    return additions, conflicts


def write_registry(registry_path: Path, additions: list[dict]) -> None:
    payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    payload["records"] = [*payload.get("records", []), *additions]
    Path(registry_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_decisions(
    decisions: list[dict],
    *,
    decisions_path: Path = DEFAULT_DECISIONS_PATH,
    work_registry: Path = DEFAULT_WORK_REGISTRY,
    texts: Texts | None = None,
    dry_run: bool = False,
) -> dict:
    """Check, de-duplicate and append decisions; register the versions they accept.

    Nothing is written when any decision fails a check.
    """
    texts = texts or Texts(decisions_path=decisions_path)
    current = current_decisions(read_decisions(decisions_path))
    recorded = {decision_content(decision) for decision in current}
    problems: list[str] = []
    to_add: list[dict] = []
    counts: Counter = Counter(given=len(decisions), already_recorded=0, superseding=0)
    for decision in decisions:
        label = f"{decision['doi']} ({decision['target'].get('kind', '')} {decision['verdict']})"
        errors = decision_errors(decision)
        for problem in (text_problem(decision, texts) if not errors else "", related_doi_problem(decision)):
            if problem:
                errors.append(problem)
        if errors:
            problems.extend(f"{label}: {error}" for error in errors)
            continue
        if decision_content(decision) in recorded:
            counts["already_recorded"] += 1
            continue
        decision = normalize_decision({**decision, "supersedes": superseded(decision, current)})
        counts["superseding"] += bool(decision["supersedes"])
        recorded.add(decision_content(decision))
        to_add.append(decision)
    if problems:
        raise ValueError(f"{len(problems)} decision(s) failed the checks; nothing was written:\n" + "\n".join(problems))
    additions, conflicts = registry_additions(to_add, work_registry)
    if not dry_run and to_add:
        append_decisions(to_add, decisions_path)
        if additions:
            write_registry(work_registry, additions)
    counts["recorded" if not dry_run else "would_record"] = len(to_add)
    return {
        "decisions": relative(decisions_path),
        "dry_run": dry_run,
        "counts": dict(counts),
        "by_verdict": dict(Counter(f"{d['target']['kind']}:{d['verdict']}" for d in to_add)),
        "work_registry_records_added": len(additions) if not dry_run else 0,
        "work_registry_records_to_add": len(additions) if dry_run else 0,
        "work_registry_conflicts": conflicts,
        "decision_ids": [decision["decision_id"] for decision in to_add],
    }
