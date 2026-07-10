"""Extract and evaluate the identity of full-text source artifacts.

The full-text store is keyed by the DOI that was requested.  That wrapper DOI
is not evidence that the downloaded XML or PDF belongs to the same paper, so
this module reads identifiers and titles from the document itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
LEGACY_SICI_DOI_RE = re.compile(r"10\.\d{4,9}/\(SICI\)[^\s\"']+", re.IGNORECASE)
VERIFIED_IDENTITY_STATUSES = {
    "verified_exact_doi",
    "verified_identity_override",
    "verified_related_doi",
    "verified_title_only",
    "verified_curated_pdf_hash",
}
FRONT_MATTER_CHAR_LIMIT = 12000
DEFAULT_PDF_HASH_ATTESTATION_REGISTRY = Path(__file__).with_name(
    "source_identity_pdf_hash_registry.json"
)
STOPWORDS = {
    "about",
    "after",
    "among",
    "and",
    "article",
    "based",
    "between",
    "effect",
    "effects",
    "for",
    "from",
    "into",
    "paper",
    "study",
    "that",
    "the",
    "their",
    "therapy",
    "this",
    "through",
    "using",
    "with",
}


def clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def strip_markup(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return clean(text)


def normalize_doi(value: object) -> str:
    text = html.unescape(str(value or "")).strip()
    text = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    legacy_match = LEGACY_SICI_DOI_RE.search(text)
    if legacy_match:
        # Legacy Wiley SICI identifiers legitimately contain ``<...>``.  A
        # conventional DOI regex truncates them at ``<`` and can merge distinct
        # papers. Stop only at an actual closing XML tag when parsing markup.
        doi = legacy_match.group(0).split("</", 1)[0]
        return doi.rstrip(".,;:)]}\"").lower()
    match = DOI_RE.search(text)
    if not match:
        return ""
    doi = match.group(0)
    # Broken metadata occasionally concatenates two identifiers without a
    # separator (``10.x/a:10.y/b``).  The second DOI is never part of the first.
    second = re.search(r"10\.\d{4,9}/", doi[3:], flags=re.IGNORECASE)
    if second:
        doi = doi[: second.start() + 3]
    # Some GROBID headers concatenate a following bibliographic identifier,
    # e.g. ``10.x/articlepmid:123``.  The PMID marker is not part of the DOI.
    doi = re.split(r"(?:pmid|pmcid)\s*:", doi, maxsplit=1, flags=re.IGNORECASE)[0]
    return doi.rstrip(".,;:)]}\"").lower()


def normalize_pmcid(value: object) -> str:
    match = re.search(r"(?:PMC)?\s*(\d+)", clean(value), flags=re.IGNORECASE)
    return f"PMC{match.group(1)}" if match else ""


def doi_equivalent(left: object, right: object) -> bool:
    a, b = normalize_doi(left), normalize_doi(right)
    if not a or not b:
        return False
    if a == b:
        return True
    compact_a = re.sub(r"[^a-z0-9]", "", a)
    compact_b = re.sub(r"[^a-z0-9]", "", b)
    return compact_a == compact_b


def split_dois(*values: object) -> set[str]:
    out: set[str] = set()
    for value in values:
        legacy_dois: set[str] = set()
        for match in LEGACY_SICI_DOI_RE.findall(str(value or "")):
            doi = normalize_doi(match)
            if doi:
                legacy_dois.add(doi)
                out.add(doi)
        for match in DOI_RE.findall(str(value or "")):
            doi = normalize_doi(match)
            if doi and not any(legacy.startswith(doi) and legacy != doi for legacy in legacy_dois):
                out.add(doi)
    return out


def title_tokens(value: object) -> list[str]:
    words = re.findall(r"[a-z0-9]+", strip_markup(value).casefold())
    return [word for word in words if len(word) > 2 and word not in STOPWORDS]


def title_similarity(left: object, right: object) -> float | None:
    a, b = strip_markup(left), strip_markup(right)
    if not a or not b:
        return None
    sequence = SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
    aset, bset = set(title_tokens(a)), set(title_tokens(b))
    jaccard = len(aset & bset) / len(aset | bset) if aset and bset else 0.0
    containment = min(
        len(aset & bset) / len(aset) if aset else 0.0,
        len(aset & bset) / len(bset) if bset else 0.0,
    )
    return round(max(sequence, jaccard, containment), 4)


def title_coverage(title: object, text: object) -> float:
    wanted = set(title_tokens(title))
    if not wanted:
        return 0.0
    present = set(title_tokens(str(text or "")[:30000]))
    return round(len(wanted & present) / len(wanted), 4)


def title_phrase_match(title: object, text: object, *, max_chars: int = 30000) -> bool:
    wanted = " ".join(title_tokens(title))
    if len(wanted.split()) < 4:
        return False
    prefix = " ".join(title_tokens(str(text or "")[:max_chars]))
    return wanted in prefix


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean(" ".join(part for part in element.itertext() if clean(part)))


def children_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def descendants_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if local_name(child.tag) == name]


def first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element.iter() if local_name(child.tag) == name), None)


def _jats_article_meta(article: ET.Element) -> ET.Element | None:
    front = next((child for child in list(article) if local_name(child.tag) in {"front", "front-stub"}), None)
    if front is None:
        return None
    if local_name(front.tag) == "front-stub":
        return front
    return first_descendant(front, "article-meta")


def jats_article_identities(xml_text: str) -> list[dict[str, Any]]:
    """Return identities for top-level JATS articles and sub-articles."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    articles = [node for node in root.iter() if local_name(node.tag) in {"article", "sub-article"}]
    if local_name(root.tag) in {"article", "sub-article"} and root not in articles:
        articles.insert(0, root)
    identities: list[dict[str, Any]] = []
    for index, article in enumerate(articles):
        meta = _jats_article_meta(article)
        if meta is None:
            continue
        ids: dict[str, str] = {}
        for node in children_named(meta, "article-id"):
            kind = clean(node.attrib.get("pub-id-type", "")).casefold()
            value = element_text(node)
            if kind and value and kind not in ids:
                ids[kind] = value
        title_group = first_descendant(meta, "title-group")
        title_node = first_descendant(title_group, "article-title") if title_group is not None else first_descendant(meta, "article-title")
        identities.append(
            {
                "format": "jats_xml",
                "article_index": index,
                "doi": normalize_doi(ids.get("doi", "")),
                "pmid": clean(ids.get("pmid", "")),
                "pmcid": normalize_pmcid(ids.get("pmcid", "") or ids.get("pmc", "")),
                "title": element_text(title_node),
                "node": article,
            }
        )
    return identities


