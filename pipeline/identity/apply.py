"""Recompute verdicts with the decisions and list the papers whose text changes:
``python -m pipeline.identity apply``.

``apply`` builds the verdict table (``bindings.py``). For every paper that the
base release extracted, it compares the text the pipeline reads now with the
text the table allows:

- now: the full text when the route table sends the paper to it, otherwise the
  abstract; nothing for a paper the route table holds;
- with the table: the full text when the table makes it usable and it holds
  article text, or the text of a DOI merged into this one, unless an access
  override keeps the paper on its abstract; otherwise the abstract unless a decision says it is not this paper's; nothing for a paper a
  record decision withholds.

A DOI merged into another is not compared: the route builder gives it no route,
and the release keeps the other DOI's findings.

Each paper whose text changes is listed in ``scope_dois.txt`` for
``run_scoped_paper_update.py prepare --doi-file``. It is re-extracted when a
text remains and removed from the release when none does. ``changes.csv``
gives the action and reason per paper. Both files, the table and a summary are
written to ``data/processed/identity/updates/<update id>/``.

With ``--install`` the table replaces the one the pipeline reads, and the
decisions that change a record's values are written to the curated metadata
overrides (``curated_changes``), which the route builder, the KG build and the
release assembly read. Without it, nothing outside the update folder changes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import time

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.audit import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_LEDGER,
    active_release,
    apply_record_corrections,
    decisions_by_doi,
    load_ledger,
    release_impact,
    stored_fulltexts,
)
from pipeline.identity.abstracts import (
    DEFAULT_DISCOVERY_RUNS,
    DEFAULT_PROVIDER_RECORDS_DIR,
    kept_abstracts,
    read_provider_records,
)
from pipeline.identity.bindings import (
    DEFAULT_VERDICTS_PATH,
    PREPRINT_RELATIONS,
    IdentityVerdicts,
    carried_rows,
    decision_rows,
    fulltext_row,
    fulltext_rows,
    usable_for,
    verdict_table,
)
from pipeline.identity.evidence import text_sha256
from pipeline.identity.register import DEFAULT_DECISIONS_PATH
from pipeline.identity.works import DEFAULT_WORK_REGISTRY, work_relation_index
from pipeline.ingest.candidate_status import clean, normalize_doi
from pipeline.validate.doi_aliases import active_doi_aliases, load_doi_aliases


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_UPDATE_ROOT = PROCESSED_DIR / "identity" / "updates"
DEFAULT_ROUTE_TABLE = PROCESSED_DIR / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_METADATA_OVERRIDES = ROOT / "data" / "curated" / "paper_metadata_overrides.json"
UNUSABLE_ABSTRACT_VERDICTS = frozenset({"not_this_work", "wrong_kind"})
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


def kept_on_abstract(route_table: Path) -> set[str]:
    """Papers an access override keeps on their abstract although a full text is stored."""
    route_table = Path(route_table)
    if not route_table.is_file():
        return set()
    routes = pd.read_parquet(route_table, columns=["doi", "manual_fulltext_access_action"])
    return {normalize_doi(doi) for doi in routes.loc[routes["manual_fulltext_access_action"] == "abstract_only", "doi"]}


def file_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else ""


def compare_texts(
    dois: set[str],
    *,
    ledger: pd.DataFrame,
    artifact_dir: Path,
    verdicts: IdentityVerdicts,
    held_now: set[str],
    impact: dict[str, dict],
    routed_fulltext: frozenset[str] | set[str] = frozenset(),
    abstract_only: frozenset[str] | set[str] = frozenset(),
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
        elif doi in routed_fulltext:
            now = "fulltext"
        else:
            now = "abstract" if abstract else "none"

        row = verdicts.fulltext(doi, path) if ready else None
        carried = verdicts.carried(doi)
        if carried is not None and not artifact_text_ready(Path(artifact_dir) / carried["artifact"])[0]:
            carried = None
        withheld = verdicts.withheld(doi)
        if withheld:
            after, reason = "none", f"withheld: {withheld['reason']}"
        elif row is not None and row["usable"] and doi not in abstract_only:
            after, reason = "fulltext", f"full text usable: {row['reason']}"
        elif carried is not None and doi not in abstract_only:
            after, reason = "fulltext", f"full text usable: {carried['reason']}"
        elif verdicts.abstract_usable(doi, abstract):
            after = "abstract"
            if doi in abstract_only:
                reason = "an access override keeps the abstract"
            else:
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


def curated_changes(
    decisions: dict[str, list[dict]], ledger: pd.DataFrame, kept: dict[str, dict[str, str]] | None = None
) -> dict[str, dict]:
    """The metadata values each paper's decisions change.

    These are its corrected fields, a cleared unusable abstract, and an abstract
    a reviewer accepted from a kept provider record (``kept``: abstracts by DOI
    and SHA-256) for a record that has none. Decisions migrated from the
    overrides file are already in it. An abstract is cleared only while the
    record still holds the abstract the decision is about.
    """
    changes: dict[str, dict] = {}
    for doi, doi_decisions in decisions.items():
        change = {"fields": {}, "clear_fields": set(), "decision_id": "", "basis": ""}
        for decision in doi_decisions:
            kind, verdict = decision["target"].get("kind"), decision["verdict"]
            if decision.get("origin"):
                continue
            if kind == "record" and verdict == "record_corrected":
                fields = {field: clean(value) for field, value in (decision.get("fields") or {}).items()}
                change["fields"].update(fields)
                change["clear_fields"] -= set(fields)
                change["clear_fields"] |= set(decision.get("clear_fields") or [])
            elif kind == "abstract" and verdict in UNUSABLE_ABSTRACT_VERDICTS:
                abstract = clean(ledger.at[doi, "abstract"]) if doi in ledger.index else ""
                if not abstract or text_sha256(abstract) != clean(decision["target"].get("sha256", "")):
                    continue
                change["clear_fields"].add("abstract")
            elif kind == "abstract" and usable_for("abstract", verdict, clean(decision.get("relation", "")), doi)[0]:
                accepted = (kept or {}).get(doi, {}).get(clean(decision["target"].get("sha256", "")), "")
                if not accepted or (doi in ledger.index and clean(ledger.at[doi, "abstract"])):
                    continue
                change["fields"]["abstract"] = accepted
                change["clear_fields"].discard("abstract")
            else:
                continue
            change["decision_id"], change["basis"] = decision["decision_id"], decision["basis"]
        if change["decision_id"]:
            changes[doi] = change
    return changes


def write_curated_changes(changes: dict[str, dict], overrides_path: Path) -> int:
    """Add the changes to the curated overrides, one record per paper; return the records changed."""
    payload = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
    records = payload.get("records", [])
    # The loaders take a paper's last record.
    position = {normalize_doi(record.get("doi", "")): index for index, record in enumerate(records)}
    changed = 0
    for doi, change in sorted(changes.items()):
        record = records[position[doi]] if doi in position else {}
        before_fields, before_cleared = record.get("fields") or {}, set(record.get("clear_fields") or [])
        cleared = (before_cleared | change["clear_fields"]) - set(change["fields"])
        fields = {field: value for field, value in {**before_fields, **change["fields"]}.items() if field not in cleared}
        if record and fields == before_fields and cleared == before_cleared:
            continue
        updated = {key: value for key, value in record.items() if key not in {"fields", "clear_fields"}}
        updated.update({"doi": doi, "evidence_basis": change["basis"], "source_decision": change["decision_id"]})
        if fields:
            updated["fields"] = fields
        if cleared:
            updated["clear_fields"] = sorted(cleared)
        if doi in position:
            records[position[doi]] = updated
        else:
            records.append(updated)
        changed += 1
    if changed:
        payload["records"] = records
        Path(overrides_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


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
    out_root: Path = DEFAULT_UPDATE_ROOT,
    verdicts_path: Path = DEFAULT_VERDICTS_PATH,
    metadata_overrides: Path = DEFAULT_METADATA_OVERRIDES,
    discovery_runs: Path = DEFAULT_DISCOVERY_RUNS,
    provider_records_dir: Path = DEFAULT_PROVIDER_RECORDS_DIR,
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
    record_changes = curated_changes(
        decisions, ledger, kept_abstracts(read_provider_records(Path(provider_records_dir), Path(discovery_runs)))
    )
    corrections = apply_record_corrections(ledger, decisions)
    relations = work_relation_index(Path(work_registry))
    text_rows, text_counts = fulltext_rows(ledger, Path(artifact_dir), relations, decisions, read_pdfs=read_pdfs)
    other_rows, other_counts = decision_rows(decisions)
    aliases = active_doi_aliases(load_doi_aliases(Path(work_registry)), set(ledger.index))
    carried, carried_counts = carried_rows(text_rows, aliases, relations)
    table = verdict_table(text_rows + carried + other_rows)
    verdicts = IdentityVerdicts(table)

    extracted = extracted_dois(outputs) - set(aliases)
    changes, change_counts = compare_texts(
        extracted,
        ledger=ledger,
        artifact_dir=Path(artifact_dir),
        verdicts=verdicts,
        held_now=held_in_routes(Path(route_table)),
        routed_fulltext=routed_to_fulltext(Path(route_table)),
        abstract_only=kept_on_abstract(Path(route_table)),
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
            "work_registry": str(work_registry),
            "work_registry_sha256": file_digest(Path(work_registry)),
            "ledger": str(ledger_path),
            "artifact_dir": str(artifact_dir),
            "outputs": [str(path) for path in outputs],
            "kg_dir": str(kg_dir) if kg_dir else "",
            "route_table": str(route_table),
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
        "carried_texts": dict(sorted(carried_counts.items())),
        "papers_extracted": len(extracted),
        "changes": dict(sorted(change_counts.items())),
        "scope_dois": len(changes),
        "curated_changes": len(record_changes),
        "installed": install,
        "verdicts_path": str(verdicts_path) if install else "",
        "seconds": round(time.monotonic() - started, 1),
    }
    (out_dir / "apply_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if install:
        install_table(table_path, summary, Path(verdicts_path))
        summary["curated_records_written"] = write_curated_changes(record_changes, Path(metadata_overrides))
    return summary


def refresh_fulltext_rows(
    written_artifacts: Iterable[Path | str],
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    verdicts_path: Path = DEFAULT_VERDICTS_PATH,
    ledger_path: Path = DEFAULT_LEDGER,
    decisions_path: Path = DEFAULT_DECISIONS_PATH,
    work_registry: Path = DEFAULT_WORK_REGISTRY,
) -> list[str]:
    """Replace the table's rows for newly written full texts; return those it does not make usable."""
    written = {Path(path).resolve().name: str(Path(path).resolve()) for path in written_artifacts}
    if not written:
        return []
    ledger = load_ledger(Path(ledger_path))
    decisions = decisions_by_doi(Path(decisions_path))
    apply_record_corrections(ledger, decisions)
    relations = work_relation_index(Path(work_registry))
    counts: Counter = Counter()
    new_rows = [
        fulltext_row(path, artifact, doi, ledger, relations, decisions, counts)
        for path, artifact, doi in stored_fulltexts(Path(artifact_dir), counts, names=set(written))
    ]
    replaced = {(row["doi"], row["artifact"]) for row in new_rows}
    table = pd.read_parquet(verdicts_path)
    keep = [
        (doi, artifact) not in replaced
        for doi, artifact in zip(table["doi"], table["artifact"])
    ]
    updated = verdict_table(table[keep].to_dict("records") + new_rows)
    staged = Path(verdicts_path).with_suffix(".parquet.tmp")
    updated.to_parquet(staged, index=False)
    staged.replace(verdicts_path)
    return sorted(
        {written[row["artifact"]] for row in new_rows if not row["usable"]}
        | {path for name, path in written.items() if name not in {row["artifact"] for row in new_rows}}
    )
