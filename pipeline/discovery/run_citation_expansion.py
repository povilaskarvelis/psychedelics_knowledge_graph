#!/usr/bin/env python3
"""Run bounded OpenAlex citation expansion from reviewed seed records."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.providers import (
    RateLimitedHttpClient,
    authors_from_openalex,
    decode_openalex_abstract,
    load_dotenv_if_present,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
    normalize_pmid,
    source_from_openalex,
    utc_now,
)
from pipeline.discovery.strategy import clean, stable_hash
from pipeline.ingest.metadata_utils import load_config, read_float, read_int


DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "discovery" / "runs"
DEFAULT_SEED_SOURCE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
PROTOCOL_ID = "psychedelics_kg_citation_expansion_v1"
WORK_SELECT = (
    "id,doi,display_name,publication_year,publication_date,type,authorships,ids,"
    "primary_location,language,abstract_inverted_index,referenced_works"
)


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_directions(value: str) -> list[str]:
    directions = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(directions) - {"citing", "references"})
    if invalid:
        raise ValueError(f"Unsupported citation directions: {', '.join(invalid)}")
    if not directions:
        raise ValueError("At least one citation direction is required")
    return list(dict.fromkeys(directions))


def load_seeds(path: Path, *, flag_column: str, max_seeds: int) -> pd.DataFrame:
    frame = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    if flag_column not in frame:
        raise ValueError(f"Seed source is missing flag column: {flag_column}")
    truthy = frame[flag_column].map(
        lambda value: value is True or clean(value).lower() in {"1", "true", "yes"}
    )
    seeds = frame[truthy].copy()
    seeds["doi"] = seeds.get("doi", "").map(normalize_doi)
    seeds["openalex_id"] = seeds.get("openalex_id", "").map(normalize_openalex_id)
    seeds = seeds[(seeds["doi"] != "") | (seeds["openalex_id"] != "")]
    seeds = seeds.sort_values(["doi", "openalex_id"]).head(max(1, int(max_seeds))).reset_index(drop=True)
    if seeds.empty:
        raise ValueError("No reviewed citation seeds with DOI or OpenAlex identifiers were found")
    seeds["seed_id"] = seeds.apply(
        lambda row: f"doi:{row['doi']}" if row["doi"] else f"openalex:{row['openalex_id']}",
        axis=1,
    )
    return seeds


def build_plan(
    seeds: pd.DataFrame,
    *,
    directions: list[str],
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    rows: list[dict] = []
    for seed in seeds.to_dict("records"):
        for direction in directions:
            identity = [seed["seed_id"], direction, from_date, to_date, PROTOCOL_ID]
            rows.append(
                {
                    "execution_id": f"exec_{stable_hash(identity, 20)}",
                    "seed_id": seed["seed_id"],
                    "seed_doi": seed.get("doi", ""),
                    "seed_openalex_id": seed.get("openalex_id", ""),
                    "seed_title": clean(seed.get("study_title") or seed.get("title")),
                    "direction": direction,
                    "from_date": from_date,
                    "to_date": to_date,
                }
            )
    return pd.DataFrame(rows)


def openalex_record(item: dict, *, rank: int) -> dict:
    ids = item.get("ids", {}) if isinstance(item.get("ids"), dict) else {}
    openalex_id = normalize_openalex_id(item.get("id") or ids.get("openalex"))
    return {
        "provider": "openalex",
        "provider_record_id": f"openalex:{openalex_id}",
        "pmid": normalize_pmid(ids.get("pmid")),
        "pmcid": normalize_pmcid(ids.get("pmcid")),
        "doi": normalize_doi(item.get("doi") or ids.get("doi")),
        "openalex_id": openalex_id,
        "semantic_scholar_id": "",
        "title": clean(item.get("display_name")),
        "authors": authors_from_openalex(item.get("authorships", [])),
        "publication_year": clean(item.get("publication_year")),
        "publication_date": clean(item.get("publication_date")),
        "journal": source_from_openalex(item),
        "publication_type": clean(item.get("type")),
        "language": clean(item.get("language")),
        "abstract": decode_openalex_abstract(item.get("abstract_inverted_index")),
        "rank_in_partition": rank,
    }


class CitationClient:
    endpoint = "https://api.openalex.org/works"

    def __init__(self, client: RateLimitedHttpClient, *, api_key: str, email: str = "") -> None:
        self.client = client
        self.api_key = api_key
        self.email = email

    def common(self) -> dict[str, object]:
        return {"api_key": self.api_key or None, "mailto": self.email or None}

    def seed_work(self, openalex_id: str, doi: str) -> dict:
        identifier = openalex_id or f"doi:{doi}"
        encoded = quote(identifier, safe=":")
        return self.client.get_json(
            f"{self.endpoint}/{encoded}",
            params={**self.common(), "select": WORK_SELECT},
        )

    def references(self, seed: dict, *, from_date: str, to_date: str, maximum: int) -> list[dict]:
        reference_ids = sorted(
            {normalize_openalex_id(value) for value in seed.get("referenced_works", []) if clean(value)}
        )
        if len(reference_ids) > maximum:
            raise RuntimeError(
                f"Reference expansion has {len(reference_ids)} records, exceeding max_records_per_seed={maximum}"
            )
        records: list[dict] = []
        for offset in range(0, len(reference_ids), 100):
            batch = reference_ids[offset : offset + 100]
            filters = [
                "openalex:" + "|".join(batch),
                f"from_publication_date:{from_date}",
                f"to_publication_date:{to_date}",
            ]
            payload = self.client.get_json(
                self.endpoint,
                params={
                    **self.common(),
                    "filter": ",".join(filters),
                    "per_page": 100,
                    "select": WORK_SELECT,
                },
            )
            page = [item for item in payload.get("results", []) if isinstance(item, dict)]
            expected = int(payload.get("meta", {}).get("count", len(page)) or 0)
            if len(page) != expected:
                raise RuntimeError(
                    f"Reference batch count reconciliation failed: expected {expected}, retrieved {len(page)}"
                )
            records.extend(page)
        return records

    def citing(self, seed_id: str, *, from_date: str, to_date: str, maximum: int) -> list[dict]:
        filters = ",".join(
            [
                f"cites:{seed_id}",
                f"from_publication_date:{from_date}",
                f"to_publication_date:{to_date}",
            ]
        )
        count_payload = self.client.get_json(
            self.endpoint,
            params={**self.common(), "filter": filters, "per_page": 1, "select": "id"},
        )
        expected = int(count_payload.get("meta", {}).get("count", 0) or 0)
        if expected > maximum:
            raise RuntimeError(
                f"Citing expansion has {expected} records, exceeding max_records_per_seed={maximum}"
            )
        records: list[dict] = []
        cursor: str | None = "*"
        while cursor:
            payload = self.client.get_json(
                self.endpoint,
                params={
                    **self.common(),
                    "filter": filters,
                    "per_page": 100,
                    "cursor": cursor,
                    "select": WORK_SELECT,
                },
            )
            page = [item for item in payload.get("results", []) if isinstance(item, dict)]
            records.extend(page)
            cursor = clean(payload.get("meta", {}).get("next_cursor")) or None
            if not page:
                cursor = None
        unique = {normalize_openalex_id(item.get("id")): item for item in records if clean(item.get("id"))}
        if len(unique) != expected:
            raise RuntimeError(
                f"Citation count reconciliation failed for {seed_id}: expected {expected}, retrieved {len(unique)}"
            )
        return list(unique.values())


def materialize_records(hits: pd.DataFrame) -> pd.DataFrame:
    if hits.empty:
        return pd.DataFrame()
    scalar = [
        "provider", "provider_record_id", "pmid", "pmcid", "doi", "openalex_id",
        "semantic_scholar_id", "title", "authors", "publication_year", "publication_date",
        "journal", "publication_type", "language", "abstract",
    ]
    rows: list[dict] = []
    for (_provider, _record_id), group in hits.groupby(["provider", "provider_record_id"], sort=True):
        row = {column: next((value for value in group[column] if clean(value)), "") for column in scalar}
        row.update(
            {
                "discovery_execution_count": int(group["execution_id"].nunique()),
                "discovery_execution_ids": " | ".join(sorted(set(group["execution_id"]))),
                "discovery_search_ids": " | ".join(sorted(set(group["search_id"]))),
                "discovery_datasets": "general",
                "discovery_layers": "citation_expansion",
                "discovery_compounds": "",
                "discovery_entities": "",
                "first_retrieved_at_utc": min(group["retrieved_at_utc"]),
                "last_retrieved_at_utc": max(group["retrieved_at_utc"]),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict:
    run_dir = Path(args.run_root).resolve() / args.run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Run directory already exists and is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    directions = parse_directions(args.directions)
    seeds = load_seeds(Path(args.seed_source), flag_column=args.seed_flag_column, max_seeds=args.max_seeds)
    plan = build_plan(
        seeds,
        directions=directions,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    seeds.to_parquet(run_dir / "citation_seeds.parquet", index=False)
    plan.to_parquet(run_dir / "search_plan.parquet", index=False)
    plan.to_csv(run_dir / "search_plan.csv", index=False)
    generated = utc_now()
    manifest = {
        "schema_version": "citation_expansion_run_v1",
        "run_id": args.run_id,
        "protocol_id": PROTOCOL_ID,
        "strategy_hash": stable_hash(
            {
                "protocol_id": PROTOCOL_ID,
                "directions": directions,
                "from_date": args.from_date,
                "to_date": args.to_date,
                "max_records_per_seed": args.max_records_per_seed,
            },
            24,
        ),
        "mode": "citation",
        "coverage_start_date": args.from_date,
        "coverage_end_date": args.to_date,
        "providers": ["openalex"],
        "datasets": ["general"],
        "layers": ["citation_expansion"],
        "scope_hash": "",
        "scope_snapshot": {},
        "advances_standard_update_coverage": False,
        "establishes_scope_baseline": False,
        "generated_at_utc": generated,
        "updated_at_utc": generated,
        "status": "planned",
        "retrieval_completion_gate_passed": False,
        "calibration_gate_passed": True,
        "completion_gate_passed": False,
        "counts": {"seeds": len(seeds), "query_executions": len(plan), "provider_hits": 0, "provider_records": 0},
        "directions": directions,
        "max_records_per_seed": args.max_records_per_seed,
        "outputs": {"run_directory": str(run_dir)},
    }
    atomic_json(run_dir / "run_manifest.json", manifest)
    if args.plan_only:
        return manifest

    load_dotenv_if_present(str(ROOT / ".env"))
    config = load_config(Path(args.config))
    openalex = config.get("openalex", {}) if isinstance(config.get("openalex"), dict) else {}
    api_key = clean(openalex.get("api_key")) or os.getenv("OPENALEX_API_KEY", "")
    email = clean(openalex.get("email")) or os.getenv("OPENALEX_EMAIL", "")
    client = RateLimitedHttpClient(
        provider="openalex_citation",
        requests_per_second=read_float(openalex.get("rate_limit_per_sec"), 2.0),
        max_requests=max(1, args.request_budget),
        max_retries=read_int(openalex.get("max_retries"), 4),
        timeout_seconds=args.timeout_seconds,
    )
    provider = CitationClient(client, api_key=api_key, email=email)
    seed_cache: dict[str, dict] = {}
    hit_rows: list[dict] = []
    for task in plan.to_dict("records"):
        seed = seed_cache.get(task["seed_id"])
        if seed is None:
            seed = provider.seed_work(task["seed_openalex_id"], task["seed_doi"])
            seed_cache[task["seed_id"]] = seed
        seed_openalex_id = normalize_openalex_id(seed.get("id"))
        if task["direction"] == "references":
            works = provider.references(
                seed,
                from_date=task["from_date"],
                to_date=task["to_date"],
                maximum=args.max_records_per_seed,
            )
        else:
            works = provider.citing(
                seed_openalex_id,
                from_date=task["from_date"],
                to_date=task["to_date"],
                maximum=args.max_records_per_seed,
            )
        retrieved_at = utc_now()
        search_id = f"citation_{task['direction']}_{seed_openalex_id}"
        for rank, item in enumerate(works, start=1):
            record = openalex_record(item, rank=rank)
            if not record["openalex_id"]:
                continue
            hit_rows.append(
                {
                    **record,
                    "run_id": args.run_id,
                    "protocol_id": PROTOCOL_ID,
                    "execution_id": task["execution_id"],
                    "search_id": search_id,
                    "dataset": "general",
                    "layer": "citation_expansion",
                    "search_type": f"citation_{task['direction']}",
                    "module_id": "reviewed_seed_expansion",
                    "compound": "",
                    "entity": "",
                    "entity_type": "citation_seed",
                    "date_basis": "publication",
                    "search_surface": "openalex_citation_graph",
                    "partition_id": f"seed:{seed_openalex_id}",
                    "partition_start_date": task["from_date"],
                    "partition_end_date": task["to_date"],
                    "page_index": 0,
                    "retrieved_at_utc": retrieved_at,
                    "citation_seed_id": task["seed_id"],
                    "citation_seed_openalex_id": seed_openalex_id,
                    "citation_direction": task["direction"],
                }
            )
    hits = pd.DataFrame(hit_rows)
    if not hits.empty:
        hits = hits.drop_duplicates(["execution_id", "provider_record_id"])
    hits.to_parquet(run_dir / "provider_hits.parquet", index=False)
    records = materialize_records(hits)
    records.to_parquet(run_dir / "retrieved_records.parquet", index=False)
    manifest["status"] = "complete"
    manifest["retrieval_completion_gate_passed"] = True
    manifest["completion_gate_passed"] = True
    manifest["updated_at_utc"] = utc_now()
    manifest["counts"].update(
        {
            "provider_hits": int(len(hits)),
            "provider_records": int(len(records)),
            "records_with_doi": int(records["doi"].astype(bool).sum()) if "doi" in records else 0,
            "records_without_doi": int((~records["doi"].astype(bool)).sum()) if "doi" in records else 0,
        }
    )
    manifest["provider_sessions"] = [
        {"ended_at_utc": utc_now(), "providers": {"openalex": client.stats.to_dict()}}
    ]
    manifest["outputs"].update(
        {
            "provider_hits_parquet": str((run_dir / "provider_hits.parquet").resolve()),
            "retrieved_records_parquet": str((run_dir / "retrieved_records.parquet").resolve()),
        }
    )
    atomic_json(run_dir / "run_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded citation expansion from reviewed OpenAlex seed records.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--seed-source", default=str(DEFAULT_SEED_SOURCE))
    parser.add_argument(
        "--seed-flag-column",
        required=True,
        help="Boolean column defining the reviewed seed cohort for this run.",
    )
    parser.add_argument("--directions", default="citing")
    parser.add_argument("--from-date", default="1800-01-01")
    parser.add_argument("--to-date", default=dt.date.today().isoformat())
    parser.add_argument(
        "--max-seeds",
        type=int,
        required=True,
        help="Explicit upper bound for reviewed seeds; there is no pilot-set default.",
    )
    parser.add_argument("--max-records-per-seed", type=int, default=2000)
    parser.add_argument("--request-budget", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.local.yaml"))
    parser.add_argument("--plan-only", action="store_true")
    return parser


def main() -> int:
    manifest = run(build_parser().parse_args())
    print(f"Run ID: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Seeds: {manifest['counts']['seeds']}")
    print(f"Citation executions: {manifest['counts']['query_executions']}")
    print(f"Provider records: {manifest['counts']['provider_records']}")
    print(f"Run directory: {manifest['outputs']['run_directory']}")
    return 0 if manifest["status"] in {"planned", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