def select_jats_article(xml_text: str, requested_doi: object) -> tuple[str, dict[str, Any]]:
    """Select the JATS article/sub-article that owns ``requested_doi``.

    The original XML is retained for a single exact article.  For collection
    XML, the matching article node is serialized so adjacent abstracts cannot
    leak into the artifact.
    """
    requested = normalize_doi(requested_doi)
    identities = jats_article_identities(xml_text)
    matches = [row for row in identities if doi_equivalent(row.get("doi"), requested)]
    if len(matches) != 1:
        found = ", ".join(sorted({row.get("doi", "") for row in identities if row.get("doi")}))
        raise ValueError(f"JATS identity mismatch: requested={requested or '<missing>'} found={found or '<missing>'}")
    match = matches[0]
    if len(identities) == 1:
        return xml_text, {key: value for key, value in match.items() if key != "node"}
    selected = ET.tostring(match["node"], encoding="unicode")
    return selected, {key: value for key, value in match.items() if key != "node"}


def tei_header_identity(xml_text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}
    header = first_descendant(root, "teiHeader")
    if header is None:
        return {}

    title = ""
    title_stmt = first_descendant(header, "titleStmt")
    if title_stmt is not None:
        for node in descendants_named(title_stmt, "title"):
            candidate = element_text(node)
            if candidate:
                title = candidate
                break

    doi = pmid = pmcid = ""
    source_desc = first_descendant(header, "sourceDesc")
    if source_desc is not None:
        for node in descendants_named(source_desc, "idno"):
            kind = clean(node.attrib.get("type", "")).casefold()
            value = element_text(node)
            if kind == "doi" and not doi:
                doi = normalize_doi(value)
            elif kind in {"pmid", "pubmed"} and not pmid:
                pmid = value
            elif kind in {"pmcid", "pmc"} and not pmcid:
                pmcid = normalize_pmcid(value)
    return {"format": "tei_xml", "doi": doi, "pmid": pmid, "pmcid": pmcid, "title": title}


