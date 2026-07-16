#!/usr/bin/env python3
"""Plan, run, and resume a versioned living literature search."""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.providers import (
    OpenAlexProvider,
    PubMedProvider,
    RateLimitedHttpClient,
    load_dotenv_if_present,
    openalex_budget_status,
)
from pipeline.discovery.composite import build_historical_gap_plan, mark_reused_component
from pipeline.discovery.runner import execute_run, prepare_run, read_json
from pipeline.discovery.runner import atomic_write_json
from pipeline.discovery.strategy import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_HISTORY_PATH,
    DEFAULT_STRATEGY_PATH,
    SUPPORTED_DATASETS,
    SUPPORTED_PROVIDERS,
    build_search_plan,
    clean,
)
from pipeline.ingest.metadata_utils import load_config, read_float, read_int


DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "discovery" / "runs"


def parse_csv_values(value: str, allowed: tuple[str, ...], label: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(values) - set(allowed))
    if invalid:
        raise ValueError(f"Unsupported {label}: {', '.join(invalid)}")
    return values


def default_run_id() -> str:
    return "living_search_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def provider_adapters(args: argparse.Namespace, config: dict) -> tuple[dict, dict[str, int]]:
    load_dotenv_if_present(str(ROOT / ".env"))
    openalex_config = config.get("openalex", {}) if isinstance(config.get("openalex"), dict) else {}
    pubmed_config = config.get("pubmed", {}) if isinstance(config.get("pubmed"), dict) else {}
    email = clean(pubmed_config.get("email")) or os.getenv("NCBI_EMAIL", "") or os.getenv("OPENALEX_EMAIL", "")
    openalex_email = clean(openalex_config.get("email")) or os.getenv("OPENALEX_EMAIL", "") or email
    ncbi_api_key = clean(pubmed_config.get("api_key")) or os.getenv("NCBI_API_KEY", "")
    openalex_api_key = clean(openalex_config.get("api_key")) or os.getenv("OPENALEX_API_KEY", "")
    max_retries = args.max_retries if args.max_retries is not None else read_int(openalex_config.get("max_retries"), 4)
    requested_providers = set(parse_csv_values(args.providers, SUPPORTED_PROVIDERS, "providers"))
    openalex_status = (
        openalex_budget_status(openalex_api_key, timeout_seconds=args.timeout_seconds)
        if "openalex" in requested_providers
        else None
    )
    requested_openalex_budget = args.openalex_request_budget
    if openalex_status is not None:
        available = int(openalex_status["search_requests_remaining"])
        if requested_openalex_budget is None or requested_openalex_budget == 0:
            openalex_budget = available
        else:
            openalex_budget = min(max(0, requested_openalex_budget), available)
        openalex_budget_context = {
            **openalex_status,
            "requested_session_budget": requested_openalex_budget,
            "resolved_session_budget": openalex_budget,
        }
    else:
        openalex_budget = 800 if requested_openalex_budget is None else max(0, requested_openalex_budget)
        openalex_budget_context = {
            "source": "fallback_or_explicit",
            "requested_session_budget": requested_openalex_budget,
            "resolved_session_budget": openalex_budget,
        }
    # The HTTP client uses zero for unlimited; -1 represents a verified
    # zero-call allowance and pauses before making a request.
    openalex_client_budget = -1 if openalex_status is not None and openalex_budget == 0 else openalex_budget
    budgets = {
        "pubmed": max(0, args.pubmed_request_budget),
        "openalex": max(0, openalex_budget),
    }
    pubmed_client = RateLimitedHttpClient(
                provider="pubmed",
                requests_per_second=read_float(pubmed_config.get("rate_limit_per_sec"), 2.5),
                max_requests=budgets["pubmed"],
                max_retries=max_retries,
                timeout_seconds=args.timeout_seconds,
                max_retry_after_seconds=args.max_retry_after_seconds,
            )
    openalex_client = RateLimitedHttpClient(
                provider="openalex",
                requests_per_second=read_float(openalex_config.get("rate_limit_per_sec"), 2.0),
                max_requests=openalex_client_budget,
                max_retries=max_retries,
                timeout_seconds=args.timeout_seconds,
                max_retry_after_seconds=args.max_retry_after_seconds,
            )
    openalex_client.budget_context = openalex_budget_context
    adapters = {
        "pubmed": PubMedProvider(
            pubmed_client,
            email=email,
            api_key=ncbi_api_key,
        ),
        "openalex": OpenAlexProvider(
            openalex_client,
            email=openalex_email,
            api_key=openalex_api_key,
        ),
    }
    return adapters, budgets


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run exhaustive, versioned PubMed/OpenAlex discovery with resumable request budgets."
    )
    parser.add_argument("--mode", choices=["update", "full", "historical_gap"], default="update")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY_PATH))
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Provider credentials and rate settings. This file is not used as the research scope source.",
    )
    parser.add_argument(
        "--scope-config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Canonical validation allowlists used to build the search scope.",
    )
    parser.add_argument("--history", default=str(DEFAULT_HISTORY_PATH))
    parser.add_argument(
        "--reuse-run-id",
        default="",
        help="Completed update run whose recent and all-time scope-delta coverage is reused by historical_gap mode.",
    )
    parser.add_argument("--providers", default=",".join(SUPPORTED_PROVIDERS))
    parser.add_argument("--datasets", default=",".join(SUPPORTED_DATASETS))
    parser.add_argument(
        "--layers",
        default="",
        help="Comma-separated core,scope,targeted_pairs. Defaults to core,scope for both update and full runs.",
    )
    parser.add_argument("--from-date", default="")
    parser.add_argument("--to-date", default="")
    parser.add_argument("--no-index-updates", action="store_true")
    parser.add_argument(
        "--openalex-created-date-updates",
        action="store_true",
        help="Use OpenAlex created-date update streams. This currently requires a paid OpenAlex plan.",
    )
    parser.add_argument("--no-scope-delta", action="store_true")
    parser.add_argument(
        "--allow-large-plan",
        action="store_true",
        help="Explicitly override the strategy's maximum execution count after inspecting the saved plan.",
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--allow-retired-strategy-resume",
        action="store_true",
        help="Resume a run whose protocol differs from the selected active strategy after explicit review.",
    )
    parser.add_argument("--retry-failed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--no-known-record-calibration",
        action="store_true",
        help=(
            "Skip the known-record coverage check for this run. Yield diagnostics and mechanical "
            "retrieval-completeness gates remain enabled."
        ),
    )
    parser.add_argument(
        "--pubmed-request-budget",
        type=int,
        default=2000,
        help="Maximum PubMed HTTP attempts in this session; 0 is unlimited. Resume to continue.",
    )
    parser.add_argument(
        "--openalex-request-budget",
        type=int,
        default=None,
        help=(
            "Maximum OpenAlex HTTP attempts in this session; defaults to the live remaining daily "
            "plus prepaid search allowance, is capped by that live allowance when specified, "
            "and falls back to 800 if status is unavailable."
        ),
    )
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--max-retry-after-seconds", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    return parser


