#!/usr/bin/env python3
"""Build and maintain a local paper library with abstracts and OA PDF sync."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    out: Dict[str, dict] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[current] = {}
            continue
        if current and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"').strip("'")
            parsed: object = value
            if value == "":
                parsed = ""
            else:
                try:
                    parsed = float(value) if "." in value else int(value)
                except ValueError:
                    parsed = value
            out[current][key.strip()] = parsed
    return out


def read_float(maybe_value: object, default: float) -> float:
    if maybe_value is None:
        return default
    try:
        return float(maybe_value)
    except Exception:
        return default


def read_int(maybe_value: object, default: int) -> int:
    if maybe_value is None:
        return default
    try:
        return int(maybe_value)
    except Exception:
        return default


class RateLimitedHttpClient:
    def __init__(self, rps: float, max_retries: int, timeout_sec: int = 40, user_agent: str = "kg-pipeline/0.1"):
        self.rps = max(0.01, rps)
        self.min_interval = 1.0 / self.rps
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self._last_request_ts = 0.0

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)
        req = Request(url, headers=req_headers)
        with urlopen(req, timeout=self.timeout_sec) as response:
            self._last_request_ts = time.monotonic()
            return response.read()

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                return self._request_bytes(url=url, headers=headers)
            except HTTPError as err:
                self._last_request_ts = time.monotonic()
                retryable = err.code in {429, 500, 502, 503, 504}
                if attempt >= self.max_retries or not retryable:
                    raise
                retry_after = err.headers.get("Retry-After") if err.headers else None
                if retry_after and retry_after.isdigit():
                    delay = max(backoff, float(retry_after))
                else:
                    delay = backoff
                time.sleep(delay + random.uniform(0.0, 0.35))
                backoff *= 1.7
            except URLError:
                self._last_request_ts = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(backoff + random.uniform(0.0, 0.35))
                backoff *= 1.7
        raise RuntimeError("Unreachable retry state")

    def get_json(self, url: str, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None) -> dict:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        body = self.get_bytes(url=full_url, headers=headers)
        return json.loads(body.decode("utf-8"))


def parse_doi_queue(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_no, parts in enumerate(csv.reader(handle), start=1):
            if not parts:
                continue
            first = normalize(parts[0])
            if not first or first.startswith("#"):
                continue

            parts = [normalize(p) for p in parts]
            doi = normalize_doi(parts[0] if len(parts) > 0 else "")
            if not doi:
                raise ValueError(f"Line {line_no}: DOI is required")

            rows.append(
                {
                    "study_doi": doi,
                    "compound": parts[1] if len(parts) > 1 else "",
                    "entity": parts[2] if len(parts) > 2 else "",
                    "study_title": parts[3] if len(parts) > 3 else "",
                    "study_year": parts[4] if len(parts) > 4 else "",
                    "authors": parts[5] if len(parts) > 5 else "",
                }
            )
    return rows


def dedupe_queue_rows(rows: List[dict]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        key = doi.lower()
        existing = merged.get(key)
        context = {
            "compound": normalize(row.get("compound", "")),
            "entity": normalize(row.get("entity", "")),
            "study_title": normalize(row.get("study_title", "")),
            "study_year": normalize(row.get("study_year", "")),
        }
        if not existing:
            merged[key] = {
                "study_doi": doi,
                "study_title": normalize(row.get("study_title", "")),
                "study_year": normalize(row.get("study_year", "")),
                "authors": normalize(row.get("authors", "")),
                "contexts": [context],
            }
            continue
        if not normalize(existing.get("study_title", "")) and context["study_title"]:
            existing["study_title"] = context["study_title"]
        if not normalize(existing.get("study_year", "")) and context["study_year"]:
            existing["study_year"] = context["study_year"]
        if not normalize(existing.get("authors", "")) and normalize(row.get("authors", "")):
            existing["authors"] = normalize(row.get("authors", ""))
        if context not in existing["contexts"]:
            existing["contexts"].append(context)
    return sorted(merged.values(), key=lambda r: normalize(r.get("study_doi", "")))


def authors_from_openalex(authorships: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for authorship in authorships:
        author_obj = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author_obj, dict):
            name = normalize(author_obj.get("display_name", ""))
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def decode_openalex_abstract(index: object) -> str:
    if not isinstance(index, dict):
        return ""
    words_by_position: Dict[int, str] = {}
    max_position = -1
    for token, positions in index.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and pos >= 0:
                words_by_position[pos] = token
                if pos > max_position:
                    max_position = pos
    if max_position < 0:
        return ""
    ordered = [words_by_position.get(i, "") for i in range(max_position + 1)]
    return " ".join([w for w in ordered if w]).strip()


def lookup_openalex_work(client: RateLimitedHttpClient, doi: str, email: str) -> Optional[dict]:
    endpoint = "https://api.openalex.org/works"
    params = {
        "filter": f"doi:https://doi.org/{doi}",
        "per-page": 1,
        "select": (
            "doi,ids,display_name,publication_year,authorships,"
            "abstract_inverted_index,open_access,best_oa_location,primary_location,locations"
        ),
    }
    if email:
        params["mailto"] = email
    payload = client.get_json(endpoint, params=params, headers={})
    results = payload.get("results", []) or []
    if not results:
        return None
    return results[0]


def is_probable_pdf_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".pdf") or ".pdf?" in lowered


def extract_oa_fields(work: dict) -> Dict[str, str]:
    open_access = work.get("open_access", {}) if isinstance(work, dict) else {}
    best_loc = work.get("best_oa_location", {}) if isinstance(work, dict) else {}
    primary_loc = work.get("primary_location", {}) if isinstance(work, dict) else {}
    locations = work.get("locations", []) if isinstance(work, dict) else []

    pdf_candidates: List[str] = []

    best_pdf = normalize(best_loc.get("pdf_url", "")) if isinstance(best_loc, dict) else ""
    primary_pdf = normalize(primary_loc.get("pdf_url", "")) if isinstance(primary_loc, dict) else ""
    if best_pdf:
        pdf_candidates.append(best_pdf)
    if primary_pdf and primary_pdf not in pdf_candidates:
        pdf_candidates.append(primary_pdf)

    for loc in locations if isinstance(locations, list) else []:
        if not isinstance(loc, dict):
            continue
        pdf_url = normalize(loc.get("pdf_url", ""))
        if pdf_url and pdf_url not in pdf_candidates:
            pdf_candidates.append(pdf_url)
        landing_page = normalize(loc.get("landing_page_url", ""))
        if landing_page and is_probable_pdf_url(landing_page) and landing_page not in pdf_candidates:
            pdf_candidates.append(landing_page)

    oa_url = normalize(open_access.get("oa_url", "")) if isinstance(open_access, dict) else ""
    if oa_url and is_probable_pdf_url(oa_url) and oa_url not in pdf_candidates:
        pdf_candidates.append(oa_url)

    return {
        "is_oa": "true" if bool(open_access.get("is_oa")) else "false",
        "oa_status": normalize(open_access.get("oa_status", "")),
        "oa_url": oa_url,
        "best_pdf_url": pdf_candidates[0] if pdf_candidates else "",
    }


def pdf_filename_for_doi(doi: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "_", normalize_doi(doi).lower())
    slug = re.sub(r"_+", "_", slug).strip("._")
    if not slug:
        slug = "paper"
    digest = hashlib.sha1(normalize_doi(doi).encode("utf-8")).hexdigest()[:10]
    slug = slug[:90]
    return f"{slug}__{digest}.pdf"


def looks_like_pdf_bytes(raw: bytes) -> bool:
    if not raw:
        return False
    # Some providers prepend whitespace/newlines before the PDF header.
    lead = raw[:2048].lstrip(b"\x00\t\r\n\f ")
    return lead.startswith(b"%PDF-")


def file_is_valid_pdf(path: Path) -> bool:
    try:
        head = path.read_bytes()[:4096]
    except Exception:
        return False
    return looks_like_pdf_bytes(head)


def read_existing_json(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def merge_existing_rows(existing: List[dict], fresh: List[dict]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for row in existing + fresh:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        key = doi.lower()
        if key not in merged:
            merged[key] = row
            continue
        # Prefer latest/fresh row values while preserving historical context list.
        previous = merged[key]
        current_contexts = previous.get("contexts", []) if isinstance(previous.get("contexts", []), list) else []
        new_contexts = row.get("contexts", []) if isinstance(row.get("contexts", []), list) else []
        context_out = []
        for context in current_contexts + new_contexts:
            if context not in context_out:
                context_out.append(context)
        merged[key] = {**previous, **row}
        merged[key]["contexts"] = context_out

    out = list(merged.values())
    out.sort(key=lambda r: (normalize(r.get("library_status", "")), normalize(r.get("study_doi", ""))))
    return out


def write_json(path: Path, rows: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: str) -> str:
    text = normalize(value).replace("\n", " ")
    return text.replace("|", "\\|")


def row_markdown_line(row: dict, include_status: bool) -> str:
    doi = normalize(row.get("study_doi", ""))
    doi_cell = f"[{escape_md(doi)}](https://doi.org/{escape_md(doi)})" if doi else ""
    title = escape_md(row.get("study_title", ""))
    year = escape_md(row.get("study_year", ""))
    status = escape_md(row.get("library_status", ""))
    reason = escape_md(row.get("action_reason", ""))
    pdf_path = escape_md(row.get("pdf_local_path", ""))

    if include_status:
        return f"| {doi_cell} | {title} | {year} | {status} | {reason} | {pdf_path} |"
    return f"| {doi_cell} | {title} | {year} | {pdf_path} |"


def write_inventory_markdown(
    path: Path,
    dataset: str,
    generated_at: str,
    in_database: List[dict],
    missing_pdf: List[dict],
) -> None:
    lines = [
        f"# Paper PDF Coverage ({dataset})",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Papers with local PDF: `{len(in_database)}`",
        f"- Papers missing local PDF: `{len(missing_pdf)}`",
        "",
        "## Papers With Local PDF",
        "",
        "| DOI | Title | Year | PDF Path |",
        "| --- | --- | --- | --- |",
    ]

    if in_database:
        for row in in_database:
            lines.append(row_markdown_line(row, include_status=False))
    else:
        lines.append("|  |  |  |  |")

    lines.extend(
        [
            "",
            "## Papers Missing Local PDF",
            "",
            "| DOI | Title | Year | Status | Reason | PDF Path |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    if missing_pdf:
        for row in missing_pdf:
            lines.append(row_markdown_line(row, include_status=True))
    else:
        lines.append("|  |  |  |  |  |  |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_inventory_row(row: dict) -> dict:
    context_labels = []
    for ctx in row.get("contexts", []) if isinstance(row.get("contexts", []), list) else []:
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        if compound or entity:
            context_labels.append(f"{compound} -> {entity}".strip(" ->"))
    return {
        "study_doi": normalize(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        "open_access_is_oa": normalize(row.get("open_access_is_oa", "")),
        "open_access_status": normalize(row.get("open_access_status", "")),
        "best_pdf_url": normalize(row.get("best_pdf_url", "")),
        "pdf_local_path": normalize(row.get("pdf_local_path", "")),
        "pdf_download_status": normalize(row.get("pdf_download_status", "")),
        "library_status": normalize(row.get("library_status", "")),
        "action_reason": normalize(row.get("action_reason", "")),
        "contexts": " | ".join(context_labels),
    }


def flatten_db_row(row: dict) -> dict:
    out = dict(row)
    contexts = out.get("contexts", [])
    out["contexts"] = json.dumps(contexts, ensure_ascii=False) if isinstance(contexts, list) else normalize(contexts)
    return out


def download_pdf(
    client: RateLimitedHttpClient,
    pdf_url: str,
    target_path: Path,
) -> Tuple[str, str, int]:
    if target_path.exists() and target_path.stat().st_size > 0:
        if file_is_valid_pdf(target_path):
            return "already_present", "", int(target_path.stat().st_size)
        return "invalid_pdf_existing", "local_file_is_not_pdf", int(target_path.stat().st_size)

    body = client.get_bytes(
        url=pdf_url,
        headers={
            "Accept": "application/pdf,*/*;q=0.9",
        },
    )
    if not body:
        return "download_failed", "empty_response", 0
    if not looks_like_pdf_bytes(body):
        return "invalid_pdf_content", "response_not_pdf", 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(".tmp")
    tmp_path.write_bytes(body)
    tmp_path.replace(target_path)
    return "downloaded", "", len(body)


def classify_library_status(row: dict) -> str:
    metadata_error = normalize(row.get("metadata_lookup_error", ""))
    pdf_path = normalize(row.get("pdf_local_path", ""))
    download_status = normalize(row.get("pdf_download_status", ""))
    is_oa = normalize(row.get("open_access_is_oa", "")).lower() == "true"
    best_pdf_url = normalize(row.get("best_pdf_url", ""))
    oa_status = normalize(row.get("open_access_status", "")).lower()

    if metadata_error:
        return "needs_download"

    if pdf_path and download_status in {"downloaded", "already_present"}:
        return "in_database"
    if is_oa and best_pdf_url:
        return "needs_download"
    if is_oa and not best_pdf_url:
        return "needs_download"
    if oa_status == "closed":
        return "needs_manual_access"
    return "needs_manual_access"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync local paper library from DOI queue: fetch abstracts, "
            "check OA, download PDFs, and emit inventory report"
        )
    )
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--doi-file", default="", help="DOI queue file (defaults to discovered queue for dataset)")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--skip-download", action="store_true", help="Do not download PDFs; metadata only")
    parser.add_argument("--replace", action="store_true", help="Replace paper DB output instead of merging")
    parser.add_argument("--paper-db-json", default="", help="Paper DB JSON output path")
    parser.add_argument("--paper-db-csv", default="", help="Paper DB CSV output path")
    parser.add_argument("--inventory-json", default="", help="Inventory report JSON output path")
    parser.add_argument("--inventory-csv", default="", help="Inventory table CSV output path")
    parser.add_argument("--inventory-md", default="", help="Inventory Markdown report output path")
    parser.add_argument("--pdf-dir", default="", help="Directory to store downloaded PDFs")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N papers processed (default: 25)",
    )
    args = parser.parse_args()

    config = parse_simple_yaml(Path(args.config).resolve())
    oa_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    s2_cfg = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar", {}), dict) else {}

    openalex_email = args.openalex_email or str(oa_cfg.get("email", ""))
    openalex_rps = args.openalex_rps if args.openalex_rps is not None else read_float(oa_cfg.get("rate_limit_per_sec"), 2.0)
    max_retries = args.max_retries if args.max_retries is not None else read_int(s2_cfg.get("max_retries"), 4)

    doi_file = (
        Path(args.doi_file).resolve()
        if args.doi_file
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.discovered.txt"
    )
    if not doi_file.exists():
        raise SystemExit(f"DOI queue file not found: {doi_file}")

    paper_db_json = (
        Path(args.paper_db_json).resolve()
        if args.paper_db_json
        else ROOT / "data" / "processed" / f"paper_library_{args.dataset}.json"
    )
    paper_db_csv = (
        Path(args.paper_db_csv).resolve()
        if args.paper_db_csv
        else ROOT / "data" / "processed" / f"paper_library_{args.dataset}.csv"
    )
    inventory_json = (
        Path(args.inventory_json).resolve()
        if args.inventory_json
        else ROOT / "data" / "processed" / f"paper_inventory_{args.dataset}.json"
    )
    inventory_csv = (
        Path(args.inventory_csv).resolve()
        if args.inventory_csv
        else ROOT / "data" / "processed" / f"paper_inventory_{args.dataset}.csv"
    )
    inventory_md = (
        Path(args.inventory_md).resolve()
        if args.inventory_md
        else ROOT / "data" / "processed" / f"paper_inventory_{args.dataset}.md"
    )
    pdf_dir = (
        Path(args.pdf_dir).resolve()
        if args.pdf_dir
        else ROOT / "data" / "raw" / "papers" / args.dataset / "pdfs"
    )

    http_client = RateLimitedHttpClient(
        rps=openalex_rps,
        max_retries=max_retries,
        user_agent="kg-pipeline/paper-library",
    )

    queue_rows = parse_doi_queue(doi_file)
    papers = dedupe_queue_rows(queue_rows)

    output_rows: List[dict] = []
    fetch_errors: List[dict] = []
    downloaded_now = 0
    already_present = 0
    download_failures = 0
    running_in_database = 0
    running_needs_download = 0
    running_needs_manual = 0
    total_papers = len(papers)

    for idx, paper in enumerate(papers, start=1):
        doi = normalize_doi(paper.get("study_doi", ""))
        if not doi:
            continue

        metadata_error = ""
        work = None
        try:
            work = lookup_openalex_work(http_client, doi=doi, email=openalex_email)
        except Exception as err:
            metadata_error = f"{type(err).__name__}: {err}"
            fetch_errors.append({"study_doi": doi, "error": metadata_error})

        if work:
            ids = work.get("ids", {}) if isinstance(work, dict) else {}
            openalex_id = normalize(ids.get("openalex", "")) if isinstance(ids, dict) else ""
            study_title = normalize(work.get("display_name", "")) or normalize(paper.get("study_title", ""))
            study_year = normalize(work.get("publication_year", "")) or normalize(paper.get("study_year", ""))
            authors = authors_from_openalex(work.get("authorships", []) or []) or normalize(paper.get("authors", ""))
            abstract = decode_openalex_abstract(work.get("abstract_inverted_index", {}))
            oa = extract_oa_fields(work)
        else:
            openalex_id = ""
            study_title = normalize(paper.get("study_title", ""))
            study_year = normalize(paper.get("study_year", ""))
            authors = normalize(paper.get("authors", ""))
            abstract = ""
            oa = {"is_oa": "false", "oa_status": "", "oa_url": "", "best_pdf_url": ""}

        pdf_filename = pdf_filename_for_doi(doi)
        pdf_path = pdf_dir / pdf_filename
        best_pdf_url = normalize(oa.get("best_pdf_url", ""))
        is_oa = normalize(oa.get("is_oa", "")).lower() == "true"

        download_status = "not_attempted"
        download_error = ""
        pdf_size_bytes = 0
        pdf_sha256 = ""

        had_invalid_local_pdf = False
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            if file_is_valid_pdf(pdf_path):
                download_status = "already_present"
                already_present += 1
                pdf_size_bytes = int(pdf_path.stat().st_size)
                pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            else:
                had_invalid_local_pdf = True
                download_status = "invalid_pdf_existing"
                download_error = "local_file_is_not_pdf"
                # Remove bad local artifact so subsequent retries can fetch cleanly.
                try:
                    pdf_path.unlink()
                except Exception:
                    pass

        if download_status == "already_present":
            pass
        elif args.skip_download:
            if had_invalid_local_pdf:
                download_status = "invalid_pdf_existing"
            elif is_oa and best_pdf_url:
                download_status = "skipped"
            elif is_oa and not best_pdf_url:
                download_status = "no_pdf_url"
            else:
                download_status = "not_open_access"
        elif is_oa and best_pdf_url:
            try:
                download_status, download_error, pdf_size_bytes = download_pdf(
                    client=http_client,
                    pdf_url=best_pdf_url,
                    target_path=pdf_path,
                )
                if download_status == "downloaded":
                    downloaded_now += 1
                elif download_status == "already_present":
                    already_present += 1
                elif download_status in {"invalid_pdf_existing", "invalid_pdf_content"}:
                    download_failures += 1
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    if file_is_valid_pdf(pdf_path):
                        pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                    else:
                        download_status = "invalid_pdf_existing"
                        download_error = "local_file_is_not_pdf"
                        try:
                            pdf_path.unlink()
                        except Exception:
                            pass
            except Exception as err:
                download_status = "download_failed"
                download_error = f"{type(err).__name__}: {err}"
                download_failures += 1
        elif had_invalid_local_pdf:
            download_status = "invalid_pdf_existing"
            if not download_error:
                download_error = "local_file_is_not_pdf"
        elif is_oa and not best_pdf_url:
            download_status = "no_pdf_url"
        else:
            download_status = "not_open_access"

        action_reason = ""
        if metadata_error:
            action_reason = f"metadata_lookup_failed: {metadata_error}"
        elif download_error:
            action_reason = download_error
        elif download_status == "no_pdf_url":
            action_reason = "open_access_but_no_direct_pdf_url"
        elif download_status == "not_open_access":
            action_reason = "closed_or_unknown_access"

        row = {
            "study_doi": doi,
            "openalex_id": openalex_id,
            "study_title": study_title,
            "study_year": study_year,
            "authors": authors,
            "abstract": abstract,
            "metadata_lookup_error": metadata_error,
            "open_access_is_oa": "true" if is_oa else "false",
            "open_access_status": normalize(oa.get("oa_status", "")),
            "open_access_url": normalize(oa.get("oa_url", "")),
            "best_pdf_url": best_pdf_url,
            "pdf_local_path": (
                str(pdf_path)
                if pdf_path.exists() and pdf_path.stat().st_size > 0 and file_is_valid_pdf(pdf_path)
                else ""
            ),
            "pdf_size_bytes": pdf_size_bytes if pdf_size_bytes else "",
            "pdf_sha256": pdf_sha256,
            "pdf_download_status": download_status,
            "action_reason": action_reason,
            "contexts": paper.get("contexts", []),
            "last_checked_utc": now_utc(),
        }
        row["library_status"] = classify_library_status(row)
        status = normalize(row.get("library_status", ""))
        if status == "in_database":
            running_in_database += 1
        elif status == "needs_download":
            running_needs_download += 1
        elif status == "needs_manual_access":
            running_needs_manual += 1
        output_rows.append(row)

        should_print_progress = (
            args.progress_every > 0
            and (idx % args.progress_every == 0 or idx == total_papers)
        )
        if should_print_progress:
            pct = idx / max(1, total_papers) * 100.0
            print(
                "PROGRESS: sync "
                f"{idx}/{total_papers} ({pct:.1f}%) "
                f"in_db={running_in_database} needs_download={running_needs_download} "
                f"needs_manual={running_needs_manual} downloaded_now={downloaded_now} "
                f"already_present={already_present} failures={download_failures}",
                flush=True,
            )

    if not args.replace:
        existing_rows = read_existing_json(paper_db_json)
        output_rows = merge_existing_rows(existing_rows, output_rows)

    in_database = [row for row in output_rows if normalize(row.get("library_status", "")) == "in_database"]
    needs_download = [row for row in output_rows if normalize(row.get("library_status", "")) == "needs_download"]
    needs_manual_access = [row for row in output_rows if normalize(row.get("library_status", "")) == "needs_manual_access"]
    missing_pdf = [row for row in output_rows if normalize(row.get("library_status", "")) != "in_database"]

    inventory_rows = [compact_inventory_row(row) for row in output_rows]
    paper_db_csv_rows = [flatten_db_row(row) for row in output_rows]
    write_json(paper_db_json, output_rows)
    write_csv(paper_db_csv, paper_db_csv_rows)
    write_csv(inventory_csv, inventory_rows)
    write_inventory_markdown(
        path=inventory_md,
        dataset=args.dataset,
        generated_at=now_utc(),
        in_database=in_database,
        missing_pdf=missing_pdf,
    )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "doi_file": str(doi_file),
        "paper_db_json": str(paper_db_json),
        "paper_db_csv": str(paper_db_csv),
        "inventory_csv": str(inventory_csv),
        "inventory_md": str(inventory_md),
        "pdf_dir": str(pdf_dir),
        "settings": {
            "openalex_rps": openalex_rps,
            "max_retries": max_retries,
            "skip_download": args.skip_download,
            "replace": args.replace,
        },
        "counts": {
            "doi_rows_read": len(queue_rows),
            "unique_papers_in_queue": len(papers),
            "papers_in_database": len(in_database),
            "papers_needing_download": len(needs_download),
            "papers_needing_manual_access": len(needs_manual_access),
            "downloaded_now": downloaded_now,
            "already_present": already_present,
            "download_failures": download_failures,
            "invalid_pdf_artifacts": len(
                [
                    row
                    for row in output_rows
                    if normalize(row.get("pdf_download_status", "")) in {"invalid_pdf_existing", "invalid_pdf_content"}
                ]
            ),
            "metadata_errors": len(fetch_errors),
        },
        "in_database": [compact_inventory_row(row) for row in in_database],
        "needs_download": [compact_inventory_row(row) for row in needs_download],
        "needs_manual_access": [compact_inventory_row(row) for row in needs_manual_access],
        "metadata_errors": fetch_errors,
    }
    write_json(inventory_json, report)

    print(f"Dataset: {args.dataset}")
    print(f"DOI queue rows read: {len(queue_rows)}")
    print(f"Unique papers: {len(papers)}")
    print(f"In database: {len(in_database)}")
    print(f"Needs download: {len(needs_download)}")
    print(f"Needs manual access: {len(needs_manual_access)}")
    print(f"Downloaded now: {downloaded_now}")
    print(f"Already present: {already_present}")
    print(f"Download failures: {download_failures}")
    print(f"Paper DB JSON: {paper_db_json}")
    print(f"Inventory report JSON: {inventory_json}")
    print(f"Inventory CSV: {inventory_csv}")
    print(f"Inventory Markdown: {inventory_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