def text_front_identity(text: str, format_name: str) -> dict[str, str]:
    prefix = str(text or "")[:30000]
    doi = normalize_doi(prefix)
    title = ""
    if format_name == "markdown":
        for line in prefix.splitlines():
            candidate = re.sub(r"^#{1,6}\s+", "", line).strip()
            if line.lstrip().startswith("#") and len(title_tokens(candidate)) >= 3:
                title = candidate
                break
    return {"format": format_name or "plain_text", "doi": doi, "pmid": "", "pmcid": "", "title": title}


def extraction_identity(extraction: dict) -> dict[str, str]:
    text = str(extraction.get("text") or "")
    metadata = extraction.get("metadata") if isinstance(extraction.get("metadata"), dict) else {}
    format_name = clean(metadata.get("format", "")).casefold()
    if format_name == "jats_xml" or "<article" in text[:5000]:
        identities = jats_article_identities(text)
        if identities:
            row = identities[0]
            return {key: clean(row.get(key, "")) for key in ("format", "doi", "pmid", "pmcid", "title")}
    if format_name == "tei_xml" or "<tei" in text[:5000].casefold():
        identity = tei_header_identity(text)
        if identity:
            return identity
    if format_name in {"markdown", "plain_text"}:
        return text_front_identity(text, format_name)
    return text_front_identity(text, format_name or "unknown")


def successful_extractions(artifact: dict) -> list[dict]:
    return [
        row
        for row in artifact.get("extractions", []) or []
        if isinstance(row, dict) and clean(row.get("status", "")).casefold() == "ok"
    ]


def identity_is_verified(value: object) -> bool:
    if isinstance(value, dict):
        status = clean(value.get("status", ""))
    else:
        status = clean(value)
    return status in VERIFIED_IDENTITY_STATUSES


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def pdf_bytes_match_hash_attestation(
    requested_doi: object,
    value: bytes,
    records: dict[str, dict] | None,
) -> bool:
    """Return true only for the registered DOI and byte-identical PDF."""
    doi = normalize_doi(requested_doi)
    record = (records or {}).get(doi)
    if not record or not value:
        return False
    return bytes_sha256(value).casefold() == clean(record.get("pdf_sha256", "")).casefold()