def run(args: argparse.Namespace) -> dict:
    run_id = clean(args.run_id) or default_run_id()
    run_dir = Path(args.run_root).resolve() / run_id
    config_path = Path(args.config).resolve()
    scope_config_path = Path(args.scope_config).resolve()
    config = load_config(config_path)
    adapters, budgets = provider_adapters(args, config)

    if args.resume:
        if not run_dir.exists():
            raise FileNotFoundError(f"Cannot resume missing run directory: {run_dir}")
        manifest = read_json(run_dir / "run_manifest.json")
        selected_strategy = read_json(Path(args.strategy).resolve())
        selected_protocol = clean(selected_strategy.get("protocol_id"))
        planned_protocol = clean(manifest.get("protocol_id"))
        if (
            selected_protocol
            and planned_protocol != selected_protocol
            and not args.allow_retired_strategy_resume
        ):
            raise ValueError(
                f"Run protocol {planned_protocol} differs from selected active protocol "
                f"{selected_protocol}; start a new run or pass --allow-retired-strategy-resume "
                "after inspecting the retired plan"
            )
        planned = set(manifest.get("providers", []))
        requested = set(parse_csv_values(args.providers, SUPPORTED_PROVIDERS, "providers"))
        selected = planned & requested
        if not selected:
            raise ValueError(
                "None of the requested providers are present in this run: "
                + ", ".join(sorted(planned))
            )
        adapters = {name: adapter for name, adapter in adapters.items() if name in selected}
    else:
        providers = parse_csv_values(args.providers, SUPPORTED_PROVIDERS, "providers")
        datasets = parse_csv_values(args.datasets, SUPPORTED_DATASETS, "datasets")
        default_layers = "core,scope"
        layers = parse_csv_values(
            args.layers or default_layers,
            ("core", "scope", "targeted_pairs"),
            "layers",
        )
        if args.mode == "historical_gap":
            reuse_run_id = clean(args.reuse_run_id)
            if not reuse_run_id:
                raise ValueError("--reuse-run-id is required in historical_gap mode")
            executions, metadata = build_historical_gap_plan(
                reuse_run_dir=Path(args.run_root).resolve() / reuse_run_id,
                strategy_path=Path(args.strategy).resolve(),
                config_path=scope_config_path,
                history_path=Path(args.history).resolve(),
                providers=providers,
                datasets=datasets,
                layers=layers,
                allow_large_plan=args.allow_large_plan,
            )
        else:
            executions, metadata = build_search_plan(
                strategy_path=Path(args.strategy).resolve(),
                config_path=scope_config_path,
                history_path=Path(args.history).resolve(),
                mode=args.mode,
                providers=providers,
                datasets=datasets,
                layers=layers,
                start_date=args.from_date,
                end_date=args.to_date,
                include_index_updates=not args.no_index_updates,
                include_openalex_index_updates=args.openalex_created_date_updates,
                include_scope_delta=not args.no_scope_delta,
                allow_large_plan=args.allow_large_plan,
            )
        metadata["provider_config_path"] = str(config_path)
        if not executions:
            raise RuntimeError("The selected search plan contains no query executions")
        manifest = prepare_run(
            run_dir=run_dir,
            run_id=run_id,
            executions=executions,
            plan_metadata=metadata,
            request_budgets=budgets,
        )
        if args.mode == "historical_gap":
            mark_reused_component(
                Path(args.run_root).resolve() / clean(args.reuse_run_id),
                role="recent_update",
            )
        adapters = {name: adapter for name, adapter in adapters.items() if name in providers}

    if args.no_known_record_calibration:
        manifest["calibration"] = {
            "known_relevant_check_enabled": False,
            "required_for_promotion": False,
            "disabled_reason": "Disabled by operator for this search run.",
        }
        manifest["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        atomic_write_json(run_dir / "run_manifest.json", manifest)

    if args.plan_only:
        return manifest
    strategy_payload = read_json(Path(manifest["strategy_path"]))
    active_budgets = {name: budgets[name] for name in adapters}
    return execute_run(
        run_dir=run_dir,
        providers=adapters,
        provider_config=strategy_payload.get("providers", {}),
        session_request_budgets=active_budgets,
        continue_on_error=args.continue_on_error,
        retry_failed=args.retry_failed,
    )


def main() -> int:
    args = build_arg_parser().parse_args()
    manifest = run(args)
    print(f"Run ID: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Completion gate passed: {manifest['completion_gate_passed']}")
    print(f"Query executions: {manifest['counts']['query_executions']}")
    print(f"Complete executions: {manifest['counts']['complete_executions']}")
    print(f"Provider hits: {manifest['counts']['provider_hits']}")
    print(f"Run directory: {manifest['outputs']['run_directory']}")
    return 0 if manifest["status"] in {"planned", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
