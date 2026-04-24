#!/usr/bin/env python3
"""Convert local PDFs into structured full-text artifacts.

The converter is intentionally non-destructive: it writes artifacts and a report
under data/processed/fulltext, but it does not update curated claims or stubs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.review.pdf_runtime import ensure_pdf_runtime
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.pdf_runtime import ensure_pdf_runtime

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GROBID_URL = "http://localhost:8070/api/processFulltextDocument"

DATASET_CONFIG = {
    "mechanistic": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "out_dir": ROOT / "data" / "processed" / "fulltext" / "mechanistic",
        "report": ROOT / "data" / "processed" / "fulltext" / "fulltext_report_mechanistic.json",
    },
    "disorder": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "out_dir": ROOT / "data" / "processed" / "fulltext" / "disorder",
        "report": ROOT / "data" / "processed" / "fulltext" / "fulltext_report_disorder.json",
    },
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def doi_to_slug(raw: object) -> str:
    doi = normalize_doi(raw)
    slug = re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")
    return slug or "unknown_doi"


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_pdf_path(row: dict) -> Path | None:
    raw_path = normalize(row.get("pdf_local_path", ""))
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path if path.exists() and path.is_file() else None


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def grobid_alive_url(grobid_url: str) -> str:
    if grobid_url.endswith("/processFulltextDocument"):
        return grobid_url[: -len("/processFulltextDocument")] + "/isalive"
    return grobid_url.rstrip("/") + "/isalive"


def grobid_is_available(grobid_url: str, timeout_sec: int = 2) -> bool:
    request = urllib.request.Request(grobid_alive_url(grobid_url), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=max(1, timeout_sec)) as response:
            return response.status == 200 and normalize(response.read().decode("utf-8", errors="replace")) == "true"
    except Exception:
        return False


def stale_fulltext_locator_dois(curated_rows: Iterable[dict]) -> set[str]:
    out = set()
    for row in curated_rows:
        if normalize(row.get("access_level", "")) != "full_text_seen":
            continue
        if not normalize(row.get("evidence_locator", "")).lower().startswith("abstract snippet:"):
            continue
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out.add(doi)
    return out


def iter_pdf_rows(
    rows: Iterable[dict],
    only_missing_artifacts: bool,
    out_dir: Path,
    doi_filter: set[str] | None = None,
) -> Iterable[tuple[dict, Path, Path]]:
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        if doi_filter is not None and doi not in doi_filter:
            continue
        pdf_path = resolve_pdf_path(row)
        if not pdf_path:
            continue
        artifact_path = out_dir / f"{doi_to_slug(doi)}.json"
        if only_missing_artifacts and artifact_path.exists():
            continue
        yield row, pdf_path, artifact_path


def compact_text(raw: str) -> str:
    return re.sub(r"\s+", " ", normalize(raw)).strip()


def sections_from_markdown(markdown: str) -> List[dict]:
    sections: List[dict] = []
    current = {"heading": "Document", "level": 0, "text": ""}

    for line in normalize(markdown).splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            if compact_text(current["text"]):
                sections.append(section_summary(current))
            current = {
                "heading": compact_text(heading_match.group(2)),
                "level": len(heading_match.group(1)),
                "text": "",
            }
            continue
        current["text"] = f"{current['text']}\n{line}" if current["text"] else line

    if compact_text(current["text"]):
        sections.append(section_summary(current))
    return sections


def section_summary(section: dict) -> dict:
    text = compact_text(section.get("text", ""))
    return {
        "heading": normalize(section.get("heading", "")) or "Document",
        "level": int(section.get("level", 0) or 0),
        "char_count": len(text),
        "snippet": text[:500],
    }


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def element_text(element: ET.Element) -> str:
    return compact_text(" ".join(text for text in element.itertext() if normalize(text)))


def sections_from_tei(tei_xml: str) -> List[dict]:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return []

    sections: List[dict] = []
    for element in root.iter():
        name = local_name(element.tag)
        if name not in {"abstract", "div"}:
            continue

        heading = "Abstract" if name == "abstract" else ""
        for child in list(element):
            if local_name(child.tag) == "head":
                heading = element_text(child)
                break

        paragraphs = []
        for child in element.iter():
            if local_name(child.tag) == "p":
                text = element_text(child)
                if text:
                    paragraphs.append(text)
        body = compact_text(" ".join(paragraphs))
        if not body:
            continue
        sections.append(
            {
                "heading": heading or "Section",
                "level": 1,
                "char_count": len(body),
                "snippet": body[:500],
            }
        )
    return sections


def extraction_result(
    backend: str,
    status: str,
    text: str = "",
    sections: List[dict] | None = None,
    error: str = "",
    metadata: dict | None = None,
) -> dict:
    return {
        "backend": backend,
        "status": status,
        "char_count": len(text),
        "section_count": len(sections or []),
        "sections": sections or [],
        "text": text,
        "error": error,
        "metadata": metadata or {},
    }


def convert_with_docling(pdf_path: Path) -> dict:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception as err:
        return extraction_result("docling", "unavailable", error=f"{type(err).__name__}: {err}")

    try:
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        document = result.document
        markdown = document.export_to_markdown()
        return extraction_result(
            "docling",
            "ok",
            text=markdown,
            sections=sections_from_markdown(markdown),
            metadata={"format": "markdown"},
        )
    except Exception as err:
        return extraction_result("docling", "failed", error=f"{type(err).__name__}: {err}")


def multipart_body(
    file_path: Path,
    field_name: str = "input",
    filename: str = "paper.pdf",
    fields: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    boundary = f"----psychkg-{uuid.uuid4().hex}"
    payload = file_path.read_bytes()
    chunks = []
    for key, value in (fields or {}).items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"),
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode("utf-8"),
            payload,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), boundary


def convert_with_grobid(
    pdf_path: Path,
    grobid_url: str,
    timeout_sec: int,
    retries: int = 2,
    retry_wait_sec: int = 5,
    consolidate_header: str = "0",
    consolidate_citations: str = "0",
) -> dict:
    fields = {
        "consolidateHeader": consolidate_header,
        "consolidateCitations": consolidate_citations,
    }
    errors = []
    attempts = max(1, retries + 1)
    tei_xml = ""
    for attempt in range(1, attempts + 1):
        body, boundary = multipart_body(pdf_path, filename=pdf_path.name, fields=fields)
        request = urllib.request.Request(
            grobid_url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                tei_xml = response.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as err:
            errors.append(f"attempt {attempt}: HTTPError {err.code}: {err.reason}")
            if err.code != 503 or attempt == attempts:
                return extraction_result("grobid", "failed", error=" | ".join(errors))
        except urllib.error.URLError as err:
            errors.append(f"attempt {attempt}: {type(err).__name__}: {err}")
            if attempt == attempts:
                return extraction_result("grobid", "unavailable", error=" | ".join(errors))
        except Exception as err:
            errors.append(f"attempt {attempt}: {type(err).__name__}: {err}")
            if attempt == attempts:
                return extraction_result("grobid", "failed", error=" | ".join(errors))

        time.sleep(max(0, retry_wait_sec))

    sections = sections_from_tei(tei_xml)
    return extraction_result(
        "grobid",
        "ok" if tei_xml else "failed",
        text=tei_xml,
        sections=sections,
        error="" if tei_xml else "empty GROBID response",
        metadata={
            "format": "tei_xml",
            "service_url": grobid_url,
            "attempts": attempt,
            "consolidateHeader": consolidate_header,
            "consolidateCitations": consolidate_citations,
        },
    )


def convert_with_pdftotext(pdf_path: Path, timeout_sec: int) -> dict:
    if not shutil.which("pdftotext"):
        return extraction_result("pdftotext", "unavailable", error="pdftotext not found")

    cmd = ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except Exception as err:
        return extraction_result("pdftotext", "failed", error=f"{type(err).__name__}: {err}")
    if proc.returncode != 0:
        return extraction_result("pdftotext", "failed", error=compact_text(proc.stderr))

    text = normalize(proc.stdout)
    return extraction_result(
        "pdftotext",
        "ok" if text else "failed",
        text=text,
        sections=[{"heading": "Document", "level": 0, "char_count": len(text), "snippet": compact_text(text)[:500]}] if text else [],
        error="" if text else "empty pdftotext output",
        metadata={"format": "plain_text"},
    )


def backend_sequence(backend: str) -> List[str]:
    if backend == "auto":
        return ["grobid", "docling", "pdftotext"]
    if backend == "all":
        return ["grobid", "docling", "pdftotext"]
    return [backend]


def convert_pdf(
    pdf_path: Path,
    backend: str,
    grobid_url: str,
    timeout_sec: int,
    grobid_retries: int = 2,
    grobid_retry_wait_sec: int = 5,
    grobid_consolidate_header: str = "0",
    grobid_consolidate_citations: str = "0",
) -> List[dict]:
    results = []
    for name in backend_sequence(backend):
        if name == "docling":
            results.append(convert_with_docling(pdf_path))
        elif name == "grobid":
            results.append(
                convert_with_grobid(
                    pdf_path,
                    grobid_url=grobid_url,
                    timeout_sec=timeout_sec,
                    retries=max(0, grobid_retries),
                    retry_wait_sec=max(0, grobid_retry_wait_sec),
                    consolidate_header=grobid_consolidate_header,
                    consolidate_citations=grobid_consolidate_citations,
                )
            )
        elif name == "pdftotext":
            results.append(convert_with_pdftotext(pdf_path, timeout_sec=timeout_sec))
        else:  # pragma: no cover - argparse prevents this
            results.append(extraction_result(name, "failed", error=f"unknown backend `{name}`"))
    return results


def select_best_extraction(extractions: List[dict]) -> dict:
    ok = [entry for entry in extractions if entry.get("status") == "ok"]
    if not ok:
        return {}
    return max(ok, key=lambda entry: (int(entry.get("section_count", 0) or 0), int(entry.get("char_count", 0) or 0)))


def build_artifact(dataset: str, row: dict, pdf_path: Path, extractions: List[dict]) -> dict:
    best = select_best_extraction(extractions)
    return {
        "schema_version": "0.1",
        "created_at_utc": now_utc(),
        "dataset": dataset,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "openalex_id": normalize(row.get("openalex_id", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "pdf_local_path": str(pdf_path),
        "best_backend": normalize(best.get("backend", "")) if best else "",
        "best_char_count": int(best.get("char_count", 0) or 0) if best else 0,
        "best_section_count": int(best.get("section_count", 0) or 0) if best else 0,
        "extractions": extractions,
    }


def should_write_artifact(artifact_path: Path, artifact: dict, write_failed_artifacts: bool) -> tuple[bool, str]:
    if artifact.get("best_backend"):
        return True, "successful extraction"
    if write_failed_artifacts:
        return True, "failed artifacts explicitly enabled"

    existing = load_json_object(artifact_path)
    if existing.get("best_backend"):
        return False, "preserved existing successful artifact"
    if artifact_path.exists():
        return False, "left existing failed/unknown artifact unchanged"
    return False, "no successful extraction; artifact not written"


def report_row(row: dict, artifact_path: Path, artifact: dict) -> dict:
    statuses = {entry.get("backend", ""): entry.get("status", "") for entry in artifact.get("extractions", [])}
    errors = {entry.get("backend", ""): entry.get("error", "") for entry in artifact.get("extractions", []) if entry.get("error")}
    return {
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "artifact_path": str(artifact_path),
        "best_backend": artifact.get("best_backend", ""),
        "best_char_count": artifact.get("best_char_count", 0),
        "best_section_count": artifact.get("best_section_count", 0),
        "statuses": statuses,
        "errors": errors,
        "write_status": artifact.get("_write_status", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert local PDFs into full-text artifacts")
    parser.add_argument("--dataset", choices=sorted(DATASET_CONFIG), required=True)
    parser.add_argument("--paper-library", default="", help="Override paper-library JSON path")
    parser.add_argument("--curated-json", default="", help="Override curated claims JSON path")
    parser.add_argument("--out-dir", default="", help="Override artifact output directory")
    parser.add_argument("--report", default="", help="Override report JSON path")
    parser.add_argument("--backend", choices=["auto", "all", "docling", "grobid", "pdftotext"], default="auto")
    parser.add_argument("--doi-file", default="", help="Optional DOI list to restrict conversion candidates")
    parser.add_argument(
        "--stale-fulltext-locators",
        action="store_true",
        help="Restrict to curated full_text_seen rows whose evidence locator still starts with `Abstract snippet:`",
    )
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument("--grobid-retries", type=int, default=2)
    parser.add_argument("--grobid-retry-wait-sec", type=int, default=5)
    parser.add_argument("--grobid-consolidate-header", choices=["0", "1", "2", "3"], default="0")
    parser.add_argument("--grobid-consolidate-citations", choices=["0", "1", "2"], default="0")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0, help="Maximum PDFs to process; 0 means all")
    parser.add_argument("--only-missing-artifacts", action="store_true")
    parser.add_argument(
        "--write-failed-artifacts",
        action="store_true",
        help="Write artifact JSON even when no backend succeeds. By default failed-only artifacts are not written.",
    )
    parser.add_argument("--no-pdf-env-bootstrap", action="store_true", help="Do not re-run inside psychkg-pdf")
    args = parser.parse_args()

    if not args.no_pdf_env_bootstrap:
        ensure_pdf_runtime()

    cfg = DATASET_CONFIG[args.dataset]
    paper_library = Path(args.paper_library).resolve() if args.paper_library else cfg["paper_db_json"]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else cfg["out_dir"]
    report_path = Path(args.report).resolve() if args.report else cfg["report"]

    if args.backend == "grobid" and not grobid_is_available(args.grobid_url):
        print(f"GROBID service is not available: {grobid_alive_url(args.grobid_url)}", file=sys.stderr)
        return 2

    rows = load_json_array(paper_library)
    doi_filter = None
    filter_sources = []
    if args.doi_file:
        doi_filter = read_doi_file(Path(args.doi_file).resolve())
        filter_sources.append({"source": "doi_file", "path": str(Path(args.doi_file).resolve()), "doi_count": len(doi_filter)})
    if args.stale_fulltext_locators:
        stale_dois = stale_fulltext_locator_dois(load_json_array(curated_json))
        doi_filter = stale_dois if doi_filter is None else doi_filter & stale_dois
        filter_sources.append(
            {"source": "stale_fulltext_locators", "path": str(curated_json), "doi_count": len(stale_dois)}
        )

    all_candidates = list(
        iter_pdf_rows(
            rows,
            only_missing_artifacts=args.only_missing_artifacts,
            out_dir=out_dir,
            doi_filter=doi_filter,
        )
    )
    candidates = all_candidates
    if args.limit > 0:
        candidates = all_candidates[: args.limit]

    report_rows = []
    counts = {
        "paper_library_rows": len(rows),
        "pdf_rows_available": len(all_candidates),
        "pdf_rows_selected": len(candidates),
        "processed": 0,
        "with_success": 0,
        "without_success": 0,
    }

    for row, pdf_path, artifact_path in candidates:
        extractions = convert_pdf(
            pdf_path=pdf_path,
            backend=args.backend,
            grobid_url=args.grobid_url,
            timeout_sec=max(1, args.timeout_sec),
            grobid_retries=max(0, args.grobid_retries),
            grobid_retry_wait_sec=max(0, args.grobid_retry_wait_sec),
            grobid_consolidate_header=args.grobid_consolidate_header,
            grobid_consolidate_citations=args.grobid_consolidate_citations,
        )
        artifact = build_artifact(args.dataset, row, pdf_path, extractions)
        write_artifact, write_reason = should_write_artifact(
            artifact_path,
            artifact,
            write_failed_artifacts=args.write_failed_artifacts,
        )
        artifact["_write_status"] = write_reason
        if write_artifact:
            write_json(artifact_path, artifact)
        report_rows.append(report_row(row, artifact_path, artifact))
        counts["processed"] += 1
        if artifact.get("best_backend"):
            counts["with_success"] += 1
        else:
            counts["without_success"] += 1

    report = {
        "generated_at_utc": now_utc(),
        "dataset": args.dataset,
        "inputs": {
            "paper_library": str(paper_library),
            "curated_json": str(curated_json),
            "out_dir": str(out_dir),
            "backend": args.backend,
            "grobid_url": args.grobid_url,
            "grobid_retries": args.grobid_retries,
            "grobid_retry_wait_sec": args.grobid_retry_wait_sec,
            "grobid_consolidate_header": args.grobid_consolidate_header,
            "grobid_consolidate_citations": args.grobid_consolidate_citations,
            "filter_sources": filter_sources,
            "only_missing_artifacts": args.only_missing_artifacts,
            "limit": args.limit,
        },
        "counts": counts,
        "rows": report_rows,
    }
    write_json(report_path, report)

    print(f"Dataset: {args.dataset}")
    print(f"Processed PDFs: {counts['processed']}")
    print(f"Successful artifacts: {counts['with_success']}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
