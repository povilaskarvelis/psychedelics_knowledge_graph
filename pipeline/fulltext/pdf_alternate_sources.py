"""Alternate open-access PDF source discovery for routed PDF downloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import html as html_lib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterable
from urllib.parse import quote, urljoin, urlparse

from pipeline.ingest.metadata_utils import (
    RateLimitedHttpClient,
    file_is_valid_pdf,
    join_candidates,
    looks_like_pdf_bytes,
    normalize_doi,
)
from pipeline.fulltext.source_identity import (
    load_pdf_hash_attestation_registry,
    pdf_bytes_match_hash_attestation,
)


PMC_IDCONV_API = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
OPENALEX_WORK_API = "https://api.openalex.org/works/doi:"
SEMANTIC_SCHOLAR_PAPER_API = "https://api.semanticscholar.org/graph/v1/paper/"

PUBLISHER_HOST_HINTS = (
    "academic.oup.com",
    "akjournals.com",
    "aspetjournals.org",
    "biologicalpsychiatryjournal.com",
    "bmj.com",
    "cambridge.org",
    "cell.com",
    "elsevier.com",
    "frontiersin.org",
    "jneurosci.org",
    "journals.sagepub.com",
    "jpsmjournal.com",
    "lww.com",
    "mdpi.com",
    "nature.com",
    "onlinelibrary.wiley.com",
    "pnas.org",
    "portlandpress.com",
    "psychiatryonline.org",
    "pubs.asahq.org",
    "sciencedirect.com",
    "springer.com",
    "tandfonline.com",
    "wolterskluwer.com",
)

REPOSITORY_NAME_HINTS = (
    "archive",
    "deep blue",
    "dspace",
    "edoc",
    "escholarship",
    "figshare",
    "institutional",
    "open access",
    "osf",
    "pure",
    "repository",
    "surrey",
    "zenodo",
    "zora",
)

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
    "review",
    "study",
    "that",
    "their",
    "therapy",
    "through",
    "using",
    "with",
}

PDF_TITLE_FRONT_CHAR_LIMIT = 2000
PDF_HASH_ATTESTATIONS = load_pdf_hash_attestation_registry()["records"]

NON_PRIMARY_PDF_HEADINGS = {
    "supplementary material",
    "supplemental material",
    "supplementary information",
    "supplemental information",
    "supporting information",
}


@dataclass(frozen=True)
class AlternatePdfCandidate:
    url: str
    source: str
    reason: str = ""
    landing_url: str = ""
    host_type: str = ""
    version: str = ""

    def to_record(self) -> dict:
        return asdict(self)


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def doi_key(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def add_candidate(candidates: list[AlternatePdfCandidate], candidate: AlternatePdfCandidate) -> None:
    if not candidate.url:
        return
    if any(existing.url == candidate.url for existing in candidates):
        return
    candidates.append(candidate)


def host_for(url: str) -> str:
    return urlparse(clean(url)).netloc.lower().removeprefix("www.")


def is_publisher_url(url: str) -> bool:
    host = host_for(url)
    return any(hint in host for hint in PUBLISHER_HOST_HINTS)


def normalize_for_title_match(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", clean(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> list[str]:
    return [
        token
        for token in normalize_for_title_match(title).split()
        if len(token) > 3 and token not in STOPWORDS and not token.isdigit()
    ]


def title_match_score(title: str, text: str) -> float:
    title_norm = normalize_for_title_match(title)
    text_norm = normalize_for_title_match(text)
    if not title_norm or not text_norm:
        return 0.0
    if title_norm in text_norm:
        return 1.0
    tokens = title_tokens(title)
    if len(tokens) < 4:
        return 0.0
    return sum(1 for token in tokens if token in text_norm) / len(tokens)


def extract_pdf_text_from_bytes(body: bytes, max_pages: int = 3) -> str:
    tmp_path = Path("")
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(body)
            tmp_path = Path(handle.name)
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", str(max(1, max_pages)), str(tmp_path), "-"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


def non_primary_pdf_artifact_basis(text: str) -> str:
    """Identify high-confidence ancillary files that are not the requested article.

    Ancillary PDFs commonly repeat the article title, so title similarity alone
    cannot distinguish them from the primary paper. Keep this deliberately
    narrow: only explicit headings and boilerplate near the start of page one
    are rejected.
    """
    first_page = text.split("\f", 1)[0]
    lines = [clean(line).lower() for line in first_page.splitlines() if clean(line)]
    for line in lines[:8]:
        if line in NON_PRIMARY_PDF_HEADINGS:
            return "supplementary_pdf_artifact"
        if any(line.startswith(f"{heading} for ") for heading in NON_PRIMARY_PDF_HEADINGS):
            return "supplementary_pdf_artifact"
    front = normalize_for_title_match(first_page)[:1200]
    if (
        "this supplementary material has been provided by the author" in front
        or "list of supplementary material for the article" in front
    ):
        return "supplementary_pdf_artifact"
    return ""


def title_validation_result(
    title: str,
    body: bytes,
    min_title_score: float,
    *,
    study_doi: str = "",
    pdf_hash_attestations: dict[str, dict] | None = None,
) -> tuple[bool, float, str]:
    if pdf_bytes_match_hash_attestation(
        study_doi,
        body,
        PDF_HASH_ATTESTATIONS if pdf_hash_attestations is None else pdf_hash_attestations,
    ):
        return True, 1.0, "curated_pdf_hash"
    if not clean(title):
        return False, 0.0, "missing_expected_title"
    if min_title_score <= 0:
        return False, 0.0, "invalid_min_title_score"
    text = extract_pdf_text_from_bytes(body)
    if not text.strip():
        # A PDF-shaped response is not source-identity evidence. Scans or
        # otherwise unreadable PDFs go to manual review instead of entering the
        # canonical store without a title check.
        return False, 0.0, "no_text_extracted"
    artifact_basis = non_primary_pdf_artifact_basis(text)
    if artifact_basis:
        return False, 0.0, artifact_basis
    # Conference books and supplements can contain many valid paper titles.
    # A match anywhere in the first few pages therefore does not identify the
    # PDF as the requested article. Require the title in the top region of page
    # one; later matches must be segmented or reviewed manually.
    first_page = text.split("\f", 1)[0]
    front_text = normalize_for_title_match(first_page)[:PDF_TITLE_FRONT_CHAR_LIMIT]
    score = title_match_score(title, front_text)
    return score >= min_title_score, score, "front_title_match"


def js_const_value(html: str, name: str) -> str:
    pattern = rf"\b{name}\s*=\s*[\"']([^\"']+)[\"']"
    match = re.search(pattern, html)
    return match.group(1) if match else ""


def solve_pmc_pow_cookie(html: str) -> str:
    """Return a cloudpmc proof-of-work cookie header value for PMC viewer pages."""

    challenge = js_const_value(html, "POW_CHALLENGE")
    difficulty_text = js_const_value(html, "POW_DIFFICULTY")
    cookie_name = js_const_value(html, "POW_COOKIE_NAME") or "cloudpmc-viewer-pow"
    if not challenge:
        return ""
    try:
        difficulty = int(difficulty_text or "4")
    except ValueError:
        difficulty = 4
    prefix = "0" * max(0, difficulty)
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{challenge}{nonce}".encode("utf-8")).hexdigest()
        if digest.startswith(prefix):
            return f"{cookie_name}={challenge},{nonce}"
        nonce += 1


def extract_pmcids_from_values(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = clean(value)
        for match in re.finditer(r"\bPMC\d+\b", text, flags=re.IGNORECASE):
            pmcid = match.group(0).upper()
            if pmcid not in out:
                out.append(pmcid)
        for match in re.finditer(r"/pmc/articles/(\d+)", text, flags=re.IGNORECASE):
            pmcid = f"PMC{match.group(1)}"
            if pmcid not in out:
                out.append(pmcid)
    return out


def pmcids_from_id_converter(client: RateLimitedHttpClient, doi: str) -> tuple[list[str], list[dict]]:
    events: list[dict] = []
    doi = doi_key(doi)
    if not doi:
        return [], events
    try:
        payload = client.get_json(
            PMC_IDCONV_API,
            params={
                "format": "json",
                "idtype": "doi",
                "tool": "kg_pdf_alternate_sources",
                "ids": doi,
            },
            headers={"Accept": "application/json,*/*;q=0.1"},
        )
    except Exception as err:
        return [], [{"event": "pmc_idconv_error", "doi": doi, "error": f"{type(err).__name__}: {err}"}]
    pmcids: list[str] = []
    for record in payload.get("records", []) if isinstance(payload, dict) else []:
        pmcid = clean(record.get("pmcid", "")).upper()
        if pmcid and pmcid not in pmcids:
            pmcids.append(pmcid)
    events.append({"event": "pmc_idconv_response", "doi": doi, "pmcid_count": len(pmcids)})
    return pmcids, events


def extract_pdf_links(page_url: str, html: str) -> list[str]:
    links: list[str] = []
    patterns = (
        r"""<meta[^>]+name=["']citation_pdf_url["'][^>]+content=["']([^"']+)["']""",
        r"""<meta[^>]+content=["']([^"']+)["'][^>]+name=["']citation_pdf_url["']""",
        r"""href\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        r"""href\s*=\s*["']([^"']*view/pdfCoverPage\?[^"']*download=true[^"']*)["']""",
        r"""href\s*=\s*["']([^"']*/server/api/core/bitstreams/[0-9a-f-]+/content[^"']*)["']""",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.IGNORECASE):
            url = urljoin(page_url, html_lib.unescape(match.group(1)))
            if url and url not in links:
                links.append(url)
    for url in dspace_original_bitstream_content_urls(page_url, html):
        if url not in links:
            links.append(url)
    return links


def public_dspace_api_url(url: str) -> str:
    parsed = urlparse(clean(url))
    path = parsed.path
    query = f"?{parsed.query}" if parsed.query else ""
    if parsed.scheme == "https" and parsed.netloc and path.startswith("/server/api/"):
        return f"{parsed.scheme}://{parsed.netloc}{path}{query}"
    if "server/api/" in path:
        root = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else ""
        return f"{root}{path[path.index('/server/api/') :]}{query}"
    return clean(url)


def dspace_item_uuid(page_url: str, html: str) -> str:
    for value in (page_url, html[:500_000]):
        match = re.search(r"/entities/publication/([0-9a-f-]{36})", value, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def dspace_original_bitstream_content_urls(page_url: str, html: str) -> list[str]:
    urls: list[str] = []
    # DSpace Angular apps commonly store the public API URL in embedded state.
    for match in re.finditer(
        r"https?://[^\"'<>\\\s]+/server/api/core/bitstreams/[0-9a-f-]+/content",
        html,
        flags=re.IGNORECASE,
    ):
        url = public_dspace_api_url(html_lib.unescape(match.group(0)))
        if url not in urls:
            urls.append(url)
    item_uuid = dspace_item_uuid(page_url, html)
    if item_uuid:
        parsed = urlparse(page_url)
        if parsed.netloc:
            api = (
                f"{parsed.scheme or 'https'}://{parsed.netloc}"
                f"/server/api/core/bitstreams/search/showableByItem?uuid={item_uuid}"
                "&name=ORIGINAL&embed=thumbnail&embed=format&page=0&size=10"
            )
            if api not in urls:
                urls.insert(0, api)
    return urls


def dspace_original_content_links_from_json(api_url: str, payload: dict) -> list[str]:
    api_parsed = urlparse(api_url)
    bitstreams = payload.get("_embedded", {}).get("bitstreams", []) if isinstance(payload, dict) else []
    out: list[str] = []
    for bitstream in bitstreams:
        if not isinstance(bitstream, dict):
            continue
        content_url = clean((bitstream.get("_links") or {}).get("content", {}).get("href", ""))
        if not content_url and clean(bitstream.get("uuid", "")):
            parsed = urlparse(api_url)
            content_url = f"{parsed.scheme}://{parsed.netloc}/server/api/core/bitstreams/{clean(bitstream.get('uuid'))}/content"
        content_url = public_dspace_api_url(content_url)
        parsed_content = urlparse(content_url)
        if api_parsed.netloc and (parsed_content.port == 8080 or (parsed_content.hostname or "").startswith("dd-")):
            content_url = f"{api_parsed.scheme}://{api_parsed.netloc}{parsed_content.path}"
        if content_url and content_url not in out:
            out.append(content_url)
    return out


def pmc_article_pdf_candidates(
    client: RateLimitedHttpClient,
    pmcid: str,
) -> tuple[list[AlternatePdfCandidate], list[dict]]:
    pmcid = clean(pmcid).upper()
    if pmcid.isdigit():
        pmcid = f"PMC{pmcid}"
    if not pmcid.startswith("PMC"):
        return [], []
    article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    try:
        body = client.get_bytes(article_url, headers={"Accept": "text/html,*/*;q=0.1"})
    except Exception as err:
        return [], [{"event": "pmc_article_error", "pmcid": pmcid, "error": f"{type(err).__name__}: {err}"}]
    html = body.decode("utf-8", errors="replace")
    candidates: list[AlternatePdfCandidate] = []
    for url in extract_pdf_links(article_url, html):
        add_candidate(
            candidates,
            AlternatePdfCandidate(
                url=url,
                source="pmc",
                reason="pmc_article_pdf_link",
                landing_url=article_url,
                host_type="repository",
            ),
        )
    return candidates, [{"event": "pmc_article_response", "pmcid": pmcid, "pdf_candidate_count": len(candidates)}]


def openalex_repository_candidates(
    client: RateLimitedHttpClient,
    doi: str,
) -> tuple[list[AlternatePdfCandidate], list[dict]]:
    doi = doi_key(doi)
    if not doi:
        return [], []
    url = f"{OPENALEX_WORK_API}{quote(doi, safe='')}"
    try:
        payload = client.get_json(url, headers={"Accept": "application/json,*/*;q=0.1"})
    except Exception as err:
        return [], [{"event": "openalex_error", "doi": doi, "error": f"{type(err).__name__}: {err}"}]

    candidates: list[AlternatePdfCandidate] = []
    locations: list[dict] = []
    best = payload.get("best_oa_location") if isinstance(payload, dict) else None
    if isinstance(best, dict):
        locations.append(best)
    for location in payload.get("locations", []) if isinstance(payload, dict) else []:
        if isinstance(location, dict):
            locations.append(location)

    oa_url = clean((payload.get("open_access") or {}).get("oa_url", "")) if isinstance(payload, dict) else ""
    if oa_url and not is_publisher_url(oa_url) and "biorxiv" not in oa_url.lower():
        add_candidate(candidates, AlternatePdfCandidate(url=oa_url, source="openalex", reason="openalex_oa_url"))

    for location in locations:
        source = location.get("source") or {}
        source_type = clean(source.get("type", "")).lower()
        source_name = clean(source.get("display_name", "")).lower()
        repositoryish = source_type == "repository" or any(hint in source_name for hint in REPOSITORY_NAME_HINTS)
        for field in ("pdf_url", "landing_page_url"):
            candidate_url = clean(location.get(field, ""))
            if not candidate_url or "biorxiv" in candidate_url.lower() or is_publisher_url(candidate_url):
                continue
            if not repositoryish and field != "pdf_url":
                continue
            add_candidate(
                candidates,
                AlternatePdfCandidate(
                    url=candidate_url,
                    source="openalex",
                    reason=f"openalex_{field}",
                    host_type=source_type,
                    version=clean(location.get("version", "")),
                ),
            )
    return candidates, [{"event": "openalex_response", "doi": doi, "pdf_candidate_count": len(candidates)}]


def semantic_scholar_candidates(
    client: RateLimitedHttpClient,
    doi: str,
) -> tuple[list[AlternatePdfCandidate], list[dict]]:
    doi = doi_key(doi)
    if not doi:
        return [], []
    paper_id = quote(f"DOI:{doi}", safe="")
    url = f"{SEMANTIC_SCHOLAR_PAPER_API}{paper_id}"
    params = "fields=title,year,isOpenAccess,openAccessPdf,externalIds,url"
    headers = {"Accept": "application/json,*/*;q=0.1"}
    api_key = os.environ.get("S2_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    try:
        payload = client.get_json(f"{url}?{params}", headers=headers)
    except Exception as err:
        return [], [{"event": "semantic_scholar_error", "doi": doi, "error": f"{type(err).__name__}: {err}"}]
    pdf = payload.get("openAccessPdf") if isinstance(payload, dict) else None
    pdf_url = clean(pdf.get("url", "")) if isinstance(pdf, dict) else ""
    if not pdf_url or "biorxiv" in pdf_url.lower():
        return [], [{"event": "semantic_scholar_response", "doi": doi, "pdf_candidate_count": 0}]
    return [
        AlternatePdfCandidate(
            url=pdf_url,
            source="semantic_scholar",
            reason="semantic_scholar_open_access_pdf",
            version=clean(pdf.get("status", "")) if isinstance(pdf, dict) else "",
        )
    ], [{"event": "semantic_scholar_response", "doi": doi, "pdf_candidate_count": 1}]


def collect_alternate_pdf_candidates(
    *,
    client: RateLimitedHttpClient,
    task: dict,
    sources: set[str],
) -> dict:
    doi = doi_key(task.get("doi", ""))
    sources = {clean(source).lower() for source in sources if clean(source)}
    candidates: list[AlternatePdfCandidate] = []
    events: list[dict] = []

    if "pmc" in sources:
        pmcids = extract_pmcids_from_values(
            [
                task.get("pmcid", ""),
                task.get("pmid", ""),
                task.get("best_pdf_url", ""),
                task.get("pdf_url_candidates", ""),
                task.get("probable_pdf_url_candidates", ""),
                task.get("other_url_candidates", ""),
            ]
        )
        converted, conversion_events = pmcids_from_id_converter(client, doi)
        events.extend(conversion_events)
        for pmcid in converted:
            if pmcid not in pmcids:
                pmcids.append(pmcid)
        for pmcid in pmcids:
            pmc_candidates, pmc_events = pmc_article_pdf_candidates(client, pmcid)
            events.extend(pmc_events)
            for candidate in pmc_candidates:
                add_candidate(candidates, candidate)

    if "openalex" in sources:
        openalex, openalex_events = openalex_repository_candidates(client, doi)
        events.extend(openalex_events)
        for candidate in openalex:
            add_candidate(candidates, candidate)

    if "semantic_scholar" in sources:
        semantic, semantic_events = semantic_scholar_candidates(client, doi)
        events.extend(semantic_events)
        for candidate in semantic:
            add_candidate(candidates, candidate)

    return {
        "candidates": candidates,
        "candidate_urls": join_candidates(candidate.url for candidate in candidates),
        "events": events,
    }


def fetch_pdf_bytes_for_candidate(
    *,
    client: RateLimitedHttpClient,
    candidate: AlternatePdfCandidate,
    allow_landing_resolution: bool = True,
) -> tuple[bytes, list[dict], str]:
    events: list[dict] = []

    def request(url: str, headers: dict[str, str]) -> bytes:
        body = client.get_bytes(url, headers=headers)
        events.append({"event": "candidate_response", "source": candidate.source, "url": url, "bytes": len(body)})
        return body

    try:
        body = request(candidate.url, {"Accept": "application/pdf,text/html;q=0.8,*/*;q=0.1"})
    except Exception as err:
        events.append(
            {
                "event": "candidate_error",
                "source": candidate.source,
                "url": candidate.url,
                "error": f"{type(err).__name__}: {err}",
            }
        )
        return b"", events, "request_error"
    if looks_like_pdf_bytes(body):
        return body, events, "direct_pdf"

    html = body[:500_000].decode("utf-8", errors="replace")
    pow_cookie = solve_pmc_pow_cookie(html)
    if pow_cookie:
        try:
            body = request(
                candidate.url,
                {
                    "Accept": "application/pdf,*/*;q=0.1",
                    "Cookie": pow_cookie,
                },
            )
        except Exception as err:
            events.append(
                {
                    "event": "pmc_pow_error",
                    "source": candidate.source,
                    "url": candidate.url,
                    "error": f"{type(err).__name__}: {err}",
                }
            )
            return b"", events, "pmc_pow_error"
        if looks_like_pdf_bytes(body):
            events.append({"event": "pmc_pow_success", "source": candidate.source, "url": candidate.url})
            return body, events, "pmc_pow"

    if allow_landing_resolution:
        for linked_url in extract_pdf_links(candidate.url, html):
            try:
                linked_body = client.get_bytes(
                    linked_url,
                    headers={"Accept": "application/pdf,*/*;q=0.1", "Referer": candidate.url},
                )
            except Exception as err:
                events.append(
                    {
                        "event": "landing_pdf_link_error",
                        "source": candidate.source,
                        "url": linked_url,
                        "error": f"{type(err).__name__}: {err}",
                    }
                )
                continue
            events.append(
                {
                    "event": "landing_pdf_link_response",
                    "source": candidate.source,
                    "url": linked_url,
                    "bytes": len(linked_body),
                }
            )
            if looks_like_pdf_bytes(linked_body):
                return linked_body, events, "landing_pdf_link"
            if "/server/api/core/bitstreams/search/showableByItem" in linked_url:
                try:
                    payload = json.loads(linked_body.decode("utf-8", errors="replace"))
                except Exception as err:
                    events.append(
                        {
                            "event": "dspace_bitstream_json_error",
                            "source": candidate.source,
                            "url": linked_url,
                            "error": f"{type(err).__name__}: {err}",
                        }
                    )
                    continue
                for content_url in dspace_original_content_links_from_json(linked_url, payload):
                    try:
                        content_body = client.get_bytes(
                            content_url,
                            headers={"Accept": "application/pdf,*/*;q=0.1", "Referer": candidate.url},
                        )
                    except Exception as err:
                        events.append(
                            {
                                "event": "dspace_bitstream_content_error",
                                "source": candidate.source,
                                "url": content_url,
                                "error": f"{type(err).__name__}: {err}",
                            }
                        )
                        continue
                    events.append(
                        {
                            "event": "dspace_bitstream_content_response",
                            "source": candidate.source,
                            "url": content_url,
                            "bytes": len(content_body),
                        }
                    )
                    if looks_like_pdf_bytes(content_body):
                        return content_body, events, "dspace_bitstream_content"

    return b"", events, "not_pdf"


def download_alternate_pdf_candidates(
    *,
    client: RateLimitedHttpClient,
    candidates: list[AlternatePdfCandidate],
    target_path: Path,
    study_doi: str = "",
    study_title: str = "",
    min_title_score: float = 0.86,
    allow_landing_resolution: bool = True,
    progress_callback=None,
) -> dict:
    if target_path.exists() and target_path.stat().st_size > 0:
        if file_is_valid_pdf(target_path):
            existing_body = target_path.read_bytes()
            valid_title, score, validation_basis = title_validation_result(
                study_title,
                existing_body,
                min_title_score,
                study_doi=study_doi,
            )
            if not valid_title:
                return {
                    "status": "invalid_pdf_existing",
                    "error": f"source_identity_mismatch:{validation_basis}:{score:.3f}",
                    "size": int(target_path.stat().st_size),
                    "selected_url": "",
                    "attempted_pdf_url_candidates": join_candidates(candidate.url for candidate in candidates),
                    "events": [
                        {
                            "event": "title_validation",
                            "source": "existing_local_pdf",
                            "url": str(target_path),
                            "score": round(score, 4),
                            "basis": validation_basis,
                            "accepted": False,
                        }
                    ],
                }
            return {
                "status": "already_present",
                "error": "",
                "size": int(target_path.stat().st_size),
                "selected_url": "",
                "attempted_pdf_url_candidates": join_candidates(candidate.url for candidate in candidates),
                "events": [],
            }
        return {
            "status": "invalid_pdf_existing",
            "error": "local_file_is_not_pdf",
            "size": int(target_path.stat().st_size),
            "selected_url": "",
            "attempted_pdf_url_candidates": join_candidates(candidate.url for candidate in candidates),
            "events": [],
        }

    errors: list[str] = []
    events: list[dict] = []
    for candidate in candidates:
        if progress_callback:
            progress_callback({"event": "alternate_candidate_attempt", **candidate.to_record()})
        body, candidate_events, mode = fetch_pdf_bytes_for_candidate(
            client=client,
            candidate=candidate,
            allow_landing_resolution=allow_landing_resolution,
        )
        events.extend(candidate_events)
        if not looks_like_pdf_bytes(body):
            event_errors = [clean(event.get("error", "")) for event in candidate_events]
            error_detail = next((error for error in reversed(event_errors) if error), "")
            suffix = f": {error_detail}" if error_detail else ""
            errors.append(f"{candidate.source}: {candidate.url} -> {mode}{suffix}")
            continue
        valid_title, score, validation_basis = title_validation_result(
            study_title,
            body,
            min_title_score,
            study_doi=study_doi,
        )
        events.append(
            {
                "event": "title_validation",
                "source": candidate.source,
                "url": candidate.url,
                "score": round(score, 4),
                "basis": validation_basis,
                "accepted": valid_title,
            }
        )
        if not valid_title:
            errors.append(
                f"{candidate.source}: {candidate.url} -> "
                f"source_identity_mismatch:{validation_basis}:{score:.3f}"
            )
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(".tmp")
        tmp_path.write_bytes(body)
        tmp_path.replace(target_path)
        if progress_callback:
            progress_callback({"event": "alternate_candidate_result", **candidate.to_record(), "status": "downloaded"})
        return {
            "status": "downloaded",
            "error": "",
            "size": len(body),
            "selected_url": candidate.url,
            "attempted_pdf_url_candidates": join_candidates(candidate.url for candidate in candidates),
            "events": events,
            "source": candidate.source,
            "download_mode": mode,
        }

    return {
        "status": "download_failed" if candidates else "no_pdf_url",
        "error": " || ".join(errors[:8]) if errors else "no_alternate_pdf_candidates",
        "size": 0,
        "selected_url": "",
        "attempted_pdf_url_candidates": join_candidates(candidate.url for candidate in candidates),
        "events": events,
    }
