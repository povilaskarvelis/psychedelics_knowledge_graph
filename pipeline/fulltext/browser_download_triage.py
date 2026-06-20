#!/usr/bin/env python3
"""Triage files saved by browser-based manual PDF recovery."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOAD_DIR = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_QUARANTINE_DIR = ROOT / "data" / "raw" / "papers" / "manual_pdf_rejected_downloads"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "browser_download_triage_report.json"
DEFAULT_REVIEW_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "browser_download_triage_review.csv"

PDF_STATUS = "valid_pdf"
NO_ACCESS_STATUS = "no_access_or_paywalled"
COOKIE_STATUS = "cookie_or_interstitial_block"
HTML_STATUS = "html_saved_non_pdf"
NON_PDF_STATUS = "non_pdf_saved"

NO_ACCESS_PATTERNS = (
    "you do not have access",
    "do not have access to this content",
    "get access",
    "purchase access",
    "rent this article",
    "subscribe to this journal",
    "institution login",
    "institutional login",
    "log in to access",
    "login to access",
    "sign in to access",
    "access options",
    "request permissions",
)
COOKIE_PATTERNS = (
    "we use cookies",
    "accept cookies",
    "cookie policy",
    "checking your browser",
    "browser check",
    "enable javascript",
    "cloudflare",
    "captcha",
    "recaptcha",
)
HTML_SUFFIXES = {".html", ".htm", ".xhtml", ".shtml"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def looks_like_pdf(path: Path) -> bool:
    try:
        raw = path.read_bytes()[:2048].lstrip(b"\x00\t\r\n\f ")
    except Exception:
        return False
    return raw.startswith(b"%PDF-")


def looks_like_html(path: Path) -> bool:
    if path.suffix.lower() in HTML_SUFFIXES:
        return True
    try:
        raw = path.read_bytes()[:4096].lstrip(b"\x00\t\r\n\f ")
    except Exception:
        return False
    return raw[:256].lower().startswith((b"<!doctype html", b"<html", b"<?xml"))


def read_text_sample(path: Path, max_bytes: int) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
    except Exception:
        return ""
    return raw.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def matched_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    lowered = normalize_text(text)
    return [pattern for pattern in patterns if pattern in lowered]


def classify_html_text(text: str) -> tuple[str, list[str]]:
    no_access = matched_patterns(text, NO_ACCESS_PATTERNS)
    if no_access:
        return NO_ACCESS_STATUS, no_access
    cookie = matched_patterns(text, COOKIE_PATTERNS)
    if cookie:
        return COOKIE_STATUS, cookie
    return HTML_STATUS, []


def classify_download_artifact(path: Path, *, max_text_bytes: int = 512_000) -> dict:
    status = NON_PDF_STATUS
    reason = ""
    matches: list[str] = []
    if looks_like_pdf(path):
        status = PDF_STATUS
        reason = "pdf_magic_header"
    elif looks_like_html(path):
        status, matches = classify_html_text(read_text_sample(path, max_text_bytes))
        reason = "html_page_saved"
    else:
        reason = "saved_file_is_not_pdf_or_html"

    try:
        stat = path.stat()
        size = stat.st_size
        mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).isoformat()
    except OSError:
        size = 0
        mtime = ""

    return {
        "file": str(path.resolve()),
        "filename": path.name,
        "status": status,
        "reason": reason,
        "matched_patterns": matches,
        "size_bytes": size,
        "modified_utc": mtime,
        "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
    }


def safe_quarantine_path(path: Path, quarantine_dir: Path, status: str) -> Path:
    dest_dir = quarantine_dir / status
    dest = dest_dir / path.name
    if not dest.exists():
        return dest
    if path.is_dir():
        index = 1
        while True:
            candidate = dest_dir / f"{path.name}__{index}"
            if not candidate.exists():
                return candidate
            index += 1
    digest = sha256_file(path)[:12]
    return dest_dir / f"{path.stem}__{digest}{path.suffix}"


def maybe_quarantine(path: Path, quarantine_dir: Path, status: str, *, apply: bool) -> str:
    dest = safe_quarantine_path(path, quarantine_dir, status)
    if not apply:
        return str(dest.resolve())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))
    return str(dest.resolve())


def html_companion_dirs(path: Path) -> list[Path]:
    if path.suffix.lower() not in HTML_SUFFIXES:
        return []
    return [path.with_name(f"{path.stem}_files")]


def maybe_quarantine_companion_dirs(path: Path, quarantine_dir: Path, status: str, *, apply: bool) -> list[str]:
    moved: list[str] = []
    for companion in html_companion_dirs(path):
        if not companion.exists() or not companion.is_dir():
            continue
        moved.append(maybe_quarantine(companion, quarantine_dir, status, apply=apply))
    return moved


def iter_download_artifacts(download_dir: Path) -> list[Path]:
    if not download_dir.exists():
        return []
    return sorted(path for path in download_dir.iterdir() if path.is_file() and not path.name.startswith("."))


def iter_orphan_html_companion_dirs(download_dir: Path) -> list[Path]:
    if not download_dir.exists():
        return []
    out: list[Path] = []
    for path in sorted(download_dir.iterdir()):
        if not path.is_dir() or path.name.startswith(".") or not path.name.endswith("_files"):
            continue
        stem = path.name[: -len("_files")]
        if any((download_dir / f"{stem}{suffix}").exists() for suffix in HTML_SUFFIXES):
            continue
        out.append(path)
    return out


def triage_download_dir(
    download_dir: Path,
    *,
    quarantine_dir: Path,
    apply: bool,
    quarantine_non_pdf: bool,
    max_text_bytes: int,
) -> list[dict]:
    records: list[dict] = []
    for path in iter_download_artifacts(download_dir):
        record = classify_download_artifact(path, max_text_bytes=max_text_bytes)
        status = clean(record["status"])
        if status != PDF_STATUS and quarantine_non_pdf:
            record["companion_quarantine_paths"] = maybe_quarantine_companion_dirs(
                path,
                quarantine_dir,
                status,
                apply=apply,
            )
            record["quarantine_path"] = maybe_quarantine(path, quarantine_dir, status, apply=apply)
            record["quarantined"] = bool(apply)
        else:
            record["companion_quarantine_paths"] = []
            record["quarantine_path"] = ""
            record["quarantined"] = False
        records.append(record)
    if quarantine_non_pdf:
        for path in iter_orphan_html_companion_dirs(download_dir):
            record = {
                "file": str(path.resolve()),
                "filename": path.name,
                "status": HTML_STATUS,
                "reason": "orphan_html_companion_dir",
                "matched_patterns": [],
                "size_bytes": 0,
                "modified_utc": "",
                "sha256": "",
                "companion_quarantine_paths": [],
                "quarantine_path": maybe_quarantine(path, quarantine_dir, HTML_STATUS, apply=apply),
                "quarantined": bool(apply),
            }
            records.append(record)
    return records


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


def build_report(download_dir: Path, quarantine_dir: Path, records: list[dict], *, apply: bool, quarantine_non_pdf: bool) -> dict:
    return {
        "created_utc": now_utc(),
        "download_dir": str(download_dir.resolve()),
        "quarantine_dir": str(quarantine_dir.resolve()),
        "apply": apply,
        "quarantine_non_pdf": quarantine_non_pdf,
        "counts": dict(Counter(clean(record.get("status", "")) for record in records)),
        "records": records,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-dir", default=str(DEFAULT_DOWNLOAD_DIR))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW_CSV))
    parser.add_argument("--max-text-bytes", type=int, default=512_000)
    parser.add_argument("--quarantine-non-pdf", action="store_true", help="Move HTML and other non-PDF saves out of the inbox.")
    parser.add_argument("--apply", action="store_true", help="Apply quarantine moves. Without this, only report planned actions.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    download_dir = Path(args.download_dir).resolve()
    quarantine_dir = Path(args.quarantine_dir).resolve()
    records = triage_download_dir(
        download_dir,
        quarantine_dir=quarantine_dir,
        apply=bool(args.apply),
        quarantine_non_pdf=bool(args.quarantine_non_pdf),
        max_text_bytes=max(1024, int(args.max_text_bytes)),
    )
    report = build_report(
        download_dir,
        quarantine_dir,
        records,
        apply=bool(args.apply),
        quarantine_non_pdf=bool(args.quarantine_non_pdf),
    )
    write_json(Path(args.report).resolve(), report)
    write_csv(Path(args.review_csv).resolve(), records)
    print(
        "BROWSER_DOWNLOAD_TRIAGE: "
        f"files={len(records):,} counts={report['counts']} report={Path(args.report).resolve()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
