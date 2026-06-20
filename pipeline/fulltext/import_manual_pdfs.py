#!/usr/bin/env python3
"""Import manually downloaded PDFs from an inbox into the canonical PDF store."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.sync_paper_library import normalize_doi, pdf_filename_for_doi  # noqa: E402

DEFAULT_INBOX_DIR = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_CONFLICT_DIR = ROOT / "data" / "raw" / "papers" / "pdf_conflicts"
DEFAULT_INVALID_DIR = ROOT / "data" / "raw" / "papers" / "invalid"
DEFAULT_MANUAL_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_import_report.json"
DEFAULT_REVIEW_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_import_review.csv"

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
PII_RE = re.compile(r"\bS\d{4}-?\d{4}\(?\d{2}\)?\d{5}-?\d\b", re.IGNORECASE)
STOPWORDS = {
    "about",
    "after",
    "among",
    "based",
    "between",
    "clinical",
    "effect",
    "effects",
    "from",
    "into",
    "paper",
    "study",
    "that",
    "their",
    "therapy",
    "through",
    "using",
    "with",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["file", "status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def looks_like_pdf(path: Path) -> bool:
    try:
        raw = path.read_bytes()[:2048].lstrip(b"\x00\t\r\n\f ")
    except Exception:
        return False
    return raw.startswith(b"%PDF-")


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def clean_doi_candidate(raw: str) -> str:
    text = unquote(raw)
    text = text.strip().strip("<>")
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", text, flags=re.IGNORECASE)
    text = text.rstrip(".,;: \t\r\n")
    while text.endswith(")") and text.count("(") < text.count(")"):
        text = text[:-1]
    return normalize_doi(text).lower()


def extract_dois_from_text(text: str) -> list[str]:
    out: list[str] = []
    for match in DOI_RE.findall(text or ""):
        doi = clean_doi_candidate(match)
        if doi and doi not in out:
            out.append(doi)
    return out


def split_candidates(value: object) -> list[str]:
    return [part.strip() for part in clean(value).split("|") if part.strip()]


def filename_key_from_url(value: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(clean(value))
    basename = Path(unquote(parsed.path)).name if parsed.path else ""
    return basename.lower()


def normalize_pii(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "", clean(value).lower())
    if text.startswith("pii"):
        text = text[3:]
    return text


def extract_pii_candidates(text: str) -> list[str]:
    out: list[str] = []
    for match in PII_RE.findall(text or ""):
        pii = normalize_pii(match)
        if pii and pii not in out:
            out.append(pii)
    compact = normalize_pii(text)
    compact_match = re.search(r"s\d{16}", compact)
    if compact_match:
        compact_pii = compact_match.group(0)
        if compact_pii not in out:
            out.append(compact_pii)
    return out


def parse_doi_from_filename(path: Path) -> list[str]:
    stem = unquote(path.stem)
    stem_without_suffix = stem.split("__", 1)[0]
    candidates = extract_dois_from_text(stem_without_suffix.replace("_", "/"))
    if candidates:
        return candidates
    candidates = extract_dois_from_text(stem_without_suffix.replace("_", " "))
    if candidates:
        return candidates
    if stem_without_suffix.lower().startswith("doi_"):
        candidates = extract_dois_from_text(stem_without_suffix[4:].replace("_", "/"))
        if candidates:
            return candidates
    return []


def extract_pdf_text(path: Path, max_pages: int) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", str(max(1, max_pages)), str(path), "-"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        text = result.stdout.decode("utf-8", errors="replace")
        if text.strip():
            return text
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = reader.pages[: max(1, max_pages)]
        return "\n".join(page.extract_text() or "" for page in pages)
    except Exception:
        return ""


def extract_pdf_metadata_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        metadata = PdfReader(str(path)).metadata
        if not metadata:
            return ""
        values = []
        for attr in ("title", "subject", "author", "creator", "producer"):
            value = getattr(metadata, attr, "")
            if value:
                values.append(str(value))
        return "\n".join(values)
    except Exception:
        return ""


def normalize_for_title_match(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", clean(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> list[str]:
    return [
        token
        for token in normalize_for_title_match(title).split()
        if len(token) > 3 and token not in STOPWORDS and not token.isdigit()
    ]


def title_match_score_against_normalized_text(title: str, text_norm: str) -> float:
    title_norm = normalize_for_title_match(title)
    if not title_norm or not text_norm:
        return 0.0
    if title_norm in text_norm:
        return 1.0
    tokens = title_tokens(title)
    if len(tokens) < 4:
        return 0.0
    token_score = sum(1 for token in tokens if token in text_norm) / len(tokens)
    if token_score == 0:
        return 0.0
    if token_score >= 0.86:
        return token_score
    ratio = SequenceMatcher(None, title_norm[:300], text_norm[:2000]).ratio()
    return max(token_score, ratio)


def title_match_score(title: str, text: str) -> float:
    return title_match_score_against_normalized_text(title, normalize_for_title_match(text))


def doi_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")


def build_filename_slug_lookup(known_records: dict[str, dict]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for doi in known_records:
        for raw in (doi, pdf_filename_for_doi(doi).split("__", 1)[0]):
            slug = doi_slug(raw)
            if not slug:
                continue
            lookup.setdefault(slug, [])
            if doi not in lookup[slug]:
                lookup[slug].append(doi)
    return lookup


def build_source_filename_lookup(known_records: dict[str, dict]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    url_fields = [
        "best_pdf_url",
        "open_access_url",
        "pdf_url_candidates",
        "probable_pdf_url_candidates",
        "other_url_candidates",
    ]
    for doi, record in known_records.items():
        values: list[str] = []
        for field in url_fields:
            values.extend(split_candidates(record.get(field, "")))
        for value in values:
            key = filename_key_from_url(value)
            if not key:
                continue
            lookup.setdefault(key, [])
            if doi not in lookup[key]:
                lookup[key].append(doi)
    return lookup


def build_pii_lookup(known_records: dict[str, dict]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for doi, record in known_records.items():
        values = [doi]
        values.extend(split_candidates(record.get("related_dois", "")))
        values.extend(split_candidates(record.get("best_pdf_url", "")))
        values.extend(split_candidates(record.get("pdf_url_candidates", "")))
        for value in values:
            for pii in extract_pii_candidates(value):
                lookup.setdefault(pii, [])
                if doi not in lookup[pii]:
                    lookup[pii].append(doi)
    return lookup


def load_known_records(manual_csv: Path, candidate_table: Path, metadata_table: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}

    def add(row: dict, source: str) -> None:
        doi = normalize_doi(row.get("doi", "")).lower()
        if not doi:
            return
        existing = records.setdefault(doi, {"doi": doi})
        for key, value in row.items():
            if clean(value) and not clean(existing.get(key, "")):
                existing[key] = value
        existing.setdefault("record_sources", [])
        if source not in existing["record_sources"]:
            existing["record_sources"].append(source)

    if manual_csv.exists():
        for row in pd.read_csv(manual_csv).fillna("").to_dict("records"):
            add(row, "manual_pdf_download_csv")
    if metadata_table.exists():
        for row in pd.read_parquet(metadata_table).fillna("").to_dict("records"):
            add(row, "metadata_table")
    if candidate_table.exists():
        for row in pd.read_parquet(candidate_table).fillna("").to_dict("records"):
            add(row, "candidate_table")
    return records


def select_match(
    *,
    file_path: Path,
    known_records: dict[str, dict],
    text: str,
    metadata_text: str,
    enable_title_match: bool,
    min_title_score: float,
    min_title_margin: float,
    filename_slug_lookup: dict[str, list[str]] | None = None,
    source_filename_lookup: dict[str, list[str]] | None = None,
    pii_lookup: dict[str, list[str]] | None = None,
) -> tuple[str, str, list[dict]]:
    known_dois = set(known_records)
    filename_dois = [doi for doi in parse_doi_from_filename(file_path) if doi in known_dois]
    if len(filename_dois) == 1:
        return filename_dois[0], "filename_doi", []
    if len(filename_dois) > 1:
        return "", "ambiguous_filename_doi", [{"doi": doi, "basis": "filename_doi"} for doi in filename_dois]

    if filename_slug_lookup:
        filename_slug = doi_slug(file_path.stem.split("__", 1)[0])
        slug_dois = filename_slug_lookup.get(filename_slug, [])
        if len(slug_dois) == 1:
            return slug_dois[0], "filename_doi_slug", []
        if len(slug_dois) > 1:
            return "", "ambiguous_filename_doi_slug", [{"doi": doi, "basis": "filename_doi_slug"} for doi in slug_dois]

    if source_filename_lookup:
        source_filename_candidates: list[dict] = []
        source_filename_dois = source_filename_lookup.get(file_path.name.lower(), [])
        if len(source_filename_dois) == 1:
            return source_filename_dois[0], "source_url_filename", []
        if len(source_filename_dois) > 1:
            source_filename_candidates = [{"doi": doi, "basis": "source_url_filename"} for doi in source_filename_dois]
    else:
        source_filename_candidates = []

    metadata_dois = [doi for doi in extract_dois_from_text(metadata_text) if doi in known_dois]
    if len(metadata_dois) == 1:
        return metadata_dois[0], "pdf_metadata_doi", []
    if len(metadata_dois) > 1:
        return "", "ambiguous_pdf_metadata_doi", [{"doi": doi, "basis": "pdf_metadata_doi"} for doi in metadata_dois]

    if pii_lookup:
        pii_matches: list[str] = []
        for value in [file_path.name, metadata_text, text]:
            for pii in extract_pii_candidates(value):
                for doi in pii_lookup.get(pii, []):
                    if doi not in pii_matches:
                        pii_matches.append(doi)
        if len(pii_matches) == 1:
            return pii_matches[0], "pii", []
        if len(pii_matches) > 1:
            return "", "ambiguous_pii", [{"doi": doi, "basis": "pii"} for doi in pii_matches]

    text_dois = [doi for doi in extract_dois_from_text(text) if doi in known_dois]
    if len(text_dois) == 1:
        return text_dois[0], "pdf_text_doi", []
    if len(text_dois) > 1:
        return "", "ambiguous_pdf_text_doi", [{"doi": doi, "basis": "pdf_text_doi"} for doi in text_dois[:20]]

    if not enable_title_match:
        if source_filename_candidates:
            return "", "ambiguous_source_url_filename", source_filename_candidates
        return "", "no_doi_found", []

    scored: list[dict] = []
    combined_text = f"{metadata_text}\n{text}"
    combined_text_norm = normalize_for_title_match(combined_text)
    for doi, record in known_records.items():
        title = clean(record.get("study_title", "") or record.get("title", ""))
        score = title_match_score_against_normalized_text(title, combined_text_norm)
        if score >= min_title_score:
            scored.append({"doi": doi, "score": round(score, 4), "title": title})
    scored.sort(key=lambda row: row["score"], reverse=True)
    if not scored:
        if source_filename_candidates:
            return "", "ambiguous_source_url_filename", source_filename_candidates
        return "", "no_title_match", []
    best = scored[0]
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    if best["score"] - second >= min_title_margin:
        return best["doi"], "title_match", scored[:5]
    return "", "ambiguous_title_match", scored[:5]


def conflict_path(conflict_dir: Path, canonical_name: str, source_hash: str) -> Path:
    canonical = Path(canonical_name)
    return conflict_dir / f"{canonical.stem}__manual_alt_{source_hash[:12]}{canonical.suffix}"


def replaced_prior_path(conflict_dir: Path, canonical_name: str, prior_hash: str) -> Path:
    canonical = Path(canonical_name)
    return conflict_dir / f"{canonical.stem}__replaced_prior_{prior_hash[:12]}{canonical.suffix}"


def ensure_candidate_pdf_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column, default in [
        ("pdf_local_path", ""),
        ("local_pdf_paths", ""),
        ("local_pdf_count", 0),
        ("pdf_sha256", ""),
        ("pdf_download_status", ""),
        ("flag_has_local_pdf", False),
        ("library_status", ""),
        ("pdf_download_error", ""),
        ("pdf_download_failure_category", ""),
        ("pdf_download_failure_categories", ""),
        ("pdf_download_retry_recommended", False),
    ]:
        if column not in df.columns:
            df[column] = default
    return df


def manual_import_status(current_status: object, import_status: object) -> str:
    current = clean(current_status).lower()
    if clean(import_status) == "already_present" and current in {"downloaded", "already_present", "manual_import"}:
        return current
    return "manual_import"


def update_candidate_table_for_imports(candidate_table: Path, imported_rows: list[dict], *, apply: bool) -> dict:
    matched_rows = [
        row
        for row in imported_rows
        if clean(row.get("doi", ""))
        and clean(row.get("status", "")) in {"matched", "already_present", "replaced_existing_pdf"}
    ]
    summary = {
        "candidate_table": str(candidate_table.resolve()),
        "apply": apply,
        "eligible_import_rows": len(matched_rows),
        "candidate_rows_updated": 0,
        "candidate_rows_matched": 0,
        "missing_candidate_dois": [],
        "missing_pdf_paths": [],
        "records": [],
    }
    if not apply or not matched_rows or not candidate_table.exists():
        return summary

    df = ensure_candidate_pdf_columns(pd.read_parquet(candidate_table))
    if "doi" not in df.columns:
        return summary

    doi_keys = df["doi"].map(lambda value: normalize_doi(clean(value)).lower())
    changed = False
    for import_row in matched_rows:
        doi = normalize_doi(clean(import_row.get("doi", ""))).lower()
        dest = Path(clean(import_row.get("destination", "")))
        if not dest.exists() or not dest.is_file():
            summary["missing_pdf_paths"].append({"doi": doi, "path": str(dest)})
            continue
        mask = doi_keys.eq(doi)
        if not mask.any():
            summary["missing_candidate_dois"].append(doi)
            continue

        dest_path = str(dest.resolve())
        digest = sha256_file(dest)
        for index in df.index[mask]:
            summary["candidate_rows_matched"] += 1
            previous_status = clean(df.at[index, "pdf_download_status"])
            updates = {
                "pdf_local_path": dest_path,
                "local_pdf_paths": dest_path,
                "local_pdf_count": 1,
                "pdf_sha256": digest,
                "pdf_download_status": manual_import_status(previous_status, import_row.get("status", "")),
                "flag_has_local_pdf": True,
                "library_status": "in_database",
                "pdf_download_error": "",
                "pdf_download_failure_category": "",
                "pdf_download_failure_categories": "",
                "pdf_download_retry_recommended": False,
            }
            row_changed = False
            for field, value in updates.items():
                if clean(df.at[index, field]) != clean(value):
                    df.at[index, field] = value
                    changed = True
                    row_changed = True
            if row_changed:
                summary["candidate_rows_updated"] += 1
            summary["records"].append(
                {
                    "doi": doi,
                    "candidate_row_index": int(index),
                    "import_status": clean(import_row.get("status", "")),
                    "previous_pdf_download_status": previous_status,
                    "new_pdf_download_status": updates["pdf_download_status"],
                    "pdf_local_path": dest_path,
                    "pdf_sha256": digest,
                    "updated": row_changed,
                }
            )

    if changed:
        df.to_parquet(candidate_table, engine="pyarrow", index=False)
    return summary


def import_manual_pdfs(
    *,
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    conflict_dir: Path = DEFAULT_CONFLICT_DIR,
    invalid_dir: Path = DEFAULT_INVALID_DIR,
    manual_csv: Path = DEFAULT_MANUAL_CSV,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    report_path: Path = DEFAULT_REPORT,
    review_csv: Path = DEFAULT_REVIEW_CSV,
    apply: bool = False,
    move: bool = False,
    enable_title_match: bool = True,
    min_title_score: float = 0.86,
    min_title_margin: float = 0.12,
    max_pages: int = 3,
    replace_existing: bool = False,
) -> dict:
    inbox_dir = inbox_dir.resolve()
    pdf_dir = pdf_dir.resolve()
    conflict_dir = conflict_dir.resolve()
    invalid_dir = invalid_dir.resolve()
    known_records = load_known_records(manual_csv, candidate_table, metadata_table)
    filename_slug_lookup = build_filename_slug_lookup(known_records)
    source_filename_lookup = build_source_filename_lookup(known_records)
    pii_lookup = build_pii_lookup(known_records)
    files = sorted(path for path in inbox_dir.glob("*.pdf") if path.is_file()) if inbox_dir.exists() else []

    imported: list[dict] = []
    review_rows: list[dict] = []
    invalid: list[dict] = []
    skipped: list[dict] = []

    for file_path in files:
        source_hash = sha256_file(file_path)
        base = {
            "file": str(file_path),
            "source_sha256": source_hash,
            "apply": apply,
            "move": move,
        }
        if not looks_like_pdf(file_path):
            dest = invalid_dir / file_path.name
            row = {**base, "status": "invalid_pdf", "reason": "file_does_not_start_with_pdf_header", "destination": str(dest)}
            invalid.append(row)
            review_rows.append(row)
            if apply:
                invalid_dir.mkdir(parents=True, exist_ok=True)
                if move:
                    shutil.move(str(file_path), str(dest))
                else:
                    shutil.copy2(file_path, dest)
            continue

        metadata_text = extract_pdf_metadata_text(file_path)
        text = extract_pdf_text(file_path, max_pages=max_pages)
        doi, basis, candidates = select_match(
            file_path=file_path,
            known_records=known_records,
            text=text,
            metadata_text=metadata_text,
            enable_title_match=enable_title_match,
            min_title_score=min_title_score,
            min_title_margin=min_title_margin,
            filename_slug_lookup=filename_slug_lookup,
            source_filename_lookup=source_filename_lookup,
            pii_lookup=pii_lookup,
        )
        if not doi:
            row = {
                **base,
                "status": "needs_review",
                "reason": basis,
                "candidate_matches_json": json.dumps(candidates, ensure_ascii=False),
            }
            review_rows.append(row)
            continue

        canonical_name = pdf_filename_for_doi(doi)
        dest = pdf_dir / canonical_name
        record = known_records.get(doi, {})
        row = {
            **base,
            "status": "matched",
            "doi": doi,
            "match_basis": basis,
            "study_title": clean(record.get("study_title", "") or record.get("title", "")),
            "destination": str(dest),
            "candidate_matches_json": json.dumps(candidates, ensure_ascii=False),
        }
        if dest.exists() and dest.is_file():
            dest_hash = sha256_file(dest)
            if dest_hash == source_hash:
                row["status"] = "already_present"
                skipped.append(row)
                imported.append(row)
                if apply and move and file_path.resolve() != dest.resolve():
                    file_path.unlink()
                continue
            if replace_existing:
                backup_dest = replaced_prior_path(conflict_dir, canonical_name, dest_hash)
                row["status"] = "replaced_existing_pdf"
                row["previous_destination"] = str(dest)
                row["previous_sha256"] = dest_hash
                row["previous_pdf_backup_path"] = str(backup_dest)
                imported.append(row)
                if apply:
                    conflict_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest), str(backup_dest))
                    if move:
                        shutil.move(str(file_path), str(dest))
                    else:
                        shutil.copy2(file_path, dest)
                continue
            conflict_dest = conflict_path(conflict_dir, canonical_name, source_hash)
            row["status"] = "conflict_existing_pdf"
            row["destination"] = str(conflict_dest)
            review_rows.append(row)
            if apply:
                conflict_dir.mkdir(parents=True, exist_ok=True)
                if move:
                    shutil.move(str(file_path), str(conflict_dest))
                else:
                    shutil.copy2(file_path, conflict_dest)
            continue

        imported.append(row)
        if apply:
            pdf_dir.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(file_path), str(dest))
            else:
                shutil.copy2(file_path, dest)

    candidate_table_update = update_candidate_table_for_imports(candidate_table, imported, apply=apply)
    counts = {
        "inbox_pdf_files": len(files),
        "imported_or_matched": len(imported),
        "new_imports": sum(1 for row in imported if row.get("status") == "matched"),
        "replaced_existing": sum(1 for row in imported if row.get("status") == "replaced_existing_pdf"),
        "already_present": sum(1 for row in imported if row.get("status") == "already_present"),
        "needs_review": sum(1 for row in review_rows if row.get("status") == "needs_review"),
        "conflicts": sum(1 for row in review_rows if row.get("status") == "conflict_existing_pdf"),
        "invalid_pdf": len(invalid),
        "candidate_rows_updated": candidate_table_update["candidate_rows_updated"],
    }
    report = {
        "generated_at_utc": now_utc(),
        "inputs": {
            "inbox_dir": str(inbox_dir),
            "pdf_dir": str(pdf_dir),
            "manual_csv": str(manual_csv.resolve()),
            "candidate_table": str(candidate_table.resolve()),
            "metadata_table": str(metadata_table.resolve()),
            "apply": apply,
            "move": move,
            "enable_title_match": enable_title_match,
            "min_title_score": min_title_score,
            "min_title_margin": min_title_margin,
            "max_pages": max_pages,
            "replace_existing": replace_existing,
        },
        "counts": counts,
        "imported": imported,
        "review": review_rows,
        "invalid": invalid,
        "skipped": skipped,
        "candidate_table_update": candidate_table_update,
    }
    write_json(report_path, report)
    write_csv(review_csv, review_rows)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import manually downloaded PDFs from an inbox.")
    parser.add_argument("--inbox-dir", default=str(DEFAULT_INBOX_DIR))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--conflict-dir", default=str(DEFAULT_CONFLICT_DIR))
    parser.add_argument("--invalid-dir", default=str(DEFAULT_INVALID_DIR))
    parser.add_argument("--manual-csv", default=str(DEFAULT_MANUAL_CSV))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW_CSV))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--move", action="store_true", help="Move matched inbox files instead of copying them.")
    parser.add_argument("--disable-title-match", action="store_true")
    parser.add_argument("--min-title-score", type=float, default=0.86)
    parser.add_argument("--min-title-margin", type=float, default=0.12)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace a differing canonical PDF after backing up the prior file to the conflict directory.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = import_manual_pdfs(
        inbox_dir=Path(args.inbox_dir),
        pdf_dir=Path(args.pdf_dir),
        conflict_dir=Path(args.conflict_dir),
        invalid_dir=Path(args.invalid_dir),
        manual_csv=Path(args.manual_csv),
        candidate_table=Path(args.candidate_table),
        metadata_table=Path(args.metadata_table),
        report_path=Path(args.report),
        review_csv=Path(args.review_csv),
        apply=bool(args.apply),
        move=bool(args.move),
        enable_title_match=not bool(args.disable_title_match),
        min_title_score=float(args.min_title_score),
        min_title_margin=float(args.min_title_margin),
        max_pages=int(args.max_pages),
        replace_existing=bool(args.replace_existing),
    )
    counts = report["counts"]
    print(f"Inbox PDF files: {counts['inbox_pdf_files']:,}")
    print(f"New imports: {counts['new_imports']:,}")
    print(f"Replaced existing: {counts['replaced_existing']:,}")
    print(f"Already present: {counts['already_present']:,}")
    print(f"Needs review: {counts['needs_review']:,}")
    print(f"Conflicts: {counts['conflicts']:,}")
    print(f"Invalid PDFs: {counts['invalid_pdf']:,}")
    print(f"Candidate rows updated: {counts['candidate_rows_updated']:,}")
    print(f"Apply mode: {bool(args.apply)}")
    print(f"Report: {Path(args.report).resolve()}")
    print(f"Review CSV: {Path(args.review_csv).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
