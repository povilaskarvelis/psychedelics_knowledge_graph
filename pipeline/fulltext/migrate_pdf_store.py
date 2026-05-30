#!/usr/bin/env python3
"""Migrate legacy PDF folders into the canonical table-native PDF store."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi, pdf_filename_prefix_for_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi, pdf_filename_prefix_for_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = ROOT / "data" / "raw" / "papers"
DEFAULT_TARGET_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_INVALID_DIR = ROOT / "data" / "raw" / "papers" / "invalid"
DEFAULT_CONFLICT_DIR = ROOT / "data" / "raw" / "papers" / "pdf_conflicts"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "pdf_store_migration_report.json"
DEFAULT_LEGACY_LIBRARY_JSONS = (
    ROOT / "data" / "processed" / "paper_library_mechanistic.json",
    ROOT / "data" / "processed" / "paper_library_disorder.json",
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except Exception:
        return str(path.expanduser())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def file_is_valid_pdf(path: Path) -> bool:
    try:
        raw = path.read_bytes()[:2048].lstrip(b"\x00\t\r\n\f ")
    except Exception:
        return False
    return raw.startswith(b"%PDF-")


def canonical_pdf_name(doi: str) -> str:
    normalized = normalize_doi(doi)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{pdf_filename_prefix_for_doi(normalized)}__{digest}.pdf"


def filename_digest(path: Path) -> str:
    stem = path.stem
    if "__" not in stem:
        return ""
    suffix = stem.rsplit("__", 1)[1]
    return suffix.lower() if len(suffix) == 10 else ""


def read_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def split_paths(value: object) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def add_row_path_mappings(row: dict, doi: str, path_to_doi: dict[str, str]) -> None:
    for field in ("pdf_local_path", "local_pdf_paths"):
        for raw_path in split_paths(row.get(field, "")):
            path_to_doi[path_key(Path(raw_path))] = doi


def build_doi_lookup(
    candidate_table: Path,
    legacy_library_jsons: Iterable[Path],
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str]]:
    doi_by_digest: dict[str, str] = {}
    doi_by_slug: dict[str, list[str]] = defaultdict(list)
    path_to_doi: dict[str, str] = {}

    def add_doi(raw_doi: object, row: dict | None = None) -> None:
        doi = normalize_doi(raw_doi)
        if not doi:
            return
        digest = hashlib.sha1(doi.encode("utf-8")).hexdigest()[:10]
        doi_by_digest[digest] = doi
        slug = doi_to_slug(doi)
        if doi not in doi_by_slug[slug]:
            doi_by_slug[slug].append(doi)
        if row:
            add_row_path_mappings(row, doi, path_to_doi)

    if candidate_table.exists():
        df = pd.read_parquet(candidate_table)
        if "doi" in df.columns:
            for row in df.to_dict("records"):
                add_doi(row.get("doi", ""), row)

    for path in legacy_library_jsons:
        for row in read_json_array(path):
            add_doi(row.get("study_doi", "") or row.get("doi", ""), row)

    return doi_by_digest, dict(doi_by_slug), path_to_doi


def infer_doi_for_pdf(
    path: Path,
    doi_by_digest: dict[str, str],
    doi_by_slug: dict[str, list[str]],
    path_to_doi: dict[str, str],
) -> tuple[str, str]:
    direct = path_to_doi.get(path_key(path), "")
    if direct:
        return direct, "stored_pdf_path"

    digest = filename_digest(path)
    if digest and digest in doi_by_digest:
        return doi_by_digest[digest], "filename_doi_hash"

    slug = doi_to_slug(path.stem.split("__", 1)[0])
    matches = doi_by_slug.get(slug, [])
    if len(matches) == 1:
        return matches[0], "filename_slug"
    if len(matches) > 1:
        return "", "ambiguous_filename_slug"
    return "", "unresolved_filename"


def pdf_sources(source_root: Path, target_dir: Path, invalid_dir: Path, conflict_dir: Path) -> list[Path]:
    source_root = source_root.resolve()
    target_dir = target_dir.resolve()
    invalid_dir = invalid_dir.resolve()
    conflict_dir = conflict_dir.resolve()
    out: list[Path] = []
    for path in sorted(source_root.glob("**/*.pdf")):
        resolved = path.resolve()
        if target_dir == resolved or target_dir in resolved.parents:
            continue
        if invalid_dir == resolved or invalid_dir in resolved.parents:
            continue
        if conflict_dir == resolved or conflict_dir in resolved.parents:
            continue
        if not path.is_file():
            continue
        out.append(path)
    return out


def move_or_copy_file(source: Path, dest: Path, mode: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if mode == "move":
        shutil.move(str(source), str(dest))
    else:
        shutil.copy2(source, dest)


def maybe_quarantine_invalid(source: Path, invalid_dir: Path, apply: bool, mode: str) -> str:
    dest = invalid_dir / source.name
    if not apply:
        return str(dest)
    invalid_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        digest = sha256_file(source)[:12]
        dest = invalid_dir / f"{source.stem}__{digest}{source.suffix}"
    if mode == "move":
        shutil.move(str(source), str(dest))
    else:
        shutil.copy2(source, dest)
    return str(dest)


def conflict_destination(source: Path, doi: str, conflict_dir: Path, source_hash: str) -> Path:
    canonical = Path(canonical_pdf_name(doi))
    return conflict_dir / f"{canonical.stem}__alt_{source_hash[:12]}{canonical.suffix}"


def maybe_move_conflict(source: Path, doi: str, conflict_dir: Path, source_hash: str, apply: bool) -> str:
    dest = conflict_destination(source, doi, conflict_dir, source_hash)
    if not apply:
        return str(dest)
    conflict_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest = conflict_dir / f"{dest.stem}__{sha256_file(source)[:12]}{dest.suffix}"
    shutil.move(str(source), str(dest))
    return str(dest)


def build_existing_canonical_pdf_paths(
    target_dir: Path,
    doi_by_digest: dict[str, str],
    doi_by_slug: dict[str, list[str]],
) -> dict[str, str]:
    out: dict[str, str] = {}
    if not target_dir.exists():
        return out
    for path in sorted(target_dir.glob("*.pdf")):
        if not path.is_file() or not file_is_valid_pdf(path):
            continue
        doi, _ = infer_doi_for_pdf(path, doi_by_digest, doi_by_slug, {})
        if doi and doi not in out:
            out[doi] = str(path.resolve())
    return out


def update_candidate_pdf_paths(
    candidate_table: Path,
    doi_to_path: dict[str, str],
    *,
    clear_stale_paths: bool,
) -> tuple[int, int]:
    if not candidate_table.exists():
        return 0, 0
    df = pd.read_parquet(candidate_table)
    if "doi" not in df.columns:
        return 0, 0
    for column, default in [
        ("pdf_local_path", ""),
        ("local_pdf_paths", ""),
        ("local_pdf_count", 0),
        ("pdf_sha256", ""),
        ("pdf_download_status", ""),
        ("flag_has_local_pdf", False),
    ]:
        if column not in df.columns:
            df[column] = default

    updated = 0
    cleared = 0
    for idx, row in df.iterrows():
        doi = normalize_doi(row.get("doi", ""))
        path = doi_to_path.get(doi)
        current_paths = split_paths(row.get("pdf_local_path", "")) + split_paths(row.get("local_pdf_paths", ""))
        current_flag = clean(row.get("flag_has_local_pdf", "")).lower() in {"1", "true", "yes"}
        has_local_marker = (
            bool(current_paths)
            or clean(row.get("local_pdf_count", "")) not in {"", "0"}
            or bool(clean(row.get("pdf_sha256", "")))
            or current_flag
            or clean(row.get("pdf_download_status", "")) in {"downloaded", "already_present", "manual_import", "invalid_pdf_existing"}
        )
        if not path and not (clear_stale_paths and has_local_marker):
            continue
        if not path:
            cleared += 1
            df.at[idx, "pdf_local_path"] = ""
            df.at[idx, "local_pdf_paths"] = ""
            df.at[idx, "local_pdf_count"] = 0
            df.at[idx, "pdf_sha256"] = ""
            df.at[idx, "flag_has_local_pdf"] = False
            if clean(row.get("pdf_download_status", "")) in {"downloaded", "already_present", "manual_import", "invalid_pdf_existing"}:
                df.at[idx, "pdf_download_status"] = "not_downloaded"
            continue
        pdf_path = Path(path)
        sha = sha256_file(pdf_path) if pdf_path.exists() and pdf_path.is_file() else ""
        status = clean(row.get("pdf_download_status", ""))
        new_status = status if status in {"downloaded", "already_present", "manual_import"} else "already_present"
        if (
            clean(row.get("pdf_local_path", "")) != path
            or clean(row.get("local_pdf_paths", "")) != path
            or clean(row.get("local_pdf_count", "")) != "1"
            or clean(row.get("pdf_sha256", "")) != sha
            or current_flag is not True
            or status != new_status
        ):
            updated += 1
        df.at[idx, "pdf_local_path"] = path
        df.at[idx, "local_pdf_paths"] = path
        df.at[idx, "local_pdf_count"] = 1
        df.at[idx, "pdf_sha256"] = sha
        df.at[idx, "flag_has_local_pdf"] = True
        df.at[idx, "pdf_download_status"] = new_status

    df.to_parquet(candidate_table, engine="pyarrow", index=False)
    return updated, cleared


def migrate_pdf_store(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    target_dir: Path = DEFAULT_TARGET_DIR,
    invalid_dir: Path = DEFAULT_INVALID_DIR,
    conflict_dir: Path = DEFAULT_CONFLICT_DIR,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    legacy_library_jsons: Iterable[Path] = DEFAULT_LEGACY_LIBRARY_JSONS,
    report_path: Path = DEFAULT_REPORT,
    apply: bool = False,
    mode: str = "copy",
    quarantine_invalid: bool = False,
    move_conflicts: bool = False,
    update_candidate_table: bool = True,
    clear_stale_candidate_paths: bool = True,
) -> dict:
    source_root = source_root.resolve()
    target_dir = target_dir.resolve()
    invalid_dir = invalid_dir.resolve()
    conflict_dir = conflict_dir.resolve()
    candidate_table = candidate_table.resolve()
    report_path = report_path.resolve()
    legacy_library_jsons = [Path(path).resolve() for path in legacy_library_jsons]

    doi_by_digest, doi_by_slug, path_to_doi = build_doi_lookup(candidate_table, legacy_library_jsons)
    canonical_paths = build_existing_canonical_pdf_paths(target_dir, doi_by_digest, doi_by_slug)
    sources = pdf_sources(source_root, target_dir, invalid_dir, conflict_dir)

    records: list[dict] = []
    unresolved: list[dict] = []
    invalid: list[dict] = []
    conflicts: list[dict] = []
    doi_to_canonical_path: dict[str, str] = {}

    for source in sources:
        valid_pdf = file_is_valid_pdf(source)
        doi, inferred_by = infer_doi_for_pdf(source, doi_by_digest, doi_by_slug, path_to_doi)
        source_hash = sha256_file(source) if valid_pdf else ""

        if not valid_pdf:
            row = {
                "source": str(source),
                "reason": "invalid_pdf_content",
                "inferred_doi": doi,
                "inferred_by": inferred_by,
            }
            if quarantine_invalid:
                row["quarantine_path"] = maybe_quarantine_invalid(source, invalid_dir, apply, mode)
            invalid.append(row)
            continue

        if not doi:
            unresolved.append({"source": str(source), "reason": inferred_by})
            continue

        dest = target_dir / canonical_pdf_name(doi)
        dest_exists = dest.exists()
        dest_hash = sha256_file(dest) if dest_exists and dest.is_file() else ""
        action = "copy" if mode == "copy" else "move"
        if dest_exists and dest_hash == source_hash:
            action = "already_canonical_duplicate"
        elif dest_exists and dest_hash != source_hash:
            row = {
                "source": str(source),
                "doi": doi,
                "destination": str(dest),
                "source_sha256": source_hash,
                "destination_sha256": dest_hash,
                "reason": "destination_exists_with_different_content",
            }
            if move_conflicts:
                row["conflict_path"] = maybe_move_conflict(source, doi, conflict_dir, source_hash, apply)
                row["action"] = "move_to_conflict_store"
            conflicts.append(row)
            continue

        if apply:
            if action == "already_canonical_duplicate":
                if mode == "move":
                    source.unlink()
            else:
                move_or_copy_file(source, dest, mode)

        doi_to_canonical_path[doi] = str(dest.resolve())
        records.append(
            {
                "source": str(source),
                "doi": doi,
                "destination": str(dest),
                "inferred_by": inferred_by,
                "sha256": source_hash,
                "action": action,
            }
        )

    candidate_rows_updated = 0
    candidate_rows_cleared = 0
    if apply and update_candidate_table:
        canonical_paths.update(doi_to_canonical_path)
        candidate_rows_updated, candidate_rows_cleared = update_candidate_pdf_paths(
            candidate_table,
            canonical_paths,
            clear_stale_paths=clear_stale_candidate_paths,
        )

    report = {
        "generated_at_utc": now_utc(),
        "apply": apply,
        "mode": mode,
        "source_root": str(source_root),
        "target_dir": str(target_dir),
        "invalid_dir": str(invalid_dir),
        "conflict_dir": str(conflict_dir),
        "candidate_table": str(candidate_table),
        "candidate_table_updated": bool(apply and update_candidate_table),
        "candidate_rows_updated": candidate_rows_updated,
        "candidate_rows_cleared": candidate_rows_cleared,
        "counts": {
            "source_pdf_files_seen": len(sources),
            "planned_or_completed_valid_migrations": len(records),
            "invalid_pdf_files": len(invalid),
            "unresolved_pdf_files": len(unresolved),
            "content_conflicts": len(conflicts),
            "unhandled_content_conflicts": 0 if move_conflicts else len(conflicts),
        },
        "records": records,
        "invalid": invalid,
        "unresolved": unresolved,
        "conflicts": conflicts,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy paper PDFs into the canonical PDF store.")
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--target-dir", default=str(DEFAULT_TARGET_DIR))
    parser.add_argument("--invalid-dir", default=str(DEFAULT_INVALID_DIR))
    parser.add_argument("--conflict-dir", default=str(DEFAULT_CONFLICT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--legacy-library-json", action="append", default=[])
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--mode", choices=["copy", "move"], default="copy")
    parser.add_argument("--apply", action="store_true", help="Write files and update the candidate table.")
    parser.add_argument("--quarantine-invalid", action="store_true")
    parser.add_argument("--move-conflicts", action="store_true", help="Move same-DOI alternate PDFs to the conflict store.")
    parser.add_argument("--skip-candidate-table-update", action="store_true")
    parser.add_argument("--keep-stale-candidate-paths", action="store_true")
    args = parser.parse_args()

    legacy_jsons = [Path(path) for path in args.legacy_library_json] if args.legacy_library_json else list(DEFAULT_LEGACY_LIBRARY_JSONS)
    report = migrate_pdf_store(
        source_root=Path(args.source_root),
        target_dir=Path(args.target_dir),
        invalid_dir=Path(args.invalid_dir),
        conflict_dir=Path(args.conflict_dir),
        candidate_table=Path(args.candidate_table),
        legacy_library_jsons=legacy_jsons,
        report_path=Path(args.report),
        apply=args.apply,
        mode=args.mode,
        quarantine_invalid=args.quarantine_invalid,
        move_conflicts=args.move_conflicts,
        update_candidate_table=not args.skip_candidate_table_update,
        clear_stale_candidate_paths=not args.keep_stale_candidate_paths,
    )
    counts = report["counts"]
    print(f"Apply mode: {'yes' if args.apply else 'no (dry-run)'}")
    print(f"Mode: {args.mode}")
    print(f"Source PDFs seen: {counts['source_pdf_files_seen']}")
    print(f"Valid migrations: {counts['planned_or_completed_valid_migrations']}")
    print(f"Invalid PDFs: {counts['invalid_pdf_files']}")
    print(f"Unresolved PDFs: {counts['unresolved_pdf_files']}")
    print(f"Content conflicts: {counts['content_conflicts']}")
    print(f"Candidate rows updated: {report['candidate_rows_updated']}")
    print(f"Candidate rows cleared: {report['candidate_rows_cleared']}")
    print(f"Report: {Path(args.report).resolve()}")
    if counts["unhandled_content_conflicts"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
