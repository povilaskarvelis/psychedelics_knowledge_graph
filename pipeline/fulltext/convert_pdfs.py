#!/usr/bin/env python3
"""Shared conversion helpers for canonical routed PDF artifacts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from pipeline.fulltext.source_identity import (
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    augment_pdf_artifact_identity,
    evaluate_artifact_identity,
    identity_is_verified,
    load_pdf_hash_attestation_registry,
    split_dois,
)

DEFAULT_GROBID_URL = "http://localhost:8070/api/processFulltextDocument"
PDF_HASH_ATTESTATIONS = load_pdf_hash_attestation_registry(
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY
)["records"]

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


def pdf_filename_prefix_for_doi(raw: object) -> str:
    doi = normalize_doi(raw)
    slug = re.sub(r"[^a-z0-9._-]+", "_", doi.lower())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return (slug or "paper")[:90]


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
        return ["grobid"]
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
    artifact = {
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
    artifact["source_identity"] = augment_pdf_artifact_identity(
        evaluate_artifact_identity(
            artifact,
            requested_doi=row.get("study_doi", ""),
            requested_title=row.get("study_title", ""),
            related_dois=split_dois(
                row.get("related_dois", ""),
                row.get("publication_relations", ""),
                row.get("published_version_doi", ""),
            ),
        ),
        artifact,
        requested_title=row.get("study_title", ""),
        pdf_hash_attestations=PDF_HASH_ATTESTATIONS,
    )
    return artifact


def should_write_artifact(artifact_path: Path, artifact: dict, write_failed_artifacts: bool) -> tuple[bool, str]:
    if artifact.get("best_backend"):
        if identity_is_verified(artifact.get("source_identity", {})):
            return True, "successful extraction with verified source identity"
        return False, "successful extraction rejected because source identity was not verified"
    if write_failed_artifacts:
        return True, "failed artifacts explicitly enabled"

    existing = load_json_object(artifact_path)
    if existing.get("best_backend"):
        return False, "preserved existing successful artifact"
    if artifact_path.exists():
        return False, "left existing failed/unknown artifact unchanged"
    return False, "no successful extraction; artifact not written"
