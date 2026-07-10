#!/usr/bin/env python3
"""Remove unresolved or container-level files from the canonical full-text store.

Quarantine is a correctness repair, not deletion: the old JSON/PDF is retained
under a run-specific directory, while canonical acquisition fields are cleared
so downstream work cannot accidentally reuse the bad source.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import clean, normalize_doi  # noqa: E402


DEFAULT_AUDIT = ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
DEFAULT_SPECIAL = ROOT / "outputs" / "source_identity_repair_20260710" / "source_identity_special_classes.csv"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_QUARANTINE = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "artifact_quarantine.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            default=lambda value: value.item() if hasattr(value, "item") else str(value),
        )
        + "\n",
        encoding="utf-8",
    )


def special_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        doi: row
        for row in pd.read_csv(path, dtype=str).fillna("").to_dict("records")
        if (doi := normalize_doi(row.get("doi", "")))
    }


def artifact_doi(path: Path, artifact: dict) -> str:
    return normalize_doi(artifact.get("study_doi", "") or path.stem.replace("_", "/"))


def is_exact_article_repair(artifact: dict) -> bool:
    identity = artifact.get("source_identity") if isinstance(artifact.get("source_identity"), dict) else {}
    return (
        clean(artifact.get("repair_run_id", "")) == "source_identity_repair_20260710"
        and clean(identity.get("status", "")) == "verified_exact_doi"
        and clean(artifact.get("best_backend", "")) in {"europepmc_fulltext_xml", "pmc_oai_xml"}
    )


def build_quarantine_plan(
    *,
    audit: dict,
    special: dict[str, dict],
    artifact_dir: Path,
) -> list[dict]:
    audit_by_doi = {
        normalize_doi(row.get("requested_doi", "")): row
        for row in audit.get("rows", []) if isinstance(row, dict)
        if normalize_doi(row.get("requested_doi", ""))
    }
    plan: list[dict] = []
    for path in sorted(artifact_dir.glob("*.json")):
        artifact = load_json(path)
        doi = artifact_doi(path, artifact)
        audit_row = audit_by_doi.get(doi, {})
        special_row = special.get(doi, {})
        reasons: list[str] = []
        if audit_row and not bool(audit_row.get("identity_verified")):
            reasons.append(clean(audit_row.get("identity_status", "identity_unverified")))
        if clean(special_row.get("classification", "")) == "proceedings_container" and not is_exact_article_repair(artifact):
            reasons.append("unsegmented_proceedings_container")
        if not reasons:
            continue
        plan.append(
            {
                "doi": doi,
                "artifact_path": str(path.resolve()),
                "pdf_local_path": clean(artifact.get("pdf_local_path", "")),
                "reasons": sorted(set(reasons)),
                "identity_status": clean(audit_row.get("identity_status", "")),
                "classification": clean(special_row.get("classification", "")),
                "best_backend": clean(artifact.get("best_backend", "")),
                "best_char_count": int(artifact.get("best_char_count", 0) or 0),
            }
        )
    return plan


def resolve_path(value: object) -> Path | None:
    raw = clean(value)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else ROOT / path


def live_pdf_references(artifact_dir: Path, quarantined_dois: set[str]) -> dict[Path, set[str]]:
    out: dict[Path, set[str]] = defaultdict(set)
    for path in artifact_dir.glob("*.json"):
        artifact = load_json(path)
        doi = artifact_doi(path, artifact)
        if doi in quarantined_dois:
            continue
        pdf = resolve_path(artifact.get("pdf_local_path", ""))
        if pdf is not None:
            out[pdf.resolve()].add(doi)
    return out


def remove_path_value(value: object, rejected_paths: set[str]) -> str:
    parts = [clean(part) for part in str(value or "").replace(" | ", "|").split("|")]
    keep = []
    for part in parts:
        if not part:
            continue
        resolved = resolve_path(part)
        if part in rejected_paths or (resolved is not None and str(resolved.resolve()) in rejected_paths):
            continue
        keep.append(part)
    return " | ".join(dict.fromkeys(keep))


def update_candidate_rows(
    frame: pd.DataFrame,
    plan: list[dict],
) -> tuple[pd.DataFrame, dict]:
    frame = frame.copy()
    if "doi" not in frame.columns:
        return frame, {"rows_changed": 0, "missing_dois": sorted(row["doi"] for row in plan)}
    normalized = frame["doi"].map(normalize_doi)
    rows_changed = 0
    missing: list[str] = []
    changes: list[dict] = []
    for row in plan:
        doi = row["doi"]
        indices = frame.index[normalized == doi].tolist()
        if not indices:
            missing.append(doi)
            continue
        rejected: set[str] = set()
        for raw in (row.get("pdf_local_path", ""),):
            path = resolve_path(raw)
            if clean(raw):
                rejected.add(clean(raw))
            if path is not None:
                rejected.add(str(path.resolve()))
        for index in indices:
            before: dict[str, object] = {}
            after: dict[str, object] = {}
            for field in ("pdf_local_path", "pdf_sha256"):
                if field in frame.columns and clean(frame.at[index, field]):
                    before[field] = frame.at[index, field]
                    frame.at[index, field] = ""
                    after[field] = ""
            if "local_pdf_paths" in frame.columns:
                old = clean(frame.at[index, "local_pdf_paths"])
                new = remove_path_value(old, rejected)
                if old != new:
                    before["local_pdf_paths"] = old
                    frame.at[index, "local_pdf_paths"] = new
                    after["local_pdf_paths"] = new
            for field, value in (
                ("pdf_download_status", "source_identity_quarantined"),
                ("best_extraction_access_tier", ""),
                ("has_converted_full_text", False),
                ("flag_has_local_pdf", False),
                ("fulltext_artifact_paths", ""),
                ("fulltext_char_count", 0),
            ):
                if field in frame.columns and frame.at[index, field] != value:
                    before[field] = frame.at[index, field]
                    frame.at[index, field] = value
                    after[field] = value
            if before:
                rows_changed += 1
                changes.append({"doi": doi, "before": before, "after": after})
    return frame, {"rows_changed": rows_changed, "missing_dois": sorted(set(missing)), "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--special-classes", default=str(DEFAULT_SPECIAL))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).resolve()
    candidate_table = Path(args.candidate_table).resolve()
    quarantine = Path(args.quarantine_dir).resolve()
    plan = build_quarantine_plan(
        audit=load_json(Path(args.audit).resolve()),
        special=special_map(Path(args.special_classes).resolve()),
        artifact_dir=artifact_dir,
    )
    target_dois = {row["doi"] for row in plan}
    references = live_pdf_references(artifact_dir, target_dois)
    candidate_frame = pd.read_parquet(candidate_table)
    updated_candidates, candidate_report = update_candidate_rows(candidate_frame, plan)

    counts: Counter[str] = Counter()
    records: list[dict] = []
    moved_pdfs: dict[str, str] = {}
    for row in plan:
        artifact_path = Path(row["artifact_path"])
        artifact_target = quarantine / "quarantined_artifacts" / artifact_path.name
        pdf_path = resolve_path(row.get("pdf_local_path", ""))
        record = {
            **row,
            "status": "planned" if not args.apply else "",
            "quarantined_artifact_path": str(artifact_target),
            "quarantined_pdf_path": "",
            "pdf_retained_reason": "",
        }
        if args.apply:
            artifact_target.parent.mkdir(parents=True, exist_ok=True)
            if artifact_path.exists():
                if artifact_target.exists():
                    artifact_target = artifact_target.with_name(f"{artifact_target.stem}__current{artifact_target.suffix}")
                    record["quarantined_artifact_path"] = str(artifact_target)
                shutil.move(str(artifact_path), str(artifact_target))
            if pdf_path is not None and pdf_path.exists():
                resolved = str(pdf_path.resolve())
                if references.get(pdf_path.resolve()):
                    record["pdf_retained_reason"] = "referenced_by_remaining_verified_artifact"
                elif resolved in moved_pdfs:
                    record["quarantined_pdf_path"] = moved_pdfs[resolved]
                else:
                    pdf_target = quarantine / "quarantined_pdfs" / pdf_path.name
                    pdf_target.parent.mkdir(parents=True, exist_ok=True)
                    if pdf_target.exists():
                        digest = dt.datetime.now().strftime("%H%M%S%f")
                        pdf_target = pdf_target.with_name(f"{pdf_target.stem}__{digest}{pdf_target.suffix}")
                    shutil.move(str(pdf_path), str(pdf_target))
                    moved_pdfs[resolved] = str(pdf_target)
                    record["quarantined_pdf_path"] = str(pdf_target)
            record["status"] = "quarantined"
        counts[record["status"]] += 1
        records.append(record)

    candidate_backup = ""
    if args.apply:
        candidate_backup_path = quarantine / "table_backups" / f"candidate_papers.pre_quarantine_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.parquet"
        candidate_backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_table, candidate_backup_path)
        candidate_backup = str(candidate_backup_path)
        temp_path = candidate_table.with_suffix(".source_identity_quarantine.tmp.parquet")
        updated_candidates.to_parquet(temp_path, engine="pyarrow", index=False)
        check = pd.read_parquet(temp_path)
        if len(check) != len(candidate_frame) or list(check.columns) != list(candidate_frame.columns):
            temp_path.unlink(missing_ok=True)
            raise RuntimeError("candidate table staging validation failed")
        temp_path.replace(candidate_table)

    report = {
        "generated_at_utc": now_utc(),
        "apply": bool(args.apply),
        "counts": {"targets": len(plan), **dict(counts)},
        "candidate_table": {
            **candidate_report,
            "path": str(candidate_table),
            "backup_path": candidate_backup,
        },
        "records": records,
    }
    write_json(Path(args.report).resolve(), report)
    print(json.dumps(report["counts"], indent=2))
    print(f"Candidate rows changed: {candidate_report['rows_changed']}")
    print(f"Report: {Path(args.report).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
