from dataclasses import replace
from pathlib import Path

import pandas as pd

from pipeline.discovery.providers import ProviderStats, RequestBudgetExhausted
from pipeline.discovery.runner import (
    atomic_write_json,
    execute_run,
    finalize_completed_retrieval,
    prepare_run,
    read_json,
)
from pipeline.discovery.strategy import SearchExecution


def execution() -> SearchExecution:
    return SearchExecution(
        execution_id="exec_test",
        search_id="search_test",
        dataset="mechanistic",
        provider="pubmed",
        layer="core",
        search_type="two_block_core",
        module_id="target",
        query="psilocybin[Text Word]",
        compound="",
        entity="",
        entity_type="domain",
        search_surface="text_word_and_controlled_vocabulary",
        date_basis="publication",
        start_date="2026-01-01",
        end_date="2026-01-02",
        protocol_id="protocol",
        strategy_hash="strategy",
        scope_hash="scope",
    )


class FakeClient:
    def __init__(self):
        self.stats = ProviderStats(provider="pubmed")


class CompleteProvider:
    def __init__(self):
        self.client = FakeClient()

    def count(self, _execution, start, end):
        return 6 if start != end else 3

    def fetch_page(self, _execution, start, _end, *, token, page_size):
        offset = int(token or 0)
        day = start[-2:]
        all_ids = [f"{day}{index}" for index in range(3)]
        ids = all_ids[offset : offset + page_size]
        records = [
            {
                "provider": "pubmed",
                "provider_record_id": f"pmid:{identifier}",
                "pmid": identifier,
                "pmcid": "",
                "doi": "" if identifier.endswith("0") else f"10.1000/{identifier}",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "title": f"Record {identifier}",
                "authors": "",
                "publication_year": "2026",
                "publication_date": start,
                "journal": "",
                "publication_type": "article",
                "language": "eng",
                "abstract": "",
                "rank_in_partition": offset + index + 1,
            }
            for index, identifier in enumerate(ids)
        ]
        next_offset = offset + len(ids)
        return records, str(next_offset) if next_offset < len(all_ids) else None


class PausedProvider(CompleteProvider):
    def count(self, _execution, _start, _end):
        raise RequestBudgetExhausted("resume later")


class PausedFetchProvider(CompleteProvider):
    def fetch_page(self, _execution, _start, _end, *, token, page_size):
        raise RequestBudgetExhausted("resume later")


class FailedProvider(CompleteProvider):
    def count(self, _execution, _start, _end):
        raise RuntimeError("provider unavailable")


class ShrinkingProvider(CompleteProvider):
    def __init__(self):
        super().__init__()
        self.count_calls = 0

    def count(self, _execution, _start, _end):
        self.count_calls += 1
        return 3 if self.count_calls == 1 else 2

    def fetch_page(self, _execution, start, _end, *, token, page_size):
        offset = int(token or 0)
        ids = ["one", "two"]
        selected = ids[offset : offset + page_size]
        records = [
            {
                "provider": "pubmed",
                "provider_record_id": f"pmid:{identifier}",
                "pmid": identifier,
                "pmcid": "",
                "doi": f"10.1000/{identifier}",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "title": identifier,
                "authors": "",
                "publication_year": "2026",
                "publication_date": start,
                "journal": "",
                "publication_type": "article",
                "language": "eng",
                "abstract": "",
                "rank_in_partition": offset + index + 1,
            }
            for index, identifier in enumerate(selected)
        ]
        next_offset = offset + len(selected)
        return records, str(next_offset) if next_offset < len(ids) else None


