#!/usr/bin/env python3
"""Fetch PMC full-text XML into the canonical full-text artifact store."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Iterable
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.build_extraction_routes import (  # noqa: E402
    DEFAULT_CANDIDATE_TABLE,
    DEFAULT_MANUAL_ROUTE_OVERRIDES,
    DEFAULT_METADATA_TABLE,
    DEFAULT_OUTPUT_TABLE,
    DEFAULT_PAPER_ROOT,
    DEFAULT_PRESCREEN_TABLE,
    DEFAULT_COUNTS_CSV,
    DEFAULT_SUMMARY_JSON,
    build_extraction_routes,
    build_local_pdf_index,
    fulltext_status_for_doi,
    local_pdf_status_for_doi,
)
from pipeline.fulltext.convert_pdfs import (  # noqa: E402
    compact_text,
    doi_to_slug,
    element_text,
    extraction_result,
    local_name,
    normalize,
    normalize_doi,
    now_utc,
    select_best_extraction,
    should_write_artifact,
)
from pipeline.ingest.sync_paper_library import (  # noqa: E402
    RateLimitedHttpClient,
    extract_pmcid_from_url,
    split_candidates,
)
from pipeline.fulltext.source_identity import (  # noqa: E402
    evaluate_artifact_identity,
    select_jats_article,
)
from pipeline.fulltext.source_identity_audit_gate import (  # noqa: E402
    DEFAULT_IDENTITY_REGISTRY,
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    DEFAULT_SOURCE_IDENTITY_AUDIT,
    DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
    DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
    refresh_source_identity_audit,
)

DEFAULT_METADATA = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_ROUTES = DEFAULT_OUTPUT_TABLE
DEFAULT_DOMAIN_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_OUT_DIR = DEFAULT_FULLTEXT_DIR / "articles"
DEFAULT_REPORT = DEFAULT_FULLTEXT_DIR / "pmc_xml_report.json"
DEFAULT_USER_AGENT = "kg-pipeline/pmc-fulltext-xml"


class FullTextXmlNotAvailable(RuntimeError):
    """Raised when known PMC XML endpoints report no reusable full text."""


def clean(value: object) -> str:
    return normalize(value)


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def join_values(values: Iterable[object]) -> str:
    out: list[str] = []
    for value in values:
        text = clean(value)
        if text and text not in out:
            out.append(text)
    return "|".join(out)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi.lower())
    return out


def pmcid_from_metadata(row: dict) -> str:
    pmcid = clean(row.get("pmcid", "")).upper()
    if pmcid:
        return pmcid
    for field in ("best_pdf_url", "pdf_url_candidates", "open_access_url"):
        for candidate in split_candidates(row.get(field, "")):
            pmcid = extract_pmcid_from_url(candidate)
            if pmcid:
                return pmcid.upper()
    return ""


def metadata_by_doi(metadata_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if metadata_df.empty or "doi" not in metadata_df.columns:
        return out
    for row in metadata_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if doi and doi not in out:
            out[doi] = row
    return out


def direct_title(element: ET.Element, default: str = "Section") -> str:
    for child in list(element):
        if local_name(child.tag) in {"title", "head"}:
            title = element_text(child)
            if title:
                return title
    return default


def direct_child_text(element: ET.Element, names: set[str]) -> str:
    parts: list[str] = []
    for child in list(element):
        if local_name(child.tag) in names:
            text = element_text(child)
            if text:
                parts.append(text)
    return compact_text(" ".join(parts))


def xml_id(element: ET.Element) -> str:
    return clean(element.attrib.get("{http://www.w3.org/XML/1998/namespace}id", "") or element.attrib.get("id", ""))


def section_summary(heading: str, text: str, *, level: int, identifier: str = "") -> dict:
    body = compact_text(text)
    return {
        "heading": clean(heading) or "Section",
        "level": level,
        "xml_id": identifier,
        "char_count": len(body),
        "snippet": body[:500],
    }


def walk_jats_sec(sec: ET.Element, sections: list[dict], level: int = 1) -> None:
    heading = direct_title(sec)
    text_parts: list[str] = []
    for child in list(sec):
        name = local_name(child.tag)
        if name in {"title", "sec", "fig", "table-wrap", "table"}:
            continue
        if name in {"p", "list", "disp-quote", "boxed-text", "statement"}:
            text = element_text(child)
            if text:
                text_parts.append(text)
    body = compact_text(" ".join(text_parts))
    if body:
        sections.append(section_summary(heading, body, level=level, identifier=xml_id(sec)))

    for child in list(sec):
        if local_name(child.tag) == "sec":
            walk_jats_sec(child, sections, level=level + 1)


def sections_from_jats(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        text = compact_text(xml_text)
        return [section_summary("Document", text, level=0)] if text else []

    sections: list[dict] = []
    for abstract in [element for element in root.iter() if local_name(element.tag) == "abstract"]:
        text = direct_child_text(abstract, {"p", "sec"}) or element_text(abstract)
        if text:
            sections.append(section_summary("Abstract", text, level=1, identifier=xml_id(abstract)))

    for body in [element for element in root.iter() if local_name(element.tag) == "body"]:
        direct = direct_child_text(body, {"p", "list", "disp-quote"})
        if direct:
            sections.append(section_summary("Body", direct, level=1, identifier=xml_id(body)))
        for child in list(body):
            if local_name(child.tag) == "sec":
                walk_jats_sec(child, sections, level=1)

    if not sections:
        text = element_text(root)
        if text:
            sections.append(section_summary("Document", text, level=0, identifier=xml_id(root)))
    return sections


def article_title_from_xml(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    for element in root.iter():
        if local_name(element.tag) == "article-title":
            title = element_text(element)
            if title:
                return title
    return ""


def pmcid_number(pmcid: str) -> str:
    text = clean(pmcid).upper()
    return text.removeprefix("PMC")


def oai_error(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    for element in root.iter():
        if local_name(element.tag) == "error":
            code = clean(element.attrib.get("code", ""))
            message = element_text(element)
            return f"{code}: {message}".strip(": ")
    return ""


def build_xml_artifact(
    row: dict,
    *,
    pmcid: str,
    endpoint: str,
    xml_text: str,
    retrieval_source: str,
    retrieval_trace: list[dict],
) -> dict:
    # A PMCID identifies what the endpoint returned; it does not prove that the
    # returned article belongs to the DOI requested by our corpus.  Select an
    # exact JATS article/sub-article and reject the artifact if no exact DOI is
    # present.  This also prevents adjacent conference abstracts from leaking
    # into a DOI-specific artifact.
    selected_xml, document_identity = select_jats_article(xml_text, row.get("doi", ""))
    sections = sections_from_jats(selected_xml)
    extraction = extraction_result(
        retrieval_source,
        "ok" if sections else "failed",
        text=selected_xml,
        sections=sections,
        error="" if sections else "no_sections_extracted",
        metadata={
            "format": "jats_xml",
            "source": retrieval_source,
            "pmcid": pmcid,
            "endpoint": endpoint,
            "retrieval_trace": retrieval_trace,
        },
    )
    extractions = [extraction]
    best = select_best_extraction(extractions)
    artifact = {
        "schema_version": "0.1",
        "created_at_utc": now_utc(),
        "dataset": "articles",
        "fulltext_artifact_layout": "canonical_articles_v1",
        "study_doi": normalize_doi(row.get("doi", "")),
        "openalex_id": clean(row.get("openalex_id", "")),
        "study_title": clean(document_identity.get("title", "")) or article_title_from_xml(selected_xml),
        "requested_study_title": clean(row.get("study_title", "")),
        "study_year": clean(row.get("study_year", "")),
        "pdf_local_path": "",
        "fulltext_source": retrieval_source,
        "pmcid": pmcid,
        "retrieval_endpoint": endpoint,
        "retrieval_trace": retrieval_trace,
        "best_backend": clean(best.get("backend", "")) if best else "",
        "best_char_count": int(best.get("char_count", 0) or 0) if best else 0,
        "best_section_count": int(best.get("section_count", 0) or 0) if best else 0,
        "extractions": extractions,
    }
    artifact["source_identity"] = evaluate_artifact_identity(
        artifact,
        requested_doi=row.get("doi", ""),
        requested_title=row.get("study_title", "") or document_identity.get("title", ""),
    )
    if not artifact["source_identity"].get("verified"):
        raise ValueError(
            "XML source identity was not verified: "
            f"{artifact['source_identity'].get('basis', 'unknown reason')}"
        )
    return artifact


def fetch_europepmc_fulltext_xml(client: RateLimitedHttpClient, pmcid: str) -> tuple[str, str]:
    endpoint = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    body = client.get_bytes(endpoint, headers={"Accept": "application/xml"})
    return endpoint, body.decode("utf-8", errors="replace")


def fetch_pmc_oai_xml(client: RateLimitedHttpClient, pmcid: str) -> tuple[str, str]:
    number = pmcid_number(pmcid)
    endpoint = (
        "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
        f"?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{number}&metadataPrefix=pmc"
    )
    body = client.get_bytes(endpoint, headers={"Accept": "application/xml"})
    xml_text = body.decode("utf-8", errors="replace")
    error = oai_error(xml_text)
    if error:
        raise FullTextXmlNotAvailable(f"PMC OAI error: {error}")
    return endpoint, xml_text


def error_record(source: str, endpoint: str, err: Exception) -> dict:
    message = f"{type(err).__name__}: {err}"
    unavailable = (
        isinstance(err, FullTextXmlNotAvailable)
        or "HTTP Error 404" in message
        or "idDoesNotExist" in message
        or "cannotDisseminateFormat" in message
    )
    return {
        "source": source,
        "endpoint": endpoint,
        "status": "not_available" if unavailable else "failed",
        "error": message,
    }


def fetch_fulltext_xml(client: RateLimitedHttpClient, pmcid: str) -> tuple[str, str, str, list[dict]]:
    attempts: list[dict] = []
    endpoints = {
        "europepmc_fulltext_xml": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
        "pmc_oai_xml": (
            "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
            f"?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid_number(pmcid)}&metadataPrefix=pmc"
        ),
    }
    for source, fetcher in (
        ("europepmc_fulltext_xml", fetch_europepmc_fulltext_xml),
        ("pmc_oai_xml", fetch_pmc_oai_xml),
    ):
        try:
            endpoint, xml_text = fetcher(client, pmcid)
            if not sections_from_jats(xml_text):
                raise FullTextXmlNotAvailable("no_parseable_sections")
            attempts.append({"source": source, "endpoint": endpoint, "status": "ok", "error": ""})
            return source, endpoint, xml_text, attempts
        except Exception as err:
            attempts.append(error_record(source, endpoints[source], err))
            continue
    if attempts and all(attempt.get("status") == "not_available" for attempt in attempts):
        raise FullTextXmlNotAvailable(json.dumps(attempts, ensure_ascii=False))
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))


def selected_rows(
    *,
    routes_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    fulltext_dir: Path,
    paper_root: Path,
    doi_filter: set[str] | None,
    include_existing_fulltext: bool,
    include_local_pdf: bool,
    include_non_retained: bool,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
) -> tuple[list[dict], Counter[str]]:
    metadata_map = metadata_by_doi(metadata_df)
    local_pdf_index = build_local_pdf_index(paper_root)
    grouped: dict[str, list[dict]] = {}
    for row in routes_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if not doi:
            continue
        grouped.setdefault(doi, []).append(row)

    rows: list[dict] = []
    skipped: Counter[str] = Counter()
    for doi in sorted(grouped):
        if doi_filter is not None and doi not in doi_filter:
            skipped["doi_filter"] += 1
            continue
        route_rows = grouped[doi]
        retained = any(truthy(row.get("retained_for_extraction_candidate", False)) for row in route_rows)
        if not retained and not include_non_retained:
            skipped["not_retained"] += 1
            continue
        if not include_existing_fulltext and fulltext_status_for_doi(
            doi,
            fulltext_dir,
            source_identity_audit=source_identity_audit,
        ).get("has_converted_full_text"):
            skipped["existing_fulltext"] += 1
            continue
        if not include_local_pdf and local_pdf_status_for_doi(doi, local_pdf_index).get("has_local_pdf"):
            skipped["local_pdf_available"] += 1
            continue
        metadata = metadata_map.get(doi, {})
        pmcid = pmcid_from_metadata(metadata)
        if not pmcid:
            skipped["missing_pmcid"] += 1
            continue
        rows.append({**metadata, "doi": doi, "pmcid": pmcid})
    return rows, skipped


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch PMC full-text XML into full-text artifacts.")
    parser.add_argument("--routes-table", default=str(DEFAULT_ROUTES))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--source-identity-audit", default=str(DEFAULT_SOURCE_IDENTITY_AUDIT))
    parser.add_argument(
        "--source-identity-audit-csv",
        default=str(DEFAULT_SOURCE_IDENTITY_AUDIT_CSV),
    )
    parser.add_argument(
        "--source-identity-unverified-dois",
        default=str(DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS),
    )
    parser.add_argument("--identity-registry", default=str(DEFAULT_IDENTITY_REGISTRY))
    parser.add_argument(
        "--pdf-hash-attestation-registry",
        default=str(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY),
    )
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--max-retry-after-sec", type=int, default=60)
    parser.add_argument("--include-existing-fulltext", action="store_true")
    parser.add_argument("--include-local-pdf", action="store_true")
    parser.add_argument("--include-non-retained", action="store_true")
    parser.add_argument("--write-failed-artifacts", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--no-rebuild-routes-after",
        action="store_true",
        help="Do not rebuild extraction routes after successful XML artifacts are written.",
    )
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    routes_table = Path(args.routes_table).resolve()
    metadata_table = Path(args.metadata_table).resolve()
    fulltext_dir = Path(args.fulltext_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    report_path = Path(args.report).resolve()
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None

    rows, skipped = selected_rows(
        routes_df=pd.read_parquet(routes_table),
        metadata_df=pd.read_parquet(metadata_table),
        fulltext_dir=fulltext_dir,
        paper_root=Path(args.paper_root).resolve(),
        doi_filter=doi_filter,
        include_existing_fulltext=bool(args.include_existing_fulltext),
        include_local_pdf=bool(args.include_local_pdf),
        include_non_retained=bool(args.include_non_retained),
        source_identity_audit=Path(args.source_identity_audit).resolve(),
    )
    if args.limit > 0:
        skipped["deferred_by_limit"] += max(0, len(rows) - args.limit)
        rows = rows[: args.limit]

    client = RateLimitedHttpClient(
        rps=max(0.01, args.rps),
        max_retries=max(0, args.max_retries),
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=max(0, args.max_retry_after_sec),
        user_agent=DEFAULT_USER_AGENT,
    )
    counts: Counter[str] = Counter()
    records: list[dict] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        "START: PMC full-text XML "
        f"targets={len(rows):,} skipped={dict(skipped)} out_dir={out_dir} dry_run={bool(args.dry_run)}",
        flush=True,
    )
    for position, row in enumerate(rows, start=1):
        doi = normalize_doi(row.get("doi", "")).lower()
        pmcid = clean(row.get("pmcid", "")).upper()
        artifact_path = out_dir / f"{doi_to_slug(doi)}.json"
        record = {
            "doi": doi,
            "pmcid": pmcid,
            "artifact_path": str(artifact_path),
            "status": "dry_run" if args.dry_run else "",
            "error": "",
            "best_char_count": 0,
            "best_section_count": 0,
            "write_status": "",
        }
        if args.dry_run:
            counts["dry_run"] += 1
        else:
            try:
                source, endpoint, xml_text, retrieval_trace = fetch_fulltext_xml(client, pmcid)
                artifact = build_xml_artifact(
                    row,
                    pmcid=pmcid,
                    endpoint=endpoint,
                    xml_text=xml_text,
                    retrieval_source=source,
                    retrieval_trace=retrieval_trace,
                )
                write, reason = should_write_artifact(
                    artifact_path,
                    artifact,
                    write_failed_artifacts=bool(args.write_failed_artifacts),
                )
                record["best_char_count"] = int(artifact.get("best_char_count", 0) or 0)
                record["best_section_count"] = int(artifact.get("best_section_count", 0) or 0)
                record["write_status"] = reason
                if write:
                    write_json(artifact_path, artifact)
                    counts["written"] += 1
                    counts[f"written_{source}"] += 1
                    record["status"] = "written"
                else:
                    counts["not_written"] += 1
                    record["status"] = "not_written"
            except Exception as err:
                message = f"{type(err).__name__}: {err}"
                record["error"] = message
                if isinstance(err, FullTextXmlNotAvailable) or "HTTP Error 404" in message:
                    record["status"] = "not_available"
                    counts["not_available"] += 1
                else:
                    record["status"] = "failed"
                    counts["failed"] += 1
        records.append(record)
        if args.progress_every > 0 and (position % args.progress_every == 0 or position == len(rows)):
            print(
                "PROGRESS: PMC full-text XML "
                f"{position:,}/{len(rows):,} written={counts['written']:,} "
                f"not_available={counts['not_available']:,} failed={counts['failed']:,}",
                flush=True,
            )

    source_identity_audit_refresh = {}
    if not args.dry_run and counts["written"] > 0:
        print("SOURCE_IDENTITY_AUDIT: refreshing before route rebuild", flush=True)
        source_identity_audit_refresh = refresh_source_identity_audit(
            artifact_dir=out_dir,
            candidate_table=Path(args.candidate_table),
            metadata_table=metadata_table,
            report_json=Path(args.source_identity_audit),
            report_csv=Path(args.source_identity_audit_csv),
            unverified_doi_file=Path(args.source_identity_unverified_dois),
            identity_registry_path=Path(args.identity_registry),
            pdf_hash_attestation_registry_path=Path(args.pdf_hash_attestation_registry),
        )

    route_rebuild = {}
    if not args.dry_run and counts["written"] > 0 and not args.no_rebuild_routes_after:
        print("ROUTE_REBUILD: rebuilding extraction routes after PMC XML artifacts", flush=True)
        route_rebuild = build_extraction_routes(
            metadata_table=metadata_table,
            candidate_table=Path(args.candidate_table).resolve(),
            prescreen_table=Path(args.prescreen_table).resolve(),
            domain_table=Path(args.domain_routing_table).resolve() if clean(args.domain_routing_table) else None,
            fulltext_dir=fulltext_dir,
            source_identity_audit=Path(args.source_identity_audit).resolve(),
            paper_root=Path(args.paper_root).resolve(),
            output_table=routes_table,
            summary_json=Path(args.route_summary_json).resolve(),
            counts_csv=Path(args.route_counts_csv).resolve(),
            manual_overrides_path=Path(args.manual_route_overrides).resolve()
            if clean(args.manual_route_overrides)
            else None,
        )
        print(
            "ROUTE_REBUILD: complete "
            f"route_rows={route_rebuild.get('route_rows', 0):,} "
            f"routed_dois={route_rebuild.get('routed_dois', 0):,}",
            flush=True,
        )

    report = {
        "generated_at_utc": now_utc(),
        "inputs": {
            "routes_table": str(routes_table),
            "metadata_table": str(metadata_table),
            "fulltext_dir": str(fulltext_dir),
            "out_dir": str(out_dir),
            "source_identity_audit": str(Path(args.source_identity_audit).resolve()),
            "doi_file": clean(args.doi_file),
            "include_existing_fulltext": bool(args.include_existing_fulltext),
            "include_local_pdf": bool(args.include_local_pdf),
            "include_non_retained": bool(args.include_non_retained),
        },
        "counts": {
            "targets": len(rows),
            "skipped": dict(skipped),
            "status": dict(counts),
            "route_rebuild_performed": bool(route_rebuild),
            "source_identity_audit_refreshed": bool(source_identity_audit_refresh),
        },
        "records": records,
    }
    if not args.dry_run:
        write_json(report_path, report)
    print(f"Targets: {len(rows):,}")
    print(f"Skipped: {dict(skipped)}")
    print(f"Status: {dict(counts)}")
    print(f"Route rebuild performed: {bool(route_rebuild)}")
    print(f"Dry run: {bool(args.dry_run)}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