def load_pdf_hash_attestation_registry(path: Path = DEFAULT_PDF_HASH_ATTESTATION_REGISTRY) -> dict:
    """Load explicit, hash-bound curator decisions for exceptional PDFs.

    This is deliberately narrower than a DOI alias.  It permits one reviewed
    byte-identical PDF whose identity cannot be established automatically (for
    example, when the metadata title is an English translation but the PDF's
    first-page title is in another script).
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError(f"Unsupported PDF hash-attestation registry: {path}")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("PDF hash-attestation registry records must be a list")
    if int(payload.get("record_count", len(raw_records))) != len(raw_records):
        raise ValueError("PDF hash-attestation registry record_count does not match records")
    records: dict[str, dict] = {}
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise ValueError(f"PDF hash-attestation record {index} must be an object")
        doi = normalize_doi(raw.get("requested_doi", ""))
        sha256 = clean(raw.get("pdf_sha256", "")).casefold()
        if not doi or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError(f"PDF hash-attestation record {index} has invalid DOI or SHA-256")
        if doi in records:
            raise ValueError(f"Duplicate PDF hash attestation for {doi}")
        if clean(raw.get("document_kind", "")) != "single_article_pdf":
            raise ValueError(f"PDF hash attestation for {doi} must assert single_article_pdf")
        if not clean(raw.get("review_basis", "")) or not clean(raw.get("reviewed_at", "")):
            raise ValueError(f"PDF hash attestation for {doi} lacks review provenance")
        records[doi] = {**raw, "requested_doi": doi, "pdf_sha256": sha256}
    return {
        "path": str(path.resolve()),
        "version": 1,
        "records": records,
    }


def apply_pdf_front_title_validation(
    identity: dict,
    artifact: dict,
    *,
    requested_title: object,
    minimum_title_score: float = 0.86,
) -> dict:
    """Recheck an unverified artifact against the top of PDF page one."""
    result = dict(identity)
    result["pdf_front_title_validation_applied"] = False
    if bool(identity.get("verified")):
        return result
    pdf_raw = clean(artifact.get("pdf_local_path", ""))
    pdf_path = Path(pdf_raw).expanduser() if pdf_raw else None
    if pdf_path is None or not pdf_path.exists() or not pdf_path.is_file():
        return result
    try:
        # Local import avoids coupling the XML identity parser to PDF runtime
        # dependencies until a PDF fallback is actually needed.
        from pipeline.fulltext.pdf_alternate_sources import title_validation_result

        accepted, score, reason = title_validation_result(
            clean(requested_title),
            pdf_path.read_bytes(),
            minimum_title_score,
        )
    except Exception as err:
        result["pdf_front_title_validation_error"] = f"{type(err).__name__}: {err}"
        return result
    result["pdf_front_title_validation"] = {
        "accepted": bool(accepted),
        "reason": clean(reason),
        "title_score": round(float(score or 0), 4),
        "minimum_title_score": float(minimum_title_score),
    }
    if not accepted:
        return result
    result.update(
        {
            "status": "verified_title_only",
            "verified": True,
            "basis": "requested title matches the bounded top region of PDF page one",
            "pdf_front_title_validation_applied": True,
        }
    )
    return result


def apply_pdf_hash_attestation(identity: dict, artifact: dict, record: dict | None) -> dict:
    """Apply an exceptional curator decision only to its exact reviewed PDF."""
    result = dict(identity)
    result.update(
        {
            "pdf_hash_attestation_present": bool(record),
            "pdf_hash_attestation_applied": False,
            "pdf_hash_attestation_disposition": "not_listed",
        }
    )
    if not record:
        return result
    if bool(identity.get("verified")):
        result["pdf_hash_attestation_disposition"] = "not_needed_identity_already_verified"
        return result
    requested = normalize_doi(artifact.get("study_doi", ""))
    if requested != normalize_doi(record.get("requested_doi", "")):
        result["pdf_hash_attestation_disposition"] = "requested_doi_mismatch"
        return result
    pdf_raw = clean(artifact.get("pdf_local_path", ""))
    pdf_path = Path(pdf_raw).expanduser() if pdf_raw else None
    if pdf_path is None or not pdf_path.exists() or not pdf_path.is_file():
        result["pdf_hash_attestation_disposition"] = "pdf_missing"
        return result
    actual_hash = file_sha256(pdf_path).casefold()
    expected_hash = clean(record.get("pdf_sha256", "")).casefold()
    artifact_hash = clean(artifact.get("pdf_sha256", "")).casefold()
    if actual_hash != expected_hash or (artifact_hash and artifact_hash != actual_hash):
        result["pdf_hash_attestation_disposition"] = "pdf_hash_mismatch"
        return result
    result.update(
        {
            "status": "verified_curated_pdf_hash",
            "verified": True,
            "basis": "curator-reviewed single-article PDF matches the registered SHA-256",
            "pdf_hash_attestation_applied": True,
            "pdf_hash_attestation_disposition": "applied_exact_hash",
            "pdf_hash_attestation_review_basis": clean(record.get("review_basis", "")),
            "pdf_hash_attestation_reviewed_at": clean(record.get("reviewed_at", "")),
            "pdf_hash_attestation_source_url": clean(record.get("source_url", "")),
        }
    )
    return result


def augment_pdf_artifact_identity(
    identity: dict,
    artifact: dict,
    *,
    requested_title: object,
    pdf_hash_attestations: dict[str, dict] | None = None,
    minimum_title_score: float = 0.86,
) -> dict:
    """Apply automatic front-title evidence, then an exact-hash exception."""
    requested = normalize_doi(artifact.get("study_doi", ""))
    front_checked = apply_pdf_front_title_validation(
        identity,
        artifact,
        requested_title=requested_title,
        minimum_title_score=minimum_title_score,
    )
    return apply_pdf_hash_attestation(
        front_checked,
        artifact,
        (pdf_hash_attestations or {}).get(requested),
    )


def evaluate_artifact_identity(
    artifact: dict,
    *,
    requested_doi: object | None = None,
    requested_title: object | None = None,
    related_dois: Iterable[object] = (),
) -> dict[str, Any]:
    requested = normalize_doi(requested_doi or artifact.get("study_doi", ""))
    title = clean(requested_title or artifact.get("study_title", ""))
    aliases = {normalize_doi(value) for value in related_dois if normalize_doi(value)}
    aliases.discard(requested)

    evidence: list[dict[str, Any]] = []
    for extraction in successful_extractions(artifact):
        identity = extraction_identity(extraction)
        text = str(extraction.get("text") or "")
        document_doi = normalize_doi(identity.get("doi", ""))
        similarity = title_similarity(title, identity.get("title", ""))
        coverage = title_coverage(title, text)
        evidence.append(
            {
                "backend": clean(extraction.get("backend", "")),
                "format": clean(identity.get("format", "")),
                "document_doi": document_doi,
                "document_title": clean(identity.get("title", "")),
                "document_pmid": clean(identity.get("pmid", "")),
                "document_pmcid": normalize_pmcid(identity.get("pmcid", "")),
                "title_similarity": similarity,
                "title_coverage": coverage,
                "title_phrase_match": title_phrase_match(title, text),
                "front_title_phrase_match": title_phrase_match(
                    title,
                    text,
                    max_chars=FRONT_MATTER_CHAR_LIMIT,
                ),
            }
        )

    def result(status: str, basis: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
        selected = row or (evidence[0] if evidence else {})
        return {
            "status": status,
            "verified": status in VERIFIED_IDENTITY_STATUSES,
            "basis": basis,
            "requested_doi": requested,
            "requested_title": title,
            "document_doi": clean(selected.get("document_doi", "")),
            "document_title": clean(selected.get("document_title", "")),
            "document_pmid": clean(selected.get("document_pmid", "")),
            "document_pmcid": clean(selected.get("document_pmcid", "")),
            "title_similarity": selected.get("title_similarity"),
            "title_coverage": selected.get("title_coverage"),
            "title_phrase_match": bool(selected.get("title_phrase_match", False)),
            "front_title_phrase_match": bool(selected.get("front_title_phrase_match", False)),
            "backend": clean(selected.get("backend", artifact.get("best_backend", ""))),
            "format": clean(selected.get("format", "")),
            "related_dois_considered": sorted(aliases),
            "evidence": evidence,
        }

    for row in evidence:
        # A target title appearing later in the document is not identity
        # evidence: it may be a cited paper or a neighbouring contribution in
        # a proceedings/container PDF.  Verification must come from the
        # parsed document header or the bounded front-matter region.
        strong_front_title = bool(row.get("front_title_phrase_match")) or (row.get("title_similarity") or 0) >= 0.85
        structured_header = row.get("format") in {"jats_xml", "tei_xml"}
        if requested and doi_equivalent(row.get("document_doi"), requested) and (structured_header or strong_front_title):
            return result("verified_exact_doi", "document identifier matches requested DOI", row)
    for row in evidence:
        if row.get("document_doi") in aliases and (
            bool(row.get("front_title_phrase_match")) or (row.get("title_similarity") or 0) >= 0.75
        ):
            return result("verified_related_doi", "document DOI is an explicit related/version DOI and title agrees", row)

    conflicting = [row for row in evidence if row.get("document_doi") and requested and not doi_equivalent(row.get("document_doi"), requested)]
    if conflicting:
        best = max(conflicting, key=lambda row: (bool(row.get("title_phrase_match")), row.get("title_similarity") or 0))
        if bool(best.get("title_phrase_match")) or (best.get("title_similarity") or 0) >= 0.75:
            return result(
                "target_text_with_conflicting_doi",
                "requested title is present but the document identifier differs; version or container must be resolved",
                best,
            )
        return result("identity_mismatch", "document DOI differs and title evidence does not support the requested paper", best)

    titled = [
        row
        for row in evidence
        if bool(row.get("front_title_phrase_match")) or (row.get("title_similarity") or 0) >= 0.88
    ]
    if titled:
        best = max(titled, key=lambda row: (bool(row.get("title_phrase_match")), row.get("title_similarity") or 0))
        return result("verified_title_only", "no document DOI recovered; strong title agreement", best)
    if evidence:
        best = max(evidence, key=lambda row: (bool(row.get("title_phrase_match")), row.get("title_similarity") or 0))
        return result("identity_unverified", "insufficient document-level identifier or title evidence", best)
    return result("identity_unverified", "artifact has no successful extraction identity evidence")
