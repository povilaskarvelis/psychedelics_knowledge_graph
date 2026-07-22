#!/usr/bin/env python3
"""Audit provider-only paper funding enrichment as a complete scope census."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.funding_metadata import (  # noqa: E402
    ASSERTION_COLUMNS,
    ATTEMPT_COLUMNS,
    FUNDING_ASSERTION_SCHEMA_VERSION,
    FUNDING_ATTEMPT_SCHEMA_VERSION,
    TERMINAL_ATTEMPT_STATUSES,
    assertion_identity,
    payload_sha256,
)
from pipeline.ingest.metadata_utils import normalize_doi  # noqa: E402


DEFAULT_ASSERTIONS = ROOT / "data" / "processed" / "corpus" / "paper_funding.parquet"
DEFAULT_ATTEMPTS = (
    ROOT / "data" / "processed" / "corpus" / "paper_funding_provider_attempts.parquet"
)
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PROVIDERS = ("openalex", "pubmed", "crossref")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def normalize_doi_value(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def nonblank(value: object) -> bool:
    return clean(value).lower() not in {"", "[]", "{}", "nan", "none", "null"}


def normalized_term(value: object) -> str:
    return " ".join(clean(value).casefold().split())


def load_table(path: Path, required: tuple[str, ...]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")
    return frame.copy()


def latest_attempts(attempts: pd.DataFrame) -> pd.DataFrame:
    frame = attempts.copy()
    frame["doi"] = frame["doi"].map(normalize_doi_value)
    frame["provider"] = frame["provider"].map(lambda value: clean(value).lower())
    frame["_retrieved_at"] = pd.to_datetime(frame["retrieved_at_utc"], utc=True, errors="coerce")
    frame["_source_order"] = range(len(frame))
    frame = frame.sort_values(
        ["doi", "provider", "_retrieved_at", "_source_order"],
        kind="stable",
        na_position="first",
    )
    return frame.drop_duplicates(["doi", "provider"], keep="last").drop(
        columns=["_retrieved_at", "_source_order"]
    )


def paper_value_sets(
    assertions: pd.DataFrame, column: str, providers: tuple[str, ...] | None = None
) -> dict[str, set[str]]:
    frame = assertions
    if providers is not None:
        frame = frame.loc[frame["provider"].isin(providers)]
    out: dict[str, set[str]] = {}
    for doi, value in frame.loc[frame[column].map(nonblank), ["doi", column]].itertuples(
        index=False, name=None
    ):
        out.setdefault(doi, set()).add(normalized_term(value))
    return out


def pairwise_overlap(
    positive_by_provider: dict[str, set[str]],
    assertions: pd.DataFrame,
    left: str,
    right: str,
) -> dict:
    shared_positive = positive_by_provider[left] & positive_by_provider[right]
    left_names = paper_value_sets(assertions, "funder_name", (left,))
    right_names = paper_value_sets(assertions, "funder_name", (right,))
    left_awards = paper_value_sets(assertions, "award_id", (left,))
    right_awards = paper_value_sets(assertions, "award_id", (right,))
    name_matches = sum(
        bool(left_names.get(doi, set()) & right_names.get(doi, set())) for doi in shared_positive
    )
    award_matches = sum(
        bool(left_awards.get(doi, set()) & right_awards.get(doi, set())) for doi in shared_positive
    )
    return {
        "papers_positive_in_both": len(shared_positive),
        "papers_with_exact_normalized_funder_name_overlap": name_matches,
        "papers_with_exact_normalized_award_id_overlap": award_matches,
    }


def top_funder_names(assertions: pd.DataFrame, limit: int) -> list[dict]:
    frame = assertions.loc[assertions["funder_name"].map(nonblank), ["doi", "funder_name"]].copy()
    frame["normalized_name"] = frame["funder_name"].map(normalized_term)
    frame = frame.drop_duplicates(["doi", "normalized_name"])
    counts = Counter(frame["normalized_name"])
    display = (
        frame.drop_duplicates("normalized_name")
        .set_index("normalized_name")["funder_name"]
        .to_dict()
    )
    return [
        {"funder_name": display[name], "papers": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def audit(
    *,
    scope_path: Path,
    assertions_path: Path,
    attempts_path: Path,
    candidates_path: Path,
    providers: tuple[str, ...],
    top_n: int,
) -> dict:
    scope = load_table(scope_path, ("doi",))
    assertions = load_table(assertions_path, ASSERTION_COLUMNS)
    attempts = load_table(attempts_path, ATTEMPT_COLUMNS)
    candidates = load_table(candidates_path, ("doi", "funders", "grant_ids"))

    scope["doi"] = scope["doi"].map(normalize_doi_value)
    assertions["doi"] = assertions["doi"].map(normalize_doi_value)
    assertions["provider"] = assertions["provider"].map(lambda value: clean(value).lower())
    candidates["doi"] = candidates["doi"].map(normalize_doi_value)
    scope_dois = set(scope["doi"])
    duplicate_scope_dois = int(scope["doi"].duplicated().sum())

    latest = latest_attempts(attempts)
    expected_pairs = {(doi, provider) for doi in scope_dois for provider in providers}
    latest_pairs = set(zip(latest["doi"], latest["provider"], strict=False))
    missing_pairs = sorted(expected_pairs - latest_pairs)
    unexpected_pairs = sorted(latest_pairs - expected_pairs)
    latest_in_scope = latest.loc[
        latest.apply(lambda row: (row["doi"], row["provider"]) in expected_pairs, axis=1)
    ].copy()

    status_by_provider: dict[str, dict[str, int]] = {}
    positive_by_provider: dict[str, set[str]] = {}
    provider_coverage: dict[str, dict] = {}
    persistent_id_columns = ("funder_openalex_id", "funder_ror_id", "funder_crossref_id")
    award_columns = ("award_id", "award_name", "award_openalex_id", "award_doi")
    for provider in providers:
        provider_attempts = latest_in_scope.loc[latest_in_scope["provider"].eq(provider)]
        statuses = provider_attempts["result_status"].value_counts().to_dict()
        status_by_provider[provider] = {str(key): int(value) for key, value in statuses.items()}
        positive = set(
            provider_attempts.loc[
                provider_attempts["result_status"].eq("funding_found"), "doi"
            ]
        )
        positive_by_provider[provider] = positive
        provider_rows = assertions.loc[
            assertions["provider"].eq(provider) & assertions["doi"].isin(scope_dois)
        ]
        funder_name_papers = set(provider_rows.loc[provider_rows["funder_name"].map(nonblank), "doi"])
        award_id_papers = set(provider_rows.loc[provider_rows["award_id"].map(nonblank), "doi"])
        persistent_id_papers = set(
            provider_rows.loc[
                provider_rows.loc[:, persistent_id_columns].apply(
                    lambda row: any(nonblank(value) for value in row), axis=1
                ),
                "doi",
            ]
        )
        any_award_papers = set(
            provider_rows.loc[
                provider_rows.loc[:, award_columns].apply(
                    lambda row: any(nonblank(value) for value in row), axis=1
                ),
                "doi",
            ]
        )
        found = int(provider_attempts["result_status"].isin({"funding_found", "no_funding_metadata"}).sum())
        provider_coverage[provider] = {
            "papers_queried": len(provider_attempts),
            "provider_records_found": found,
            "provider_record_found_percent": percent(found, len(scope_dois)),
            "papers_with_funding": len(positive),
            "papers_with_funding_percent": percent(len(positive), len(scope_dois)),
            "assertion_rows": len(provider_rows),
            "papers_with_funder_name": len(funder_name_papers),
            "papers_with_persistent_funder_id": len(persistent_id_papers),
            "papers_with_any_award_metadata": len(any_award_papers),
            "papers_with_award_id": len(award_id_papers),
            "unique_normalized_funder_names": int(
                provider_rows.loc[provider_rows["funder_name"].map(nonblank), "funder_name"]
                .map(normalized_term)
                .nunique()
            ),
            "unique_normalized_award_ids": int(
                provider_rows.loc[provider_rows["award_id"].map(nonblank), "award_id"]
                .map(normalized_term)
                .nunique()
            ),
        }

    any_positive = set().union(*positive_by_provider.values())
    signatures: Counter[str] = Counter()
    for doi in scope_dois:
        signature = "+".join(
            provider for provider in providers if doi in positive_by_provider[provider]
        )
        signatures[signature or "none"] += 1

    assertions_in_scope = assertions.loc[assertions["doi"].isin(scope_dois)].copy()
    papers_with_award_id = set(
        assertions_in_scope.loc[assertions_in_scope["award_id"].map(nonblank), "doi"]
    )
    papers_with_funder_name = set(
        assertions_in_scope.loc[assertions_in_scope["funder_name"].map(nonblank), "doi"]
    )
    papers_with_persistent_id = set(
        assertions_in_scope.loc[
            assertions_in_scope.loc[:, persistent_id_columns].apply(
                lambda row: any(nonblank(value) for value in row), axis=1
            ),
            "doi",
        ]
    )

    assertion_counts = assertions_in_scope.groupby(["doi", "provider"]).size().to_dict()
    count_mismatches: list[dict] = []
    positive_without_assertions: list[dict] = []
    assertions_without_positive: list[dict] = []
    for row in latest_in_scope.to_dict("records"):
        key = (row["doi"], row["provider"])
        actual = int(assertion_counts.get(key, 0))
        try:
            reported = int(clean(row.get("funding_assertion_count", "")) or 0)
        except ValueError:
            reported = -1
        if actual != reported:
            count_mismatches.append(
                {"doi": row["doi"], "provider": row["provider"], "reported": reported, "actual": actual}
            )
        if row["result_status"] == "funding_found" and actual == 0:
            positive_without_assertions.append({"doi": row["doi"], "provider": row["provider"]})
        if row["result_status"] != "funding_found" and actual:
            assertions_without_positive.append({"doi": row["doi"], "provider": row["provider"]})

    payload_hash_mismatches: list[dict] = []
    invalid_payload_json: list[dict] = []
    for row in attempts.to_dict("records"):
        try:
            payload = json.loads(clean(row.get("source_payload_json", "")) or "{}")
        except json.JSONDecodeError:
            invalid_payload_json.append(
                {"doi": normalize_doi_value(row.get("doi", "")), "provider": clean(row.get("provider", ""))}
            )
            continue
        expected_hash = payload_sha256(payload)
        if expected_hash != clean(row.get("source_payload_sha256", "")):
            payload_hash_mismatches.append(
                {"doi": normalize_doi_value(row.get("doi", "")), "provider": clean(row.get("provider", ""))}
            )

    assertion_key_mismatches = int(
        sum(assertion_identity(row) != clean(row.get("assertion_key", "")) for row in assertions.to_dict("records"))
    )
    latest_by_pair = {
        (row["doi"], row["provider"]): row for row in latest_in_scope.to_dict("records")
    }
    assertion_provenance_mismatches: list[dict] = []
    provenance_fields = (
        "provider_record_id",
        "retrieval_run_id",
        "retrieved_at_utc",
        "source_payload_sha256",
    )
    for row in assertions_in_scope.to_dict("records"):
        latest_row = latest_by_pair.get((row["doi"], row["provider"]), {})
        mismatched_fields = [
            field
            for field in provenance_fields
            if clean(row.get(field, "")) != clean(latest_row.get(field, ""))
        ]
        if mismatched_fields:
            assertion_provenance_mismatches.append(
                {
                    "doi": row["doi"],
                    "provider": row["provider"],
                    "fields": mismatched_fields,
                }
            )

    scoped_candidates = candidates.loc[candidates["doi"].isin(scope_dois)].drop_duplicates("doi")
    legacy_funder_papers = set(
        scoped_candidates.loc[scoped_candidates["funders"].map(nonblank), "doi"]
    )
    legacy_grant_papers = set(
        scoped_candidates.loc[scoped_candidates["grant_ids"].map(nonblank), "doi"]
    )

    latest_error_rows = latest_in_scope.loc[latest_in_scope["result_status"].eq("error")]
    nonterminal_rows = latest_in_scope.loc[
        ~latest_in_scope["result_status"].isin(TERMINAL_ATTEMPT_STATUSES)
    ]
    duplicate_assertion_keys = int(assertions["assertion_key"].duplicated().sum())
    history_pair_counts = attempts.assign(
        doi=attempts["doi"].map(normalize_doi_value),
        provider=attempts["provider"].map(lambda value: clean(value).lower()),
    ).groupby(["doi", "provider"]).size()

    integrity_checks = {
        "scope_dois_unique": duplicate_scope_dois == 0,
        "provider_matrix_complete": not missing_pairs and not unexpected_pairs,
        "all_latest_attempts_terminal": nonterminal_rows.empty,
        "no_latest_provider_errors": latest_error_rows.empty,
        "assertion_keys_unique": duplicate_assertion_keys == 0,
        "assertion_keys_recompute": assertion_key_mismatches == 0,
        "assertion_schema_version_valid": bool(
            assertions["schema_version"].eq(FUNDING_ASSERTION_SCHEMA_VERSION).all()
        ),
        "attempt_schema_version_valid": bool(
            attempts["schema_version"].eq(FUNDING_ATTEMPT_SCHEMA_VERSION).all()
        ),
        "assertion_timestamps_valid": bool(
            pd.to_datetime(assertions["retrieved_at_utc"], utc=True, errors="coerce")
            .notna()
            .all()
        ),
        "attempt_timestamps_valid": bool(
            pd.to_datetime(attempts["retrieved_at_utc"], utc=True, errors="coerce")
            .notna()
            .all()
        ),
        "assertion_provenance_matches_latest_attempt": not assertion_provenance_mismatches,
        "all_assertions_within_scope": bool(assertions["doi"].isin(scope_dois).all()),
        "all_assertion_providers_expected": bool(assertions["provider"].isin(providers).all()),
        "attempt_payload_hashes_valid": not payload_hash_mismatches and not invalid_payload_json,
        "attempt_assertion_counts_match": not count_mismatches,
        "positive_attempts_have_assertions": not positive_without_assertions,
        "nonpositive_attempts_have_no_assertions": not assertions_without_positive,
    }

    pairwise: dict[str, dict] = {}
    for index, left in enumerate(providers):
        for right in providers[index + 1 :]:
            pairwise[f"{left}+{right}"] = pairwise_overlap(
                positive_by_provider, assertions_in_scope, left, right
            )

    return {
        "schema_version": "paper_funding_audit_v1",
        "generated_at_utc": now_utc(),
        "analysis_design": "Complete census of the frozen screened-in DOI scope; no inferential tests.",
        "inputs": {
            "scope": str(scope_path),
            "assertions": str(assertions_path),
            "attempts": str(attempts_path),
            "candidates_legacy_comparison_only": str(candidates_path),
            "providers": list(providers),
        },
        "census": {
            "scope_papers": len(scope_dois),
            "expected_provider_pairs": len(expected_pairs),
            "latest_provider_pairs": len(latest_pairs & expected_pairs),
            "attempt_history_rows": len(attempts),
            "provider_pairs_with_retries": int((history_pair_counts > 1).sum()),
            "extra_retry_attempt_rows": int((history_pair_counts - 1).clip(lower=0).sum()),
            "funding_assertion_rows": len(assertions),
            "papers_with_any_provider_funding": len(any_positive),
            "papers_with_any_provider_funding_percent": percent(len(any_positive), len(scope_dois)),
            "papers_with_funder_name": len(papers_with_funder_name),
            "papers_with_persistent_funder_id": len(papers_with_persistent_id),
            "papers_with_award_id": len(papers_with_award_id),
        },
        "latest_status_by_provider": status_by_provider,
        "provider_coverage": provider_coverage,
        "provider_positive_overlap": dict(sorted(signatures.items())),
        "pairwise_exact_value_overlap": pairwise,
        "legacy_candidate_comparison": {
            "legacy_funders_present": len(legacy_funder_papers),
            "legacy_grant_ids_present": len(legacy_grant_papers),
            "provider_funding_positive_legacy_funders_blank": len(any_positive - legacy_funder_papers),
            "legacy_funders_positive_recovered_by_providers": len(any_positive & legacy_funder_papers),
            "legacy_funders_positive_not_recovered_by_providers": len(legacy_funder_papers - any_positive),
            "provider_award_id_positive_legacy_grant_ids_blank": len(papers_with_award_id - legacy_grant_papers),
            "legacy_grant_ids_positive_recovered_by_providers": len(papers_with_award_id & legacy_grant_papers),
            "legacy_grant_ids_positive_not_recovered_by_providers": len(legacy_grant_papers - papers_with_award_id),
            "note": "Legacy columns are used only for post hoc coverage comparison, never as enrichment evidence.",
        },
        "top_raw_provider_reported_funder_names": top_funder_names(assertions_in_scope, top_n),
        "integrity_checks": integrity_checks,
        "integrity_issue_counts": {
            "duplicate_scope_dois": duplicate_scope_dois,
            "missing_provider_pairs": len(missing_pairs),
            "unexpected_provider_pairs": len(unexpected_pairs),
            "latest_error_rows": len(latest_error_rows),
            "latest_nonterminal_rows": len(nonterminal_rows),
            "duplicate_assertion_keys": duplicate_assertion_keys,
            "assertion_key_mismatches": assertion_key_mismatches,
            "invalid_assertion_schema_versions": int(
                (~assertions["schema_version"].eq(FUNDING_ASSERTION_SCHEMA_VERSION)).sum()
            ),
            "invalid_attempt_schema_versions": int(
                (~attempts["schema_version"].eq(FUNDING_ATTEMPT_SCHEMA_VERSION)).sum()
            ),
            "invalid_assertion_timestamps": int(
                pd.to_datetime(assertions["retrieved_at_utc"], utc=True, errors="coerce")
                .isna()
                .sum()
            ),
            "invalid_attempt_timestamps": int(
                pd.to_datetime(attempts["retrieved_at_utc"], utc=True, errors="coerce")
                .isna()
                .sum()
            ),
            "assertion_provenance_mismatches": len(assertion_provenance_mismatches),
            "assertions_outside_scope": int((~assertions["doi"].isin(scope_dois)).sum()),
            "assertions_from_unexpected_providers": int((~assertions["provider"].isin(providers)).sum()),
            "invalid_attempt_payload_json": len(invalid_payload_json),
            "attempt_payload_hash_mismatches": len(payload_hash_mismatches),
            "attempt_assertion_count_mismatches": len(count_mismatches),
            "positive_attempts_without_assertions": len(positive_without_assertions),
            "nonpositive_attempts_with_assertions": len(assertions_without_positive),
        },
        "integrity_issue_examples": {
            "missing_provider_pairs": missing_pairs[:10],
            "unexpected_provider_pairs": unexpected_pairs[:10],
            "attempt_assertion_count_mismatches": count_mismatches[:10],
            "payload_hash_mismatches": payload_hash_mismatches[:10],
            "assertion_provenance_mismatches": assertion_provenance_mismatches[:10],
        },
        "audit_passed": bool(all(integrity_checks.values())),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        required=True,
        help="Frozen scope.parquet from the funding enrichment run being audited.",
    )
    parser.add_argument("--assertions", default=str(DEFAULT_ASSERTIONS))
    parser.add_argument("--attempts", default=str(DEFAULT_ATTEMPTS))
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS))
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    providers = tuple(value.strip().lower() for value in args.providers.split(",") if value.strip())
    report = audit(
        scope_path=Path(args.scope).resolve(),
        assertions_path=Path(args.assertions).resolve(),
        attempts_path=Path(args.attempts).resolve(),
        candidates_path=Path(args.candidates).resolve(),
        providers=providers,
        top_n=max(0, args.top_n),
    )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
