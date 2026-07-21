#!/usr/bin/env python3
"""Rank the manual PDF download queue by value and recoverability."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
DEFAULT_OUTPUT_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_ranked.csv"
DEFAULT_OUTPUT_TXT = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_ranked.txt"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_ranked_report.json"
DEFAULT_BROWSER_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_browser_recovery_candidates.csv"
DEFAULT_DOI_ARTICLE_CSV = (
    ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_doi_article_recovery_candidates.csv"
)
DEFAULT_PREPRINT_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_preprint_review_candidates.csv"

TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}
PRIORITY_COLUMNS = [
    "manual_priority_tier",
    "manual_priority_score",
    "manual_value_score",
    "manual_recoverability_score",
    "manual_host_class",
    "manual_browser_recovery_candidate",
    "manual_browser_recovery_hint",
    "manual_doi_article_recovery_candidate",
    "manual_doi_article_recovery_hint",
    "manual_doi_landing_url",
    "manual_preprint_like",
    "manual_preprint_review_hint",
    "manual_priority_reason",
]
REPOSITORY_HOST_MARKERS = (
    "biorxiv.org",
    "medrxiv.org",
    "osf.io",
    "psyarxiv",
    "figshare",
    "zenodo",
    "archive.org",
    "researchsquare",
    "preprints.org",
    "escholarship.org",
    "ncbi.nlm.nih.gov",
    "europepmc",
    "ebi.ac.uk",
    "repository",
    "eprints",
    "scholarworks",
    "openrepository",
)
INSTITUTIONAL_HOST_MARKERS = (
    ".edu",
    ".ac.",
    "harvard",
    "cambridge",
    "oxford",
    "sussex",
    "curtin",
    "monash",
    "qut",
    "unimelb",
)
PUBLISHER_HOST_MARKERS = (
    "jamanetwork.com",
    "journals.sagepub.com",
    "onlinelibrary.wiley.com",
    "tandfonline.com",
    "sciencedirect.com",
    "elsevier",
    "springer",
    "nature.com",
    "akjournals.com",
    "degruyter.com",
    "cambridge.org",
    "oup.com",
)
UNTRUSTED_BROWSER_HOSTS = (
    "scholarhub.ui.ac.id",
)


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def split_pipe(value: object) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def unique_hosts(*values: object) -> list[str]:
    hosts: list[str] = []
    for value in values:
        for candidate in split_pipe(value):
            host = urlparse(candidate).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if host and host not in hosts:
                hosts.append(host)
    return hosts


def host_class(hosts: list[str]) -> str:
    joined = " ".join(hosts)
    if any(marker in joined for marker in REPOSITORY_HOST_MARKERS):
        return "repository_or_preprint"
    if any(marker in joined for marker in INSTITUTIONAL_HOST_MARKERS):
        return "institutional_repository"
    if any(marker in joined for marker in PUBLISHER_HOST_MARKERS):
        return "publisher_platform"
    if hosts:
        return "other_host"
    return "no_url_host"


def row_text(row: dict) -> str:
    return " ".join(
        clean(row.get(field, ""))
        for field in (
            "doi",
            "study_title",
            "study_journal",
            "publication_type",
            "best_pdf_url",
            "pdf_url_candidates",
            "open_access_url",
            "source_types",
        )
    ).lower()


def preprint_like(row: dict) -> bool:
    text = row_text(row)
    return any(
        marker in text
        for marker in (
            "biorxiv",
            "medrxiv",
            "psyarxiv",
            "osf.io",
            "osf preprints",
            "authorea",
            "chemrxiv",
            "research square",
            "researchsquare",
            "preprint",
            "10.1101/",
            "10.31234/",
            "10.22541/",
        )
    )


def browser_recovery_candidate(row: dict, hclass: str) -> tuple[bool, str]:
    failure = clean(row.get("pdf_download_failure_category", "")).lower()
    oa = clean(row.get("open_access_status", "")).lower()
    has_url = bool(
        clean(row.get("best_pdf_url", ""))
        or clean(row.get("pdf_url_candidates", ""))
        or clean(row.get("open_access_url", ""))
    )
    if not has_url:
        return False, "no URL to inspect"
    if failure not in {"forbidden", "non_pdf_response", "other_download_failure", "provider_error", "timeout"}:
        return False, f"failure={failure or 'unknown'} is lower-yield for browser recovery"
    if oa == "closed":
        return False, "closed-access metadata"
    if hclass in {"repository_or_preprint", "institutional_repository"}:
        return True, "repository/preprint page may expose a browser-only download path"
    if failure == "non_pdf_response":
        return True, "landing page may require article/full-text link, then PDF/download click-through"
    if failure == "other_download_failure":
        return True, "direct URL did not yield a PDF; browser navigation may expose the actual download control"
    if failure == "forbidden" and oa in {"gold", "green", "bronze", "diamond", "hybrid"}:
        return True, "direct PDF blocked; browser may expose article/full-text links or viewer download"
    if failure in {"provider_error", "timeout"} and oa in {"gold", "green", "diamond"}:
        return True, "provider failed direct request; browser retry may still work"
    return False, "lower-yield browser candidate"


def untrusted_browser_source(row: dict) -> str:
    hosts = unique_hosts(
        row.get("best_pdf_url", ""),
        row.get("pdf_url_candidates", ""),
        row.get("open_access_url", ""),
    )
    return next(
        (host for host in hosts if any(marker in host for marker in UNTRUSTED_BROWSER_HOSTS)),
        "",
    )


def suspected_nonarticle_record(row: dict) -> str:
    doi = clean(row.get("doi", "")).lower()
    title = clean(row.get("study_title", "")).lower()
    journal = clean(row.get("study_journal", "")).lower()
    publication_type = clean(row.get("publication_type", "")).lower()
    best_url = clean(row.get("best_pdf_url", "")).lower()
    if doi.startswith("10.5281/zenodo."):
        return "Zenodo deposit"
    if publication_type in {
        "conference-abstract",
        "conference abstract",
        "dissertation",
        "thesis",
        "dataset",
        "posted-content",
    }:
        return f"publication_type={publication_type}"
    if re.match(r"^\(\d{2,4}\)\s+", title):
        return "numbered conference/supplement abstract title"
    if re.match(r"^(?:ps|op|oc|poster)\s*0*\d+\b", title, flags=re.IGNORECASE):
        return "conference/supplement abstract title code"
    if any(marker in title for marker in ("conference abstract", "meeting abstract")):
        return "title identifies a conference abstract"
    if any(marker in title for marker in ("doctoral thesis", "phd thesis", "master's thesis", "master thesis")):
        return "title identifies a thesis"
    if any(marker in journal for marker in ("research repository", "institutional repository", "thesis repository")):
        return "journal/source identifies a repository record"
    if "thesis" in Path(urlparse(best_url).path).name.lower():
        return "PDF filename identifies a thesis"
    return ""


def doi_article_recovery_candidate(row: dict) -> tuple[bool, str, str]:
    doi = clean(row.get("doi", "")).lower()
    landing_url = f"https://doi.org/{doi}" if doi.startswith("10.") else ""
    if not landing_url:
        return False, "missing or invalid DOI", ""
    untrusted_host = untrusted_browser_source(row)
    if untrusted_host:
        return False, f"untrusted browser source host={untrusted_host}", landing_url
    nonarticle_reason = suspected_nonarticle_record(row)
    if nonarticle_reason:
        return False, nonarticle_reason, landing_url
    return (
        True,
        "open DOI landing page; require a matching journal-article page before following full-text/PDF/download controls",
        landing_url,
    )


def int_value(value: object) -> int:
    try:
        return int(float(clean(value) or 0))
    except ValueError:
        return 0


def extraction_value_score(row: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    route_count = int_value(row.get("route_count", 0))
    if route_count:
        add = min(route_count, 5) * 8
        score += add
        reasons.append(f"{route_count} extraction route(s)")

    text = " ".join(
        [
            clean(row.get("study_title", "")).lower(),
            clean(row.get("prompt_profiles", "")).lower(),
            clean(row.get("source_types", "")).lower(),
            clean(row.get("domain_routes", "")).lower(),
        ]
    )
    if any(term in text for term in ("meta_analysis", "meta-analysis", "systematic review", "structured_review")):
        score += 30
        reasons.append("secondary synthesis signal")
    if any(term in text for term in ("consensus", "guideline")):
        score += 24
        reasons.append("guideline/consensus signal")
    if "primary_clinical" in text or "clinical_outcome" in text:
        score += 18
        reasons.append("clinical outcome route")
    if any(term in text for term in ("brain_system", "molecular_target", "molecular_pathway", "cognitive_behavioral")):
        score += 16
        reasons.append("mechanism/domain route")
    if "safety" in text or "tolerability" in text:
        score += 10
        reasons.append("safety route")
    return score, reasons


def recoverability_score(row: dict) -> tuple[int, str, list[str]]:
    score = 0
    reasons: list[str] = []
    failure = clean(row.get("pdf_download_failure_category", "")).lower()
    oa = clean(row.get("open_access_status", "")).lower()
    hosts = unique_hosts(row.get("best_pdf_url", ""), row.get("pdf_url_candidates", ""), row.get("open_access_url", ""))
    hclass = host_class(hosts)

    failure_scores = {
        "non_pdf_response": 34,
        "forbidden": 24,
        "provider_error": 10,
        "timeout": 10,
        "other_download_failure": 8,
        "not_found": 2,
    }
    score += failure_scores.get(failure, 8)
    if failure:
        reasons.append(f"failure={failure}")

    oa_scores = {
        "gold": 24,
        "diamond": 24,
        "green": 20,
        "bronze": 14,
        "hybrid": 12,
        "closed": -12,
    }
    score += oa_scores.get(oa, 0)
    if oa:
        reasons.append(f"oa={oa}")

    host_scores = {
        "repository_or_preprint": 28,
        "institutional_repository": 24,
        "other_host": 12,
        "publisher_platform": 4,
        "no_url_host": -20,
    }
    score += host_scores[hclass]
    reasons.append(f"host_class={hclass}")

    if len(hosts) > 1:
        score += 6
        reasons.append("multiple URL hosts")
    if clean(row.get("pmcid", "")):
        score += 8
        reasons.append("PMCID present")
    if clean(row.get("pdf_download_retry_recommended", "")).lower() in {"true", "1", "yes"}:
        score -= 8
        reasons.append("already failed retryable pass")

    return score, hclass, reasons


def tier_for_scores(total_score: int, recoverability: int, value: int) -> str:
    if total_score >= 125 and recoverability >= 60:
        return "A"
    if total_score >= 100 and recoverability >= 50:
        return "B"
    if total_score >= 72 or value >= 60:
        return "C"
    return "D"


def rank_rows(df: pd.DataFrame) -> pd.DataFrame:
    ranked_rows: list[dict] = []
    for row in df.fillna("").to_dict("records"):
        value_score, value_reasons = extraction_value_score(row)
        recovery_score, hclass, recovery_reasons = recoverability_score(row)
        total_score = value_score + recovery_score
        tier = tier_for_scores(total_score, recovery_score, value_score)
        is_preprint = preprint_like(row)
        browser_candidate, browser_hint = browser_recovery_candidate(row, hclass)
        doi_article_candidate, doi_article_hint, doi_landing_url = doi_article_recovery_candidate(row)
        ranked = {
            **row,
            "manual_priority_tier": tier,
            "manual_priority_score": total_score,
            "manual_value_score": value_score,
            "manual_recoverability_score": recovery_score,
            "manual_host_class": hclass,
            "manual_browser_recovery_candidate": browser_candidate,
            "manual_browser_recovery_hint": browser_hint,
            "manual_doi_article_recovery_candidate": doi_article_candidate,
            "manual_doi_article_recovery_hint": doi_article_hint,
            "manual_doi_landing_url": doi_landing_url,
            "manual_preprint_like": is_preprint,
            "manual_preprint_review_hint": (
                "search title for a published article DOI; keep preprint only if no published duplicate is found"
                if is_preprint
                else ""
            ),
            "manual_priority_reason": "; ".join([*value_reasons, *recovery_reasons]),
        }
        ranked_rows.append(ranked)
    out = pd.DataFrame(ranked_rows)
    if out.empty:
        return pd.DataFrame(columns=PRIORITY_COLUMNS + [col for col in df.columns if col not in PRIORITY_COLUMNS])
    out["_tier_order"] = out["manual_priority_tier"].map(TIER_ORDER).fillna(99).astype(int)
    out = out.sort_values(
        ["_tier_order", "manual_priority_score", "manual_recoverability_score", "route_count", "doi"],
        ascending=[True, False, False, False, True],
    ).drop(columns=["_tier_order"])
    return out[PRIORITY_COLUMNS + [col for col in out.columns if col not in PRIORITY_COLUMNS]]


def write_outputs(
    ranked: pd.DataFrame,
    output_csv: Path,
    output_txt: Path,
    report_json: Path,
    browser_csv: Path,
    doi_article_csv: Path,
    preprint_csv: Path,
) -> dict:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(output_csv, index=False)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("\n".join(ranked.get("doi", pd.Series(dtype=str)).astype(str).tolist()) + ("\n" if len(ranked) else ""), encoding="utf-8")
    browser = ranked[ranked.get("manual_browser_recovery_candidate", pd.Series(dtype=bool)).astype(bool)].copy()
    doi_articles = ranked[
        ranked.get("manual_doi_article_recovery_candidate", pd.Series(dtype=bool)).astype(bool)
    ].copy()
    preprints = ranked[ranked.get("manual_preprint_like", pd.Series(dtype=bool)).astype(bool)].copy()
    browser_csv.parent.mkdir(parents=True, exist_ok=True)
    doi_article_csv.parent.mkdir(parents=True, exist_ok=True)
    preprint_csv.parent.mkdir(parents=True, exist_ok=True)
    browser.to_csv(browser_csv, index=False)
    doi_articles.to_csv(doi_article_csv, index=False)
    preprints.to_csv(preprint_csv, index=False)
    report = {
        "input_rows": int(len(ranked)),
        "output_csv": str(output_csv.resolve()),
        "output_txt": str(output_txt.resolve()),
        "browser_recovery_csv": str(browser_csv.resolve()),
        "doi_article_recovery_csv": str(doi_article_csv.resolve()),
        "preprint_review_csv": str(preprint_csv.resolve()),
        "tier_counts": dict(Counter(ranked.get("manual_priority_tier", pd.Series(dtype=str)).astype(str))),
        "failure_category_counts": dict(Counter(ranked.get("pdf_download_failure_category", pd.Series(dtype=str)).astype(str))),
        "host_class_counts": dict(Counter(ranked.get("manual_host_class", pd.Series(dtype=str)).astype(str))),
        "browser_recovery_candidate_rows": int(len(browser)),
        "doi_article_recovery_candidate_rows": int(len(doi_articles)),
        "preprint_like_rows": int(len(preprints)),
        "browser_recovery_tier_counts": dict(Counter(browser.get("manual_priority_tier", pd.Series(dtype=str)).astype(str))),
        "preprint_like_tier_counts": dict(Counter(preprints.get("manual_priority_tier", pd.Series(dtype=str)).astype(str))),
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-txt", default=str(DEFAULT_OUTPUT_TXT))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--browser-recovery-csv", default=str(DEFAULT_BROWSER_CSV))
    parser.add_argument("--doi-article-recovery-csv", default=str(DEFAULT_DOI_ARTICLE_CSV))
    parser.add_argument("--preprint-review-csv", default=str(DEFAULT_PREPRINT_CSV))
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    input_csv = Path(args.input_csv).resolve()
    if not input_csv.exists():
        raise FileNotFoundError(f"Manual PDF queue not found: {input_csv}")
    ranked = rank_rows(pd.read_csv(input_csv))
    report = write_outputs(
        ranked,
        Path(args.output_csv).resolve(),
        Path(args.output_txt).resolve(),
        Path(args.report_json).resolve(),
        Path(args.browser_recovery_csv).resolve(),
        Path(args.doi_article_recovery_csv).resolve(),
        Path(args.preprint_review_csv).resolve(),
    )
    print(f"RANKED_MANUAL_PDF_QUEUE: rows={len(ranked):,} tiers={report['tier_counts']} csv={report['output_csv']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
