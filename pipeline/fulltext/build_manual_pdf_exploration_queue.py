#!/usr/bin/env python3
"""Build a human-oriented PDF recovery queue and host-pattern scout.

This queue is separate from eligibility and candidate-paper state. It ranks
only records for which the current full-text worklist has a known URL route;
prior retrieval failures remain non-terminal provenance.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "processed" / "corpus"
AUDITS = CORPUS / "audits"
DEFAULT_WORKLIST = CORPUS / "fulltext_enrichment_worklist.parquet"
DEFAULT_RANKED = AUDITS / "manual_pdf_download_ranked.csv"
DEFAULT_HOST_PASS = AUDITS / "doi_browser_host_pass_queue_20260719.csv"
DEFAULT_PASS3 = AUDITS / "doi_browser_pass3_lower_yield_queue_20260719_v1.csv"
DEFAULT_TECHNICAL_RETRY = AUDITS / "doi_browser_technical_retry_queue_20260719.csv"
DEFAULT_LANGUAGE_AUDIT = AUDITS / "manual_pdf_recovery_language_audit.csv"
DEFAULT_QUEUE = AUDITS / "manual_pdf_recovery_priority_queue.csv"
DEFAULT_HOST_SUMMARY = AUDITS / "manual_pdf_recovery_host_summary.csv"
DEFAULT_SCOUT = AUDITS / "manual_pdf_recovery_pattern_scout.csv"
DEFAULT_SCOUT_HTML = AUDITS / "manual_pdf_recovery_pattern_scout.html"
DEFAULT_REPORT = AUDITS / "manual_pdf_recovery_priority_report.json"

UNTRUSTED_HOST_MARKERS = ("scholarhub.ui.ac.id",)
REPOSITORY_HOST_MARKERS = (
    "repository", "eprints", "scholarworks", "dspace", "zenodo", "figshare",
    "osf.io", "archive.org", "escholarship", "researchgate", "hdl.handle.net",
    "handle.net", ".edu", ".ac.",
)
PUBLISHER_HOST_MARKERS = (
    "wiley", "tandfonline", "sciencedirect", "elsevier", "springer", "nature.com",
    "sagepub", "oup.com", "academic.oup.com", "cambridge.org", "jamanetwork", "bmj.com",
)
LANE_LABELS = {
    1: "direct_pdf_browser_rescue",
    2: "oa_repository_or_open_journal_landing",
    3: "oa_publisher_or_doi_clickthrough",
    4: "lower_confidence_or_metadata_conflict",
    5: "identity_publication_format_or_language_review",
    6: "non_english_excluded_from_manual_recovery",
}


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def truthy(value: object) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def split_pipe(value: object) -> list[str]:
    return [part.strip() for part in clean(value).split("|") if part.strip()]


def normalized_host(url: object) -> str:
    host = urlparse(clean(url)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def unique_urls(*values: object) -> list[str]:
    out: list[str] = []
    for value in values:
        for url in split_pipe(value):
            if url and url not in out:
                out.append(url)
    return out


def route_host_class(host: str) -> str:
    if any(marker in host for marker in UNTRUSTED_HOST_MARKERS):
        return "untrusted_source"
    if host in {"doi.org", "dx.doi.org"}:
        return "doi_resolver"
    if host in {"doaj.org", "pubmed.ncbi.nlm.nih.gov"}:
        return "bibliographic_landing"
    if any(marker in host for marker in REPOSITORY_HOST_MARKERS):
        return "repository_or_institutional"
    if any(marker in host for marker in PUBLISHER_HOST_MARKERS):
        return "publisher_platform"
    return "other_article_host" if host else "missing_host"


def _route_score(url: str, *, probable: bool, oa_url: str) -> tuple[int, str]:
    host = normalized_host(url)
    path = urlparse(url).path.lower()
    score = 100 if probable else 0
    score += 12 if url == oa_url else 0
    score += 20 if host not in {"doi.org", "dx.doi.org", "pubmed.ncbi.nlm.nih.gov"} else 0
    score += 20 if path.endswith(".pdf") or "/pdf" in path or "download" in path or "bitstream" in path else 0
    hclass = route_host_class(host)
    score += 10 if hclass == "repository_or_institutional" else 0
    score -= 200 if hclass == "untrusted_source" else 0
    return score, url


def pick_primary_route(row: dict) -> tuple[str, str]:
    probable = unique_urls(row.get("probable_pdf_url_candidates", ""))
    oa_url = clean(row.get("open_access_url_current", row.get("open_access_url", "")))
    candidates = unique_urls(
        row.get("probable_pdf_url_candidates", ""), oa_url,
        row.get("pdf_url_candidates_current", row.get("pdf_url_candidates", "")),
        row.get("best_pdf_url_current", row.get("best_pdf_url", "")),
    )
    if not candidates:
        doi = clean(row.get("doi", "")).lower()
        return (f"https://doi.org/{doi}" if doi.startswith("10.") else "", "doi_landing")
    probable_set = set(probable)
    route = max(candidates, key=lambda url: _route_score(url, probable=url in probable_set, oa_url=oa_url))
    host, path = normalized_host(route), urlparse(route).path.lower()
    if route in probable_set:
        kind = "probable_pdf_url"
    elif host in {"doi.org", "dx.doi.org"}:
        kind = "doi_landing"
    elif path.endswith(".pdf") or "/pdf" in path or "download" in path or "bitstream" in path:
        kind = "possible_direct_download"
    else:
        kind = "oa_or_article_landing"
    return route, kind


def oa_positive(row: dict) -> bool:
    status = clean(row.get("open_access_status_current", row.get("open_access_status", ""))).lower()
    return truthy(row.get("open_access_is_oa", "")) or status in {"gold", "green", "bronze", "diamond", "hybrid"}


def provisional_format_risk(row: dict) -> str:
    """Return a review signal, never an exclusion decision."""
    title = clean(row.get("study_title_current", row.get("study_title", ""))).lower()
    doi = clean(row.get("doi", "")).lower()
    if re.search(r"\b(conference|congress|meeting abstract|oral presentation)\b", title):
        return "title suggests conference/meeting material"
    if re.match(r"^(?:poster sessions?|speaker\s*\d+|poster\s*\d+)\b", title):
        return "title suggests a poster/session abstract rather than an article"
    if re.match(r"^appendix\b", title) or re.search(r"\.app\d+$", doi):
        return "title/DOI suggests a book appendix rather than a journal article"
    if re.search(r"\b(thesis|dissertation)\b", title):
        return "title suggests a thesis or dissertation"
    return ""


def priority_lane(row: dict) -> tuple[int, str]:
    failure = clean(row.get("pdf_download_failure_category", "")).lower()
    quality = clean(row.get("pdf_url_quality", "")).lower()
    hclass = route_host_class(clean(row.get("route_host", "")))
    doi_ok = truthy(row.get("manual_doi_article_recovery_candidate", ""))
    doi_hint = clean(row.get("manual_doi_article_recovery_hint", "")).lower()
    format_risk = provisional_format_risk(row)
    if failure == "source_identity_mismatch":
        return 5, "Prior URL produced a document whose DOI/title identity did not match."
    if format_risk:
        return 5, f"Publication-format review required: {format_risk}."
    if hclass == "untrusted_source" or (not doi_ok and any(x in doi_hint for x in ("untrusted", "abstract", "thesis", "deposit"))):
        return 5, "Review source identity/publication format before accepting a PDF."
    if not oa_positive(row):
        return 4, "A URL exists, but current OA metadata is closed or internally inconsistent."
    if quality == "probable_pdf":
        if failure == "not_found":
            return 4, "The probable PDF URL is stale/not found; use DOI landing as fallback."
        return 1, "Open probable PDF URL in browser; direct automation was blocked or returned a non-PDF response."
    if hclass == "repository_or_institutional":
        return 2, "Open item page and look for PDF, download, bitstream, or files controls."
    if hclass in {"publisher_platform", "doi_resolver", "bibliographic_landing", "other_article_host"}:
        return 3, "Open article/DOI landing and follow full-text, PDF, or download controls."
    return 4, "Known route is incomplete; inspect DOI landing and alternate URLs manually."


def priority_score(row: dict, host_count: int) -> int:
    lane = int(row["priority_lane"])
    status = clean(row.get("open_access_status", "")).lower()
    failure = clean(row.get("prior_download_failure", "")).lower()
    hclass = clean(row.get("route_host_class", ""))
    score = {1: 500, 2: 400, 3: 300, 4: 200, 5: 100, 6: 0}[lane]
    score += {"gold": 24, "diamond": 24, "green": 22, "bronze": 12, "hybrid": 8, "closed": -25}.get(status, 0)
    score += {"repository_or_institutional": 20, "other_article_host": 12, "publisher_platform": 8,
              "doi_resolver": 4, "bibliographic_landing": 2, "untrusted_source": -50}.get(hclass, 0)
    score += {"forbidden": 12, "non_pdf_response": 12, "other_download_failure": 10,
              "timeout": 6, "provider_error": 5, "not_found": -15, "source_identity_mismatch": -35}.get(failure, 0)
    score += 4 if clean(row.get("source_family", "")) == "secondary_literature" else 0
    return score + min(20, int(round(math.log2(max(host_count, 1) + 1) * 3)))


def recommended_strategy(host: str, route_types: set[str]) -> str:
    hclass = route_host_class(host)
    if "probable_pdf_url" in route_types:
        return "Test direct PDF URL; automate a host-specific browser/session download if repeatable."
    if hclass == "repository_or_institutional":
        return "Identify item-page file/bitstream control or repository API pattern."
    if hclass == "publisher_platform":
        return "Follow article/full-text/PDF controls; record publisher-specific click path."
    if hclass == "doi_resolver":
        return "Resolve DOI, confirm identity/access, then record final publisher/PDF pattern."
    if hclass == "bibliographic_landing":
        return "Follow bibliographic landing to the journal article and record final host."
    return "Inspect representative pages and record any stable PDF/download pattern."


def load_optional_by_doi(path: Path, status_columns: tuple[str, ...], reason_columns: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "doi" not in frame.columns:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for row in frame.to_dict("records"):
        doi = clean(row.get("doi", "")).lower()
        status = next((clean(row.get(c, "")) for c in status_columns if clean(row.get(c, ""))), "")
        reason = next((clean(row.get(c, "")) for c in reason_columns if clean(row.get(c, ""))), "")
        if doi:
            out[doi] = (status, reason)
    return out


def build_queue(
    worklist: pd.DataFrame,
    ranked: pd.DataFrame,
    *,
    host_pass=None,
    pass3=None,
    technical_retry=None,
    language_audit=None,
) -> pd.DataFrame:
    current = worklist[worklist["fulltext_enrichment_action"].eq("download_known_pdf")].copy()
    current["doi"] = current["doi"].fillna("").astype(str).str.strip().str.lower()
    old = ranked.copy()
    old["doi"] = old["doi"].fillna("").astype(str).str.strip().str.lower()
    merged = old.merge(current, on="doi", how="inner", suffixes=("", "_current"))
    host_pass, pass3, technical_retry = host_pass or {}, pass3 or {}, technical_retry or {}
    language_audit = language_audit or {}
    records = []
    for row in merged.fillna("").to_dict("records"):
        doi = clean(row.get("doi", "")).lower()
        route, route_type = pick_primary_route(row)
        row["route_host"] = normalized_host(route)
        row["route_host_class"] = route_host_class(row["route_host"])
        lane, reason = priority_lane(row)
        language = language_audit.get(doi, {})
        language_decision = clean(language.get("language_audit_decision", ""))
        if language_decision == "exclude_non_english":
            lane = 6
            reason = "High-confidence title-language audit identifies a non-English record."
        elif language_decision == "review_language_signal" and lane < 5:
            lane = 5
            reason = "Language metadata and title-language evidence require review before PDF recovery."
        prior_status, prior_reason = technical_retry.get(doi, pass3.get(doi, host_pass.get(doi, ("not_attempted_in_browser_log", ""))))
        all_urls = unique_urls(row.get("probable_pdf_url_candidates", ""), row.get("open_access_url_current", ""),
                               row.get("pdf_url_candidates_current", ""), row.get("best_pdf_url_current", ""))
        records.append({
            "priority_lane": lane, "priority_group": LANE_LABELS[lane], "priority_reason": reason,
            "doi": doi, "doi_url": f"https://doi.org/{doi}",
            "study_title": clean(row.get("study_title_current", row.get("study_title", ""))),
            "study_year": clean(row.get("study_year_current", row.get("study_year", ""))),
            "study_journal": clean(row.get("study_journal", "")),
            "source_family": clean(row.get("source_family", "")), "source_type": clean(row.get("source_type", "")),
            "open_access_is_oa": clean(row.get("open_access_is_oa", "")),
            "open_access_status": clean(row.get("open_access_status_current", row.get("open_access_status", ""))),
            "route_type": route_type, "primary_route_url": route, "route_host": row["route_host"],
            "route_host_class": row["route_host_class"],
            "alternate_urls": "|".join(url for url in all_urls if url != route),
            "pdf_url_quality": clean(row.get("pdf_url_quality", "")),
            "publication_format_review_signal": provisional_format_risk(row),
            "metadata_language": clean(language.get("metadata_language", "")),
            "detected_title_language": clean(language.get("detected_title_language", "")),
            "detected_title_language_confidence": clean(language.get("detected_title_language_confidence", "")),
            "language_audit_decision": language_decision,
            "language_audit_evidence": clean(language.get("format_evidence", "")),
            "prior_download_failure": clean(row.get("pdf_download_failure_category", "")),
            "prior_browser_status": prior_status, "prior_browser_reason": prior_reason,
            "manual_recovery_instruction": reason, "manual_review_status": "", "manual_review_notes": "",
        })
    out = pd.DataFrame(records)
    if out.empty:
        return out
    counts = out["route_host"].value_counts().to_dict()
    out["host_candidate_count"] = out["route_host"].map(counts).fillna(0).astype(int)
    out["priority_score"] = [priority_score(row, int(row["host_candidate_count"])) for row in out.to_dict("records")]
    out = out.sort_values(["priority_lane", "priority_score", "host_candidate_count", "route_host", "doi"],
                          ascending=[True, False, False, True, True]).reset_index(drop=True)
    out.insert(0, "queue_rank", range(1, len(out) + 1))
    return out


def build_host_summary(queue: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for host, group in queue.groupby("route_host", dropna=False):
        top = group.sort_values(["priority_lane", "priority_score"], ascending=[True, False]).iloc[0]
        route_types = set(group["route_type"].astype(str))
        rows.append({
            "route_host": host, "route_host_class": route_host_class(host), "candidate_count": len(group),
            "high_priority_count": int(group["priority_lane"].isin([1, 2, 3]).sum()),
            "probable_pdf_count": int(group["route_type"].eq("probable_pdf_url").sum()),
            "landing_page_count": int((~group["route_type"].eq("probable_pdf_url")).sum()),
            "priority_groups": json.dumps(dict(Counter(group["priority_group"].astype(str))), sort_keys=True),
            "oa_statuses": json.dumps(dict(Counter(group["open_access_status"].astype(str))), sort_keys=True),
            "prior_failure_categories": json.dumps(dict(Counter(group["prior_download_failure"].astype(str))), sort_keys=True),
            "recommended_pattern_test": recommended_strategy(host, route_types),
            "example_doi": top["doi"], "example_title": top["study_title"], "example_route_url": top["primary_route_url"],
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(["high_priority_count", "candidate_count", "route_host"],
                                         ascending=[False, False, True]).reset_index(drop=True)
    out.insert(0, "host_pattern_rank", range(1, len(out) + 1))
    return out


def build_pattern_scout(queue: pd.DataFrame, host_summary: pd.DataFrame, *, max_hosts: int, examples_per_host: int) -> pd.DataFrame:
    hosts = host_summary.loc[host_summary["high_priority_count"].gt(0), "route_host"].head(max_hosts).tolist()
    chunks = []
    for host_rank, host in enumerate(hosts, start=1):
        sample = queue[queue["route_host"].eq(host) & queue["priority_lane"].isin([1, 2, 3])].head(examples_per_host).copy()
        sample.insert(0, "host_pattern_rank", host_rank)
        sample.insert(1, "example_within_host", range(1, len(sample) + 1))
        chunks.append(sample)
    if not chunks:
        return pd.DataFrame(columns=["scout_rank", *queue.columns])
    out = pd.concat(chunks, ignore_index=True)
    out.insert(0, "scout_rank", range(1, len(out) + 1))
    return out


def write_scout_html(path: Path, scout: pd.DataFrame) -> None:
    rows = []
    for row in scout.fillna("").to_dict("records"):
        rows.append("<tr>" +
            f"<td>{int(row['scout_rank'])}</td><td>{html.escape(clean(row['priority_group']))}</td>" +
            f"<td>{html.escape(clean(row['route_host']))}</td>" +
            f"<td><a href=\"{html.escape(clean(row['doi_url']), quote=True)}\">{html.escape(clean(row['doi']))}</a></td>" +
            f"<td>{html.escape(clean(row['study_title']))}</td><td>{html.escape(clean(row['open_access_status']))}</td>" +
            f"<td><a href=\"{html.escape(clean(row['primary_route_url']), quote=True)}\">open route</a></td>" +
            f"<td>{html.escape(clean(row['prior_browser_status']))}</td>" +
            f"<td>{html.escape(clean(row['manual_recovery_instruction']))}</td></tr>")
    document = """<!doctype html><html><head><meta charset="utf-8"><title>Manual PDF recovery pattern scout</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:24px;line-height:1.35}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ddd;padding:7px;vertical-align:top}th{position:sticky;top:0;background:#f4f4f4;text-align:left}tr:nth-child(even){background:#fafafa}a{color:#075bcc}</style></head><body>
<h1>Manual PDF recovery pattern scout</h1><p>Representative high-priority records grouped by host. Confirm article identity before saving. Unresolved failures remain retrieval provenance only.</p>
<table><thead><tr><th>#</th><th>Lane</th><th>Host</th><th>DOI</th><th>Title</th><th>OA</th><th>Route</th><th>Prior browser result</th><th>What to try</th></tr></thead><tbody>""" + "".join(rows) + "</tbody></table></body></html>"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worklist", default=str(DEFAULT_WORKLIST)); parser.add_argument("--ranked", default=str(DEFAULT_RANKED))
    parser.add_argument("--host-pass", default=str(DEFAULT_HOST_PASS)); parser.add_argument("--pass3", default=str(DEFAULT_PASS3))
    parser.add_argument("--technical-retry", default=str(DEFAULT_TECHNICAL_RETRY)); parser.add_argument("--output-queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--language-audit", default=str(DEFAULT_LANGUAGE_AUDIT))
    parser.add_argument("--output-host-summary", default=str(DEFAULT_HOST_SUMMARY)); parser.add_argument("--output-scout", default=str(DEFAULT_SCOUT))
    parser.add_argument("--output-scout-html", default=str(DEFAULT_SCOUT_HTML)); parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    parser.add_argument("--max-scout-hosts", type=int, default=60); parser.add_argument("--examples-per-host", type=int, default=3)
    args = parser.parse_args()
    worklist = pd.read_parquet(Path(args.worklist)); ranked = pd.read_csv(Path(args.ranked), dtype=str, keep_default_na=False)
    host_pass = load_optional_by_doi(Path(args.host_pass), ("prior_browser_status",), ("prior_browser_reason",))
    pass3 = load_optional_by_doi(Path(args.pass3), ("internal_browser_status",), ("internal_browser_reason",))
    technical = load_optional_by_doi(Path(args.technical_retry), ("status",), ("reason", "error"))
    language_audit = {}
    language_path = Path(args.language_audit)
    if language_path.is_file():
        language_frame = pd.read_csv(language_path, dtype=str, keep_default_na=False)
        language_audit = {
            clean(row.get("doi", "")).lower(): row
            for row in language_frame.to_dict("records")
            if clean(row.get("doi", ""))
        }
    queue = build_queue(
        worklist,
        ranked,
        host_pass=host_pass,
        pass3=pass3,
        technical_retry=technical,
        language_audit=language_audit,
    )
    summary = build_host_summary(queue)
    scout = build_pattern_scout(queue, summary, max_hosts=args.max_scout_hosts, examples_per_host=args.examples_per_host)
    outputs = {"queue": Path(args.output_queue), "host_summary": Path(args.output_host_summary),
               "scout": Path(args.output_scout), "scout_html": Path(args.output_scout_html), "report": Path(args.report_json)}
    for key in ("queue", "host_summary", "scout"):
        outputs[key].parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(outputs["queue"], index=False); summary.to_csv(outputs["host_summary"], index=False)
    scout.to_csv(outputs["scout"], index=False); write_scout_html(outputs["scout_html"], scout)
    report = {
        "schema_version": "manual_pdf_recovery_priority_report_v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": {"scope": "current download_known_pdf worklist only",
                   "unresolved_failures": "retrieval provenance only; not candidate-paper access or eligibility decisions",
                   "acceptance_gate": "validate PDF bytes, DOI/title identity, and publication format before canonical import"},
        "counts": {"queue_rows": len(queue), "oa_positive_rows": int(queue.apply(lambda r: oa_positive(r.to_dict()), axis=1).sum()) if len(queue) else 0,
                   "probable_pdf_rows": int(queue["route_type"].eq("probable_pdf_url").sum()) if len(queue) else 0,
                   "host_patterns": len(summary), "scout_rows": len(scout),
                   "priority_groups": dict(Counter(queue.get("priority_group", pd.Series(dtype=str)).astype(str))),
                   "oa_statuses": dict(Counter(queue.get("open_access_status", pd.Series(dtype=str)).astype(str))),
                   "prior_failures": dict(Counter(queue.get("prior_download_failure", pd.Series(dtype=str)).astype(str)))},
        "outputs": {key: str(path.resolve()) for key, path in outputs.items() if key != "report"},
    }
    outputs["report"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
