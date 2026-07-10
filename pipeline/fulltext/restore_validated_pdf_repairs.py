#!/usr/bin/env python3
"""Restore independently validated PDF repairs that an older audit quarantined."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import clean, normalize_doi  # noqa: E402


DEFAULT_REPAIR_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "pdf_artifact_repair_applied.json"
DEFAULT_QUARANTINE_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "artifact_quarantine_applied.json"
DEFAULT_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "validated_pdf_restoration.json"


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validated_repair_artifact(artifact: dict, pdf_path: Path) -> tuple[bool, str]:
    identity = artifact.get("source_identity") if isinstance(artifact.get("source_identity"), dict) else {}
    validation = identity.get("pdf_front_page_validation") if isinstance(identity.get("pdf_front_page_validation"), dict) else {}
    if clean(artifact.get("repair_run_id", "")) != "source_identity_repair_20260710":
        return False, "wrong_repair_run"
    if clean(artifact.get("fulltext_source", "")) != "validated_pdf_source_identity_repair":
        return False, "wrong_source"
    if clean(identity.get("status", "")) != "verified_title_only" or not bool(identity.get("verified")):
        return False, "identity_not_attested"
    if not bool(validation.get("accepted")) or clean(validation.get("reason", "")) != "verified_front_page":
        return False, "front_page_not_validated"
    if float(validation.get("title_score", 0) or 0) < 0.86:
        return False, "title_score_below_threshold"
    if int(validation.get("front_page_char_count", 0) or 0) < 300:
        return False, "front_page_text_too_short"
    expected = clean(artifact.get("pdf_sha256", "")).lower()
    if not pdf_path.exists() or not expected or sha256(pdf_path).lower() != expected:
        return False, "pdf_hash_mismatch"
    return True, ""


def restoration_plan(repair_report: dict, quarantine_report: dict) -> list[dict]:
    quarantined = {
        normalize_doi(row.get("doi", "")): row
        for row in quarantine_report.get("records", [])
        if isinstance(row, dict) and normalize_doi(row.get("doi", ""))
    }
    rows: list[dict] = []
    for repair in repair_report.get("records", []):
        if not isinstance(repair, dict) or clean(repair.get("status", "")) != "replaced_validated_pdf":
            continue
        doi = normalize_doi(repair.get("doi", ""))
        artifact_target = Path(clean(repair.get("artifact_path", ""))).resolve()
        if artifact_target.exists():
            continue
        quarantine = quarantined.get(doi, {})
        artifact_source = Path(clean(quarantine.get("quarantined_artifact_path", ""))).resolve()
        pdf_source = Path(clean(quarantine.get("quarantined_pdf_path", ""))).resolve()
        if not pdf_source.exists():
            # A shared or pre-existing target may have been retained; use the
            # attested canonical path only when it still exists.
            candidate = Path(clean(repair.get("pdf_path", ""))).resolve()
            if candidate.exists():
                pdf_source = candidate
        artifact = load_json(artifact_source) if artifact_source.exists() else {}
        pdf_target = Path(clean(artifact.get("pdf_local_path", ""))).resolve() if artifact else Path()
        valid, reason = validated_repair_artifact(artifact, pdf_source) if artifact else (False, "artifact_missing")
        rows.append(
            {
                "doi": doi,
                "artifact_source": str(artifact_source),
                "artifact_target": str(artifact_target),
                "pdf_source": str(pdf_source),
                "pdf_target": str(pdf_target),
                "validated": valid,
                "validation_error": reason,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-report", default=str(DEFAULT_REPAIR_REPORT))
    parser.add_argument("--quarantine-report", default=str(DEFAULT_QUARANTINE_REPORT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    plan = restoration_plan(
        load_json(Path(args.repair_report).resolve()),
        load_json(Path(args.quarantine_report).resolve()),
    )
    counts: Counter[str] = Counter()
    records: list[dict] = []
    for row in plan:
        record = dict(row)
        if not row["validated"]:
            record["status"] = "validation_failed"
        elif not args.apply:
            record["status"] = "validated_dry_run"
        else:
            artifact_source = Path(row["artifact_source"])
            artifact_target = Path(row["artifact_target"])
            pdf_source = Path(row["pdf_source"])
            pdf_target = Path(row["pdf_target"])
            if artifact_target.exists() or (pdf_target.exists() and pdf_target.resolve() != pdf_source.resolve()):
                raise RuntimeError(f"Refusing to overwrite an existing restoration target for {row['doi']}")
            artifact_target.parent.mkdir(parents=True, exist_ok=True)
            pdf_target.parent.mkdir(parents=True, exist_ok=True)
            moved_pdf = False
            try:
                if pdf_source.resolve() != pdf_target.resolve():
                    shutil.move(str(pdf_source), str(pdf_target))
                    moved_pdf = True
                shutil.move(str(artifact_source), str(artifact_target))
            except Exception:
                if moved_pdf and pdf_target.exists() and not pdf_source.exists():
                    shutil.move(str(pdf_target), str(pdf_source))
                raise
            record["status"] = "restored"
        counts[record["status"]] += 1
        records.append(record)

    report = {
        "apply": bool(args.apply),
        "counts": {"targets": len(plan), **dict(counts)},
        "records": records,
    }
    output = Path(args.report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {output}")
    return 1 if counts["validation_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
