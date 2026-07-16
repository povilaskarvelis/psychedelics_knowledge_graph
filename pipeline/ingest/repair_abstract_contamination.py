#!/usr/bin/env python3
"""Audit and repair full text or container text stored as paper abstracts.

The command is safe to resume with the same run ID.  It first preserves the
affected canonical rows in the run directory, then tries provider recovery in
batched order.  A recovered value must pass the same abstract-quality policy
used by discovery promotion.  Unresolved contaminated fields are blanked so
that deterministic pre-screening can route them as having no usable abstract.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.abstract_quality import (  # noqa: E402
    assess_abstract,
    best_valid_abstract,
    clean_text,
    extract_embedded_abstract,
    normalize_provider,
)
from pipeline.ingest.enrich_paper_metadata import (  # noqa: E402
    OUTPUT_COLUMNS,
    candidate_metadata_row,
    merge_rows,
    merged_output_rows,
    read_table,
    write_table,
)
from pipeline.ingest.metadata_utils import (  # noqa: E402
    PAPER_METADATA_SCHEMA_VERSION,
    load_config,
    normalize_doi,
    read_float,
    read_int,
)
from pipeline.ingest.run_batch_abstract_enrichment import (  # noqa: E402
    RESULT_COLUMNS,
    BatchHttpClient,
    atomic_write_json,
    atomic_write_parquet,
    now_utc,
    run_crossref_batches,
    run_pmc_batches,
    run_pubmed_batches,
    run_semantic_scholar_batches,
)


DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_RUNS_DIR = ROOT / "data" / "processed" / "corpus" / "metadata_enrichment_runs"
DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.yaml"
MANIFEST_SCHEMA = "abstract_contamination_repair_v1"


def default_run_id() -> str:
    return "abstract_contamination_repair_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalized_doi(value: Any) -> str:
    return normalize_doi(clean(value)).lower()


def append_pipe_token(raw: Any, token: str) -> str:
    values = [part.strip() for part in clean(raw).split("|") if part.strip()]
    if token and token not in values:
        values.append(token)
    return "|".join(values)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_doi_scope(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(path)
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalized_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def candidate_abstract_provider(row: dict, metadata: dict | None = None) -> str:
    metadata = metadata or {}
    candidate_abstract = clean_text(row.get("abstract", ""))
    metadata_abstract = clean_text(metadata.get("abstract", ""))
    metadata_provider = clean(metadata.get("metadata_provider", ""))
    if candidate_abstract and candidate_abstract == metadata_abstract and metadata_provider:
        return metadata_provider
    discovery_providers = clean(row.get("discovery_providers", ""))
    if discovery_providers:
        return discovery_providers
    return clean(row.get("metadata_provider", "")) or "candidate"


def build_contamination_scope(
    candidates_path: Path,
    metadata_path: Path,
    *,
    allowed_dois: set[str] | None,
) -> pd.DataFrame:
    candidates = pd.read_parquet(candidates_path)
    if "doi" not in candidates.columns:
        raise ValueError(f"Candidate table has no DOI column: {candidates_path}")
    candidate_rows = {
        normalized_doi(row.get("doi")): row
        for row in candidates.to_dict("records")
        if normalized_doi(row.get("doi"))
    }
    metadata_rows = {
        normalized_doi(row.get("doi")): row
        for row in read_table(metadata_path)
        if normalized_doi(row.get("doi"))
    }

    rows: list[dict] = []
    for doi, candidate in candidate_rows.items():
        if allowed_dois is not None and doi not in allowed_dois:
            continue
        metadata = metadata_rows.get(doi, {})
        title = clean(metadata.get("study_title", "")) or clean(candidate.get("study_title", ""))
        candidate_abstract = clean_text(candidate.get("abstract", ""))
        metadata_abstract = clean_text(metadata.get("abstract", ""))
        candidate_provider = candidate_abstract_provider(candidate, metadata)
        metadata_provider = clean(metadata.get("metadata_provider", "")) or "metadata"
        candidate_quality = assess_abstract(
            candidate_abstract,
            provider=candidate_provider,
            title=title,
        )
        metadata_quality = assess_abstract(
            metadata_abstract,
            provider=metadata_provider,
            title=title,
        )
        if candidate_quality.status != "contaminated" and metadata_quality.status != "contaminated":
            continue

        local_rows = []
        if candidate_quality.usable:
            local_rows.append(
                {
                    "provider": normalize_provider(candidate_provider),
                    "abstract": candidate_abstract,
                    "title": title,
                    "source": "candidate",
                }
            )
        if metadata_quality.usable:
            local_rows.append(
                {
                    "provider": normalize_provider(metadata_provider),
                    "abstract": metadata_abstract,
                    "title": title,
                    "source": "metadata",
                }
            )
        local_replacement = best_valid_abstract(local_rows)
        rows.append(
            {
                "doi": doi,
                "study_title": title,
                "study_year": clean(metadata.get("study_year", "")) or clean(candidate.get("study_year", "")),
                "pmid": clean(metadata.get("pmid", "")) or clean(candidate.get("pmid", "")),
                "pmcid": clean(metadata.get("pmcid", "")) or clean(candidate.get("pmcid", "")),
                "candidate_provider": candidate_provider,
                "candidate_abstract": candidate_abstract,
                "candidate_char_count": len(candidate_abstract),
                "candidate_quality": candidate_quality.status,
                "candidate_reasons": "|".join(candidate_quality.reasons),
                "metadata_provider": metadata_provider,
                "metadata_abstract": metadata_abstract,
                "metadata_char_count": len(metadata_abstract),
                "metadata_quality": metadata_quality.status,
                "metadata_reasons": "|".join(metadata_quality.reasons),
                "local_replacement_provider": clean(local_replacement.get("provider", "")) if local_replacement else "",
                "local_replacement_source": clean(local_replacement.get("source", "")) if local_replacement else "",
                "local_replacement_abstract": clean(local_replacement.get("abstract", "")) if local_replacement else "",
                "recovery_required": local_replacement is None,
            }
        )
    return pd.DataFrame(rows).sort_values("doi", kind="stable").reset_index(drop=True) if rows else pd.DataFrame(
        columns=[
            "doi",
            "study_title",
            "study_year",
            "pmid",
            "pmcid",
            "candidate_provider",
            "candidate_abstract",
            "candidate_char_count",
            "candidate_quality",
            "candidate_reasons",
            "metadata_provider",
            "metadata_abstract",
            "metadata_char_count",
            "metadata_quality",
            "metadata_reasons",
            "local_replacement_provider",
            "local_replacement_source",
            "local_replacement_abstract",
            "recovery_required",
        ]
    )


def valid_recovered_rows(results: Sequence[dict], scope: pd.DataFrame) -> tuple[dict[str, dict], list[dict]]:
    title_by_doi = dict(zip(scope["doi"], scope["study_title"])) if not scope.empty else {}
    accepted_candidates: list[dict] = []
    rejected: list[dict] = []
    for raw in results:
        row = dict(raw)
        doi = normalized_doi(row.get("doi"))
        abstract = clean_text(row.get("abstract", ""))
        if clean(row.get("status", "")) != "recovered" or not abstract:
            continue
        quality = assess_abstract(
            abstract,
            provider=row.get("provider", ""),
            title=title_by_doi.get(doi, ""),
        )
        row["abstract"] = abstract
        row["title"] = title_by_doi.get(doi, "")
        if quality.usable:
            accepted_candidates.append(row)
        else:
            rejected.append(
                {
                    "doi": doi,
                    "provider": clean(row.get("provider", "")),
                    "char_count": len(abstract),
                    "reasons": "|".join(quality.reasons),
                }
            )

    grouped: dict[str, list[dict]] = {}
    for row in accepted_candidates:
        grouped.setdefault(normalized_doi(row.get("doi")), []).append(row)
    selected: dict[str, dict] = {}
    for doi, rows in grouped.items():
        choice = best_valid_abstract(rows)
        if choice is not None:
            selected[doi] = choice
    return selected, rejected


def scope_summary(scope: pd.DataFrame) -> dict:
    reasons = Counter()
    for column in ("candidate_reasons", "metadata_reasons"):
        if column not in scope.columns:
            continue
        for raw in scope[column].fillna(""):
            reasons.update(part for part in str(raw).split("|") if part)
    return {
        "records": int(len(scope)),
        "recovery_required": int(scope["recovery_required"].astype(bool).sum()) if not scope.empty else 0,
        "local_replacements": int(scope["local_replacement_abstract"].fillna("").astype(str).str.strip().ne("").sum()) if not scope.empty else 0,
        "candidate_contaminated": int(scope["candidate_quality"].eq("contaminated").sum()) if not scope.empty else 0,
        "metadata_contaminated": int(scope["metadata_quality"].eq("contaminated").sum()) if not scope.empty else 0,
        "by_reason": dict(sorted(reasons.items())),
    }


def salvaged_abstract_for_scope_row(scope_row: dict) -> dict | None:
    candidates: list[dict] = []
    title = clean(scope_row.get("study_title", ""))
    for source in ("metadata", "candidate"):
        if clean(scope_row.get(f"{source}_quality", "")) != "contaminated":
            continue
        extracted = extract_embedded_abstract(
            scope_row.get(f"{source}_abstract", ""),
            title=title,
        )
        if extracted is None:
            continue
        candidates.append(
            {
                "abstract": extracted.text,
                "source": source,
                "method": extracted.method,
                "boundary": extracted.boundary,
            }
        )
    if not candidates:
        return None
    method_priority = {"explicit_abstract_section": 0, "leading_summary_before_introduction": 1}
    return min(
        candidates,
        key=lambda item: (method_priority.get(item["method"], 99), len(item["abstract"]), item["source"]),
    )


def atomic_replace_candidate(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.stem + ".abstract_repair_tmp.parquet")
    frame.to_parquet(temporary, engine="pyarrow", index=False)
    temporary.replace(path)


def apply_repairs(
    *,
    candidates_path: Path,
    metadata_path: Path,
    scope: pd.DataFrame,
    recovered_by_doi: dict[str, dict],
    run_id: str,
    run_dir: Path,
) -> dict:
    candidates = pd.read_parquet(candidates_path)
    candidates["_doi_key"] = candidates["doi"].map(normalized_doi)
    candidate_index = {doi: index for index, doi in candidates["_doi_key"].items() if doi}
    existing_metadata_rows = read_table(metadata_path)
    existing_metadata = {
        normalized_doi(row.get("doi")): row
        for row in existing_metadata_rows
        if normalized_doi(row.get("doi"))
    }

    affected = set(scope["doi"])
    candidate_backup = run_dir / "pre_repair_candidate_rows.parquet"
    metadata_backup = run_dir / "pre_repair_metadata_rows.parquet"
    if not candidate_backup.exists():
        atomic_write_parquet(candidate_backup, candidates[candidates["_doi_key"].isin(affected)].drop(columns=["_doi_key"]))
    if not metadata_backup.exists():
        backup_rows = [row for doi, row in existing_metadata.items() if doi in affected]
        atomic_write_parquet(metadata_backup, pd.DataFrame(backup_rows, columns=list(OUTPUT_COLUMNS)))

    timestamp = now_utc()
    metadata_updates: dict[str, dict] = {}
    actions: list[dict] = []
    provider_counts: Counter[str] = Counter()
    for scope_row in scope.to_dict("records"):
        doi = normalized_doi(scope_row.get("doi"))
        index = candidate_index.get(doi)
        if index is None:
            raise ValueError(f"Repair scope DOI is missing from candidate table: {doi}")

        local_abstract = clean_text(scope_row.get("local_replacement_abstract", ""))
        recovered = recovered_by_doi.get(doi)
        salvaged = salvaged_abstract_for_scope_row(scope_row)
        if local_abstract:
            replacement_abstract = local_abstract
            replacement_provider = clean(scope_row.get("local_replacement_provider", "")) or "local_valid_field"
            action = "replaced_from_existing_valid_field"
        elif recovered:
            replacement_abstract = clean_text(recovered.get("abstract", ""))
            replacement_provider = normalize_provider(recovered.get("provider", ""))
            action = "recovered_from_provider"
        elif salvaged:
            replacement_abstract = clean_text(salvaged.get("abstract", ""))
            replacement_provider = "embedded_abstract_extraction"
            action = "extracted_identifiable_abstract_section"
        else:
            replacement_abstract = ""
            replacement_provider = ""
            action = "invalidated_unresolved_contamination"

        candidate_row = candidates.loc[index].drop(labels=["_doi_key"]).to_dict()
        existing = existing_metadata.get(doi, {})
        if replacement_abstract:
            candidates.at[index, "abstract"] = replacement_abstract
            for column, value in (
                ("metadata_provider", replacement_provider),
                ("metadata_provider_chain", append_pipe_token(candidate_row.get("metadata_provider_chain", ""), replacement_provider)),
                ("metadata_providers_queried", append_pipe_token(candidate_row.get("metadata_providers_queried", ""), replacement_provider)),
                ("metadata_lookup_error", ""),
                ("metadata_missing_reason", ""),
                ("metadata_enrichment_status", "enriched"),
                ("metadata_enrichment_run_id", run_id),
                ("metadata_enriched_at_utc", timestamp),
            ):
                if column in candidates.columns:
                    candidates.at[index, column] = value

            candidate_row["abstract"] = replacement_abstract
            base = merge_rows(existing, candidate_metadata_row(candidate_row))
            base["abstract"] = replacement_abstract
            base["metadata_provider"] = replacement_provider
            base["metadata_provider_chain"] = append_pipe_token(base.get("metadata_provider_chain", ""), replacement_provider)
            base["metadata_providers_queried"] = append_pipe_token(base.get("metadata_providers_queried", ""), replacement_provider)
            base["metadata_lookup_warnings"] = append_pipe_token(
                base.get("metadata_lookup_warnings", ""),
                "repaired_contaminated_abstract",
            )
            base["metadata_lookup_error"] = ""
            base["metadata_missing_reason"] = ""
            base["metadata_enrichment_status"] = "enriched"
            base["metadata_enrichment_run_id"] = run_id
            base["metadata_enriched_at_utc"] = timestamp
            base["paper_metadata_schema_version"] = PAPER_METADATA_SCHEMA_VERSION
            if replacement_provider == "semantic_scholar" and recovered:
                base["semantic_scholar_id"] = clean(recovered.get("provider_record_id", "")) or clean(base.get("semantic_scholar_id", ""))
            metadata_updates[doi] = {column: clean(base.get(column, "")) for column in OUTPUT_COLUMNS}
            provider_counts[replacement_provider] += 1
        else:
            if clean(scope_row.get("candidate_quality", "")) == "contaminated":
                candidates.at[index, "abstract"] = ""
            if "metadata_missing_reason" in candidates.columns:
                candidates.at[index, "metadata_missing_reason"] = "abstract_contamination_unresolved"
            if "metadata_enrichment_status" in candidates.columns:
                candidates.at[index, "metadata_enrichment_status"] = "abstract_unresolved"
            if "metadata_enrichment_run_id" in candidates.columns:
                candidates.at[index, "metadata_enrichment_run_id"] = run_id
            if "metadata_enriched_at_utc" in candidates.columns:
                candidates.at[index, "metadata_enriched_at_utc"] = timestamp
            if existing and clean(scope_row.get("metadata_quality", "")) == "contaminated":
                base = {column: clean(existing.get(column, "")) for column in OUTPUT_COLUMNS}
                base["abstract"] = ""
                base["metadata_lookup_warnings"] = append_pipe_token(
                    base.get("metadata_lookup_warnings", ""),
                    "invalidated_contaminated_abstract",
                )
                base["metadata_missing_reason"] = "abstract_contamination_unresolved"
                base["metadata_enrichment_status"] = "abstract_unresolved"
                base["metadata_enrichment_run_id"] = run_id
                base["metadata_enriched_at_utc"] = timestamp
                metadata_updates[doi] = base

        actions.append(
            {
                "doi": doi,
                "action": action,
                "replacement_provider": replacement_provider,
                "replacement_char_count": len(replacement_abstract),
                "candidate_reasons": clean(scope_row.get("candidate_reasons", "")),
                "metadata_reasons": clean(scope_row.get("metadata_reasons", "")),
                "extraction_source": clean(salvaged.get("source", "")) if salvaged else "",
                "extraction_method": clean(salvaged.get("method", "")) if salvaged else "",
                "extraction_boundary": clean(salvaged.get("boundary", "")) if salvaged else "",
            }
        )

    candidates = candidates.drop(columns=["_doi_key"])
    atomic_replace_candidate(candidates, candidates_path)
    if metadata_updates:
        merged_rows = merged_output_rows(metadata_updates, existing_metadata)
        temporary = metadata_path.with_name(metadata_path.stem + ".abstract_repair_tmp.parquet")
        write_table(temporary, merged_rows)
        temporary.replace(metadata_path)

    actions_path = run_dir / "abstract_repair_actions.parquet"
    atomic_write_parquet(actions_path, pd.DataFrame(actions))
    action_counts = Counter(row["action"] for row in actions)
    return {
        "schema_version": "abstract_contamination_apply_report_v1",
        "run_id": run_id,
        "applied_at_utc": timestamp,
        "scope_records": len(scope),
        "action_counts": dict(action_counts),
        "replacement_provider_counts": dict(provider_counts),
        "candidate_table": str(candidates_path),
        "candidate_table_sha256": sha256_file(candidates_path),
        "metadata_table": str(metadata_path),
        "metadata_table_sha256": sha256_file(metadata_path),
        "candidate_backup": str(candidate_backup),
        "metadata_backup": str(metadata_backup),
        "actions_table": str(actions_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--providers", default="pubmed,pmc,semantic_scholar,crossref")
    parser.add_argument("--pubmed-batch-size", type=int, default=200)
    parser.add_argument("--pmc-batch-size", type=int, default=50)
    parser.add_argument("--semantic-scholar-batch-size", type=int, default=500)
    parser.add_argument("--crossref-batch-size", type=int, default=100)
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--crossref-workers", type=int, default=3)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--no-apply", action="store_true")
    parser.add_argument(
        "--apply-existing-results",
        action="store_true",
        help="Reapply a completed run's preserved scope/results after improving deterministic repair logic.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    providers = [part.strip() for part in args.providers.split(",") if part.strip()]
    unknown = set(providers) - {"pubmed", "pmc", "semantic_scholar", "crossref"}
    if unknown:
        raise SystemExit(f"Unsupported providers: {', '.join(sorted(unknown))}")
    candidates_path = Path(args.candidate_table).resolve()
    metadata_path = Path(args.metadata_table).resolve()
    doi_path = Path(args.doi_file).resolve() if clean(args.doi_file) else None
    run_dir = Path(args.run_dir).resolve() if clean(args.run_dir) else (DEFAULT_RUNS_DIR / args.run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    scope_path = run_dir / "abstract_contamination_scope.parquet"
    manifest_path = run_dir / "run_manifest.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != MANIFEST_SCHEMA:
            raise ValueError(f"Unsupported run manifest: {manifest_path}")
        if manifest.get("status") == "complete" and not args.apply_existing_results:
            print(f"Run already complete: {manifest_path}", flush=True)
            return 0
        manifest.pop("error", None)
    else:
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "run_id": args.run_id,
            "status": "auditing",
            "created_at_utc": now_utc(),
            "updated_at_utc": now_utc(),
            "configuration": {
                "candidate_table": str(candidates_path),
                "metadata_table": str(metadata_path),
                "doi_file": str(doi_path) if doi_path else "",
                "providers": providers,
            },
        }
        atomic_write_json(manifest_path, manifest)

    if scope_path.exists():
        scope = pd.read_parquet(scope_path)
    else:
        scope = build_contamination_scope(
            candidates_path,
            metadata_path,
            allowed_dois=load_doi_scope(doi_path),
        )
        atomic_write_parquet(scope_path, scope)
    manifest["scope"] = scope_summary(scope)
    manifest["scope_table"] = str(scope_path)
    manifest["updated_at_utc"] = now_utc()
    manifest["status"] = "audit_complete" if args.audit_only else "recovering"
    atomic_write_json(manifest_path, manifest)

    summary = manifest["scope"]
    print(f"Contaminated DOI records: {summary['records']:,}", flush=True)
    print(f"Local valid replacements: {summary['local_replacements']:,}", flush=True)
    print(f"Provider recovery required: {summary['recovery_required']:,}", flush=True)
    if args.audit_only or scope.empty:
        return 0

    if args.apply_existing_results:
        results_path = run_dir / "abstract_recovery_results.parquet"
        if not results_path.is_file():
            raise FileNotFoundError(f"Existing recovery results not found: {results_path}")
        results = pd.read_parquet(results_path).to_dict("records")
        recovery_scope = scope[scope["recovery_required"].astype(bool)].copy()
        recovered, rejected = valid_recovered_rows(results, recovery_scope)
        apply_report = apply_repairs(
            candidates_path=candidates_path,
            metadata_path=metadata_path,
            scope=scope,
            recovered_by_doi=recovered,
            run_id=args.run_id,
            run_dir=run_dir,
        )
        atomic_write_json(run_dir / "abstract_repair_report.json", apply_report)
        manifest["apply_report"] = apply_report
        manifest["reapplied_existing_results_at_utc"] = now_utc()
        manifest["status"] = "complete"
        manifest["completed_at_utc"] = now_utc()
        manifest["updated_at_utc"] = now_utc()
        atomic_write_json(manifest_path, manifest)
        print(f"Reapplied existing recovery results with current repair logic: {manifest_path}", flush=True)
        return 0

    recovery_scope = scope[scope["recovery_required"].astype(bool)].copy()
    scope_rows = recovery_scope[["doi", "pmid", "pmcid", "study_title", "study_year"]].to_dict("records")
    config = load_config(Path(args.config).resolve())
    pubmed_config = config.get("pubmed", {}) if isinstance(config.get("pubmed"), dict) else {}
    pmc_config = config.get("pmc", {}) if isinstance(config.get("pmc"), dict) else {}
    semantic_config = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar"), dict) else {}
    crossref_config = config.get("crossref", {}) if isinstance(config.get("crossref"), dict) else {}
    max_retries = args.max_retries if args.max_retries is not None else read_int(semantic_config.get("max_retries"), 4)
    results: list[dict] = []

    try:
        if "pubmed" in providers:
            client = BatchHttpClient(
                rps=args.pubmed_rps if args.pubmed_rps is not None else read_float(pubmed_config.get("rate_limit_per_sec"), 3.0),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/abstract-repair-pubmed",
            )
            results.extend(
                run_pubmed_batches(
                    scope_rows,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=client,
                    batch_size=args.pubmed_batch_size,
                    email=clean(pubmed_config.get("email", "")),
                    api_key=clean(pubmed_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        recovered, _ = valid_recovered_rows(results, recovery_scope)
        remaining = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered]
        if "pmc" in providers:
            client = BatchHttpClient(
                rps=args.pmc_rps if args.pmc_rps is not None else read_float(pmc_config.get("rate_limit_per_sec"), 3.0),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/abstract-repair-pmc",
            )
            results.extend(
                run_pmc_batches(
                    remaining,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=client,
                    batch_size=args.pmc_batch_size,
                    email=clean(pubmed_config.get("email", "")),
                    api_key=clean(pubmed_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        recovered, _ = valid_recovered_rows(results, recovery_scope)
        remaining = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered]
        if "semantic_scholar" in providers:
            client = BatchHttpClient(
                rps=(
                    args.semantic_scholar_rps
                    if args.semantic_scholar_rps is not None
                    else read_float(semantic_config.get("rate_limit_per_sec"), 0.5)
                ),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/abstract-repair-semantic-scholar",
            )
            results.extend(
                run_semantic_scholar_batches(
                    remaining,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=client,
                    batch_size=args.semantic_scholar_batch_size,
                    api_key=clean(semantic_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        recovered, _ = valid_recovered_rows(results, recovery_scope)
        remaining = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered]
        if "crossref" in providers:
            client = BatchHttpClient(
                rps=args.crossref_rps if args.crossref_rps is not None else read_float(crossref_config.get("rate_limit_per_sec"), 5.0),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/abstract-repair-crossref",
            )
            results.extend(
                run_crossref_batches(
                    remaining,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=client,
                    batch_size=args.crossref_batch_size,
                    workers=args.crossref_workers,
                    email=clean(crossref_config.get("email", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        results_path = run_dir / "abstract_recovery_results.parquet"
        atomic_write_parquet(results_path, pd.DataFrame(results, columns=list(RESULT_COLUMNS)))
        recovered, rejected = valid_recovered_rows(results, recovery_scope)
        rejected_path = run_dir / "rejected_recovery_abstracts.parquet"
        atomic_write_parquet(rejected_path, pd.DataFrame(rejected))
        recovery_summary = {
            "provider_attempt_rows": len(results),
            "valid_abstracts_recovered": len(recovered),
            "provider_abstracts_rejected_as_contaminated": len(rejected),
            "unresolved_after_recovery": len(recovery_scope) - len(recovered),
            "status_counts_by_provider": {
                provider: dict(Counter(clean(row.get("status", "")) for row in results if row.get("provider") == provider))
                for provider in providers
            },
        }
        manifest["recovery"] = recovery_summary
        manifest["recovery_results_table"] = str(results_path)
        manifest["rejected_recovery_table"] = str(rejected_path)
        manifest["status"] = "recovery_complete" if args.no_apply else "applying"
        manifest["updated_at_utc"] = now_utc()
        atomic_write_json(manifest_path, manifest)
        print(f"Valid provider abstracts recovered: {len(recovered):,}", flush=True)
        print(f"Unresolved contaminated abstracts: {recovery_summary['unresolved_after_recovery']:,}", flush=True)
        if args.no_apply:
            return 0

        apply_report = apply_repairs(
            candidates_path=candidates_path,
            metadata_path=metadata_path,
            scope=scope,
            recovered_by_doi=recovered,
            run_id=args.run_id,
            run_dir=run_dir,
        )
        atomic_write_json(run_dir / "abstract_repair_report.json", apply_report)
        manifest["apply_report"] = apply_report
        manifest["status"] = "complete"
        manifest["completed_at_utc"] = now_utc()
        manifest["updated_at_utc"] = now_utc()
        atomic_write_json(manifest_path, manifest)
        print(f"Repair complete: {manifest_path}", flush=True)
        return 0
    except Exception as error:
        manifest["status"] = "failed"
        manifest["updated_at_utc"] = now_utc()
        manifest["error"] = f"{type(error).__name__}: {error}"
        atomic_write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