class TinyStableShortfallProvider(ShrinkingProvider):
    def count(self, _execution, _start, _end):
        return 1001

    def fetch_page(self, _execution, start, _end, *, token, page_size):
        offset = int(token or 0)
        ids = [str(index) for index in range(1000)]
        selected = ids[offset : offset + page_size]
        records = [
            {
                "provider": "pubmed",
                "provider_record_id": f"pmid:{identifier}",
                "pmid": identifier,
                "pmcid": "",
                "doi": f"10.1000/{identifier}",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "title": identifier,
                "authors": "",
                "publication_year": "2026",
                "publication_date": start,
                "journal": "",
                "publication_type": "article",
                "language": "eng",
                "abstract": "",
                "rank_in_partition": offset + index + 1,
            }
            for index, identifier in enumerate(selected)
        ]
        next_offset = offset + len(selected)
        return records, str(next_offset) if next_offset < len(ids) else None


def prepare(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    prepare_run(
        run_dir=run_dir,
        run_id="run",
        executions=[execution()],
        plan_metadata={
            "protocol_id": "protocol",
            "strategy_path": str(tmp_path / "strategy.json"),
            "providers": ["pubmed"],
            "datasets": ["mechanistic"],
            "layers": ["core"],
            "mode": "update",
            "coverage_start_date": "2026-01-01",
            "coverage_end_date": "2026-01-02",
            "strategy_hash": "strategy",
            "scope_hash": "scope",
            "scope_snapshot": {},
        },
        request_budgets={"pubmed": 10},
    )
    return run_dir


def test_runner_partitions_and_reconciles_every_provider_id(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": CompleteProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
    )

    assert manifest["status"] == "complete"
    assert manifest["completion_gate_passed"]
    assert manifest["counts"]["provider_hits"] == 6
    assert manifest["counts"]["records_without_doi"] == 2
    assert manifest["provider_sessions"][0]["request_budgets"] == {"pubmed": 10}
    executions = pd.read_parquet(run_dir / "query_executions.parquet")
    assert executions.loc[0, "expected_total"] == 6
    assert executions.loc[0, "retrieved_total"] == 6
    assert executions.loc[0, "partition_count"] == 2


def test_completed_retrieval_can_be_finalized_again_without_provider_requests(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    complete = execute_run(
        run_dir=run_dir,
        providers={"pubmed": CompleteProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
    )
    assert complete["status"] == "complete"
    manifest_path = run_dir / "run_manifest.json"
    interrupted = read_json(manifest_path)
    interrupted["status"] = "materializing"
    interrupted["completion_gate_passed"] = False
    atomic_write_json(manifest_path, interrupted)

    finalized = finalize_completed_retrieval(run_dir)

    assert finalized["status"] == "complete"
    assert finalized["completion_gate_passed"]
    assert finalized["counts"]["provider_hits"] == 6


def test_runner_marks_budget_pause_as_incomplete_not_complete(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": PausedProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
    )

    assert manifest["status"] == "paused_budget"
    assert not manifest["completion_gate_passed"]
    assert manifest["counts"]["complete_executions"] == 0
    state = read_json(run_dir / "run_state.json")
    assert state["executions"]["exec_test"]["pending_ranges"] == [
        {"start_date": "2026-01-01", "end_date": "2026-01-02"}
    ]

    resumed = execute_run(
        run_dir=run_dir,
        providers={"pubmed": CompleteProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
    )
    assert resumed["status"] == "complete"
    assert resumed["completion_gate_passed"]


def test_retry_failed_resets_active_partition_reconciliation_allowance(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    state_path = run_dir / "run_state.json"
    state = read_json(state_path)
    execution_state = state["executions"]["exec_test"]
    execution_state.update(
        {
            "status": "failed",
            "pending_ranges": [],
            "active_partition": {
                "partition_id": "part_failed",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
                "expected_count": 3,
                "initial_expected_count": 3,
                "final_expected_count": 3,
                "reconciliation_attempts": 1,
                "next_token": "",
                "page_index": 2,
            },
            "error": "RuntimeError: count_reconciliation_failed",
        }
    )
    atomic_write_json(state_path, state)

    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": PausedFetchProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
        retry_failed=True,
    )

    assert manifest["status"] == "paused_budget"
    resumed_state = read_json(state_path)["executions"]["exec_test"]
    assert resumed_state["status"] == "running"
    assert resumed_state["retry_count"] == 1
    assert resumed_state["active_partition"]["reconciliation_attempts"] == 0
    assert resumed_state["error"] == ""


def test_runner_marks_provider_error_as_failed(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": FailedProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
    )

    assert manifest["status"] == "failed"
    assert not manifest["completion_gate_passed"]
    assert manifest["counts"]["failed_executions"] == 1


def test_runner_reconciles_provider_count_drift_after_pagination(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    provider = ShrinkingProvider()
    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": provider},
        provider_config={"pubmed": {"partition_max_records": 10, "page_size": 2}},
    )

    assert manifest["status"] == "complete"
    state = read_json(run_dir / "run_state.json")["executions"]["exec_test"]
    partition = state["completed_partitions"][0]
    assert partition["initial_expected_count"] == 3
    assert partition["final_expected_count"] == 2
    assert partition["count_drift"] == -1
    assert partition["retrieved_count"] == 2
    assert state["count_request_count"] == 2


def test_runner_accepts_and_reports_tiny_stable_count_shortfall(tmp_path: Path) -> None:
    run_dir = prepare(tmp_path)
    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": TinyStableShortfallProvider()},
        provider_config={
            "pubmed": {
                "partition_max_records": 2000,
                "page_size": 1000,
                "reconciliation_retries": 0,
                "count_drift_tolerance_records": 3,
                "count_drift_tolerance_fraction": 0.001,
            }
        },
    )

    assert manifest["status"] == "complete"
    assert manifest["counts"]["accepted_count_drift_partitions"] == 1
    assert manifest["counts"]["accepted_count_drift_records"] == 1
    state = read_json(run_dir / "run_state.json")["executions"]["exec_test"]
    partition = state["completed_partitions"][0]
    assert partition["reconciliation_status"] == "accepted_provider_count_drift"
    assert partition["reconciliation_shortfall"] == 1
    executions = pd.read_parquet(run_dir / "query_executions.parquet")
    assert executions.loc[0, "accepted_count_drift_records"] == 1


def test_runner_can_resume_only_one_provider(tmp_path: Path) -> None:
    pubmed_execution = execution()
    openalex_execution = replace(
        pubmed_execution,
        execution_id="exec_openalex",
        search_id="search_openalex",
        provider="openalex",
        query="psilocybin",
        search_surface="fulltext",
    )
    run_dir = tmp_path / "run"
    prepare_run(
        run_dir=run_dir,
        run_id="run",
        executions=[pubmed_execution, openalex_execution],
        plan_metadata={
            "protocol_id": "protocol",
            "strategy_path": str(tmp_path / "strategy.json"),
            "providers": ["pubmed", "openalex"],
            "datasets": ["mechanistic"],
            "layers": ["core"],
            "mode": "update",
            "coverage_start_date": "2026-01-01",
            "coverage_end_date": "2026-01-02",
            "strategy_hash": "strategy",
            "scope_hash": "scope",
            "scope_snapshot": {},
        },
        request_budgets={"pubmed": 10, "openalex": 10},
    )

    manifest = execute_run(
        run_dir=run_dir,
        providers={"pubmed": CompleteProvider()},
        provider_config={"pubmed": {"partition_max_records": 3, "page_size": 2}},
        session_request_budgets={"pubmed": 10},
    )

    assert manifest["status"] == "incomplete"
    assert not manifest["completion_gate_passed"]
    assert manifest["counts"]["complete_executions"] == 1
    assert manifest["provider_sessions"][0]["request_budgets"] == {"pubmed": 10}
    state = read_json(run_dir / "run_state.json")
    assert state["executions"]["exec_test"]["status"] == "complete"
    assert state["executions"]["exec_openalex"]["status"] == "pending"
