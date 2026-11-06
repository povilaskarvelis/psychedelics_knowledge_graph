"""Recompute verdicts with the decisions and list the papers whose text changes:
``python -m pipeline.identity apply``.

``apply`` builds the verdict table (``bindings.py``). For every paper that the
base release extracted, it compares the text the pipeline reads now with the
text the table allows:

- now: the full text when the current full-text gate accepts it and it holds
  article text, otherwise the abstract; nothing for a paper the route table
  holds;
- with the table: the full text when the table makes it usable and it holds
  article text, otherwise the abstract unless a decision says it is not this
  paper's; nothing for a paper a record decision withholds.

Each paper whose text changes is listed in ``scope_dois.txt`` for
``run_scoped_paper_update.py prepare --doi-file``. It is re-extracted when a
text remains and removed from the release when none does. ``changes.csv``
gives the action and reason per paper. Both files, the table and a summary are
written to ``data/processed/identity/updates/<update id>/``.

With ``--install`` the table replaces the one the pipeline reads; without it,
nothing outside the update folder changes.
"""

from __future__ import annotations

from collections import Counter
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import time

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.fulltext.source_identity_audit_gate import DEFAULT_SOURCE_IDENTITY_AUDIT, SourceIdentityAuditGate
from pipeline.identity.audit import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_LEDGER,
    active_release,
    apply_record_corrections,
    decisions_by_doi,
    load_ledger,
    release_impact,
)
from pipeline.identity.bindings import (
    DEFAULT_VERDICTS_PATH,
    PREPRINT_RELATIONS,
    IdentityVerdicts,
    decision_rows,
    fulltext_rows,
    verdict_table,
)
from pipeline.identity.register import DEFAULT_DECISIONS_PATH
from pipeline.identity.works import DEFAULT_WORK_REGISTRY, work_relation_index
from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_UPDATE_ROOT = PROCESSED_DIR / "identity" / "updates"
DEFAULT_ROUTE_TABLE = PROCESSED_DIR / "corpus" / "paper_extraction_routes.parquet"
CHANGE_FIELDS = (
    "doi",
    "action",
    "text_now",
    "text_after",
    "reason",
    "fulltext_verdict",
    "fulltext_rule",
    "decision_ids",
    "release_findings_main",
    "release_findings_detail",
)


def extracted_dois(outputs: list[Path]) -> set[str]:
    """Papers with extraction outputs in the base release."""
    dois: set[str] = set()
    for path in outputs:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    doi = normalize_doi(json.loads(line).get("study_doi", ""))
                    if doi:
                        dois.add(doi)
    return dois


def held_in_routes(route_table: Path) -> set[str]:
    if not Path(route_table).is_file():
        return set()
    routes = pd.read_parquet(route_table, columns=["doi", "route_action"])
    return {normalize_doi(doi) for doi in routes.loc[routes["route_action"] == "hold_source_review", "doi"]}


def routed_to_fulltext(route_table: Path) -> set[str]:
    """Papers the release extracted from full text, whatever the current gate says now."""
    route_table = Path(route_table)
    if not route_table.is_file():
        return set()
    routes = pd.read_parquet(route_table, columns=["doi", "route_action"])
    return {normalize_doi(doi) for doi in routes.loc[routes["route_action"] == "extract_from_full_text", "doi"]}


def file_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else ""


def compare_texts(
    dois: set[str],
    *,
    ledger: pd.DataFrame,
    artifact_dir: Path,
    verdicts: IdentityVerdicts,
    gate: SourceIdentityAuditGate,
    held_now: set[str],
    impact: dict[str, dict],
    routed_fulltext: frozenset[str] | set[str] = frozenset(),
) -> tuple[list[dict], Counter]:
    """One change per paper whose text with the table differs from its text now."""
    # Imported here: the route builder is a large module that only this comparison needs.
    from pipeline.extract.build_extraction_routes import artifact_text_ready

    changes: list[dict] = []
    counts: Counter = Counter()
    for doi in sorted(dois):
        path = Path(artifact_dir) / f"{doi_to_slug(doi)}.json"
        ready = path.is_file() and artifact_text_ready(path)[0]
        abstract = clean(ledger.at[doi, "abstract"]) if doi in ledger.index else ""
        if doi in held_now:
            now = "none"
        elif ready and (doi in routed_fulltext or gate.is_verified(doi, path)):
            now = "fulltext"
        else:
            now = "abstract" if abstract else "none"

        row = verdicts.fulltext(doi, path) if ready else None
        withheld = verdicts.withheld(doi)
        if withheld:
            after, reason = "none", f"withheld: {withheld['reason']}"
        elif row is not None and row["usable"]:
            after, reason = "fulltext", f"full text usable: {row['reason']}"
        elif verdicts.abstract_usable(doi, abstract):
            after = "abstract"
            reason = f"full text not usable: {row['reason']}" if row is not None else "no full text holds article text"
        else:
            after = "none"
            reason = "abstract not usable: " + (verdicts.abstract(doi, abstract) or {}).get("reason", "no abstract")
        if row is not None and row["usable"] and row["verdict"] == "version_of" and row["relation"] in PREPRINT_RELATIONS:
            counts["fulltext_versions_used"] += 1
        if now == after:
            continue
        action = "re-extract" if after != "none" else "remove"
        counts[action] += 1
        counts[f"{now}_to_{after}"] += 1
        entry = impact.get(doi, {})
        changes.append(
            {
                "doi": doi,
                "action": action,
                "text_now": now,
                "text_after": after,
                "reason": reason,
                "fulltext_verdict": row["verdict"] if row is not None else "",
                "fulltext_rule": row["computed_rule"] if row is not None else "",
                "decision_ids": row["decision_ids"] if row is not None else "",
                "release_findings_main": entry.get("main", 0),
                "release_findings_detail": entry.get("detail", 0),
            }
        )
    return changes, counts


def install_table(table_path: Path, summary: dict, verdicts_path: Path) -> None:
    verdicts_path = Path(verdicts_path)
    verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    staged = verdicts_path.with_suffix(".parquet.tmp")
    shutil.copyfile(table_path, staged)
    staged.replace(verdicts_path)
    verdicts_path.with_suffix(".json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_apply(
    *,
    update_id: str | None = None,
    outputs: list[Path] | None = None,
    kg_dir: Path | None = None,
    ledger_path: Path = DEFAULT_LEDGER,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    decisions_path: Path = DEFAULT_DECISIONS_PATH,
    work_registry: Path = DEFAULT_WORK_REGISTRY,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
    out_root: Path = DEFAULT_UPDATE_ROOT,
    verdicts_path: Path = DEFAULT_VERDICTS_PATH,
    read_pdfs: bool = True,
    install: bool = False,
) -> dict:
    """Write the verdict table and the papers whose text changes; return the summary."""
    started = time.monotonic()
    update_id = update_id or "identity_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(out_root) / update_id
    if out_dir.exists():
        raise FileExistsError(f"Update folder already exists: {out_dir}")
    if outputs is None and kg_dir is None:
        outputs, kg_dir = active_release()
    outputs = [Path(path) for path in outputs or []]

    ledger = load_ledger(Path(ledger_path))
    decisions = decisions_by_doi(Path(decisions_path))
    corrections = apply_record_corrections(ledger, decisions)
    relations = work_relation_index(Path(work_registry))
    text_rows, text_counts = fulltext_rows(ledger, Path(artifact_dir), relations, decisions, read_pdfs=read_pdfs)
    other_rows, other_counts = decision_rows(decisions)
    table = verdict_table(text_rows + other_rows)
    verdicts = IdentityVerdicts(table)

    extracted = extracted_dois(outputs)
    changes, change_counts = compare_texts(
        extracted,
        ledger=ledger,
        artifact_dir=Path(artifact_dir),
        verdicts=verdicts,
        gate=SourceIdentityAuditGate(Path(source_identity_audit)),
        held_now=held_in_routes(Path(route_table)),
        routed_fulltext=routed_to_fulltext(Path(route_table)),
        impact=release_impact(kg_dir),
    )

    out_dir.mkdir(parents=True)
    table_path = out_dir / "verdicts.parquet"
    table.to_parquet(table_path, index=False)
    with (out_dir / "changes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CHANGE_FIELDS))
        writer.writeheader()
        writer.writerows(changes)
    (out_dir / "scope_dois.txt").write_text("".join(f"{change['doi']}\n" for change in changes), encoding="utf-8")
    fulltexts = table[table["target_kind"] == "fulltext"]
    summary = {
        "update_id": update_id,
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "decisions": str(decisions_path),
            "decisions_sha256": file_digest(Path(decisions_path)),
            "work_registry_sha256": file_digest(Path(work_registry)),
            "ledger": str(ledger_path),
            "artifact_dir": str(artifact_dir),
            "outputs": [str(path) for path in outputs],
            "kg_dir": str(kg_dir) if kg_dir else "",
            "route_table": str(route_table),
            "source_identity_audit": str(source_identity_audit),
            "record_corrections_applied": dict(corrections),
            "read_pdfs": read_pdfs,
        },
        "fulltexts": {
            "rows": int(len(fulltexts)),
            "usable": int(fulltexts["usable"].sum()),
            "by_verdict": {key: int(value) for key, value in fulltexts["verdict"].value_counts().items()},
            "checks": dict(sorted(text_counts.items())),
        },
        "decision_rows": dict(sorted(other_counts.items())),
        "papers_extracted": len(extracted),
        "changes": dict(sorted(change_counts.items())),
        "scope_dois": len(changes),
        "installed": install,
        "verdicts_path": str(verdicts_path) if install else "",
        "seconds": round(time.monotonic() - started, 1),
    }
    (out_dir / "apply_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if install:
        install_table(table_path, summary, Path(verdicts_path))
    return summary
