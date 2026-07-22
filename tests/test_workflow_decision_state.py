import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.workflow.decision_state import (
    ActiveArtifact,
    downstream_candidate_defaults,
    reconcile_candidate_frame,
    reconcile_workflow_decision,
)


def test_prescreen_invalidation_clears_post_retrieval_projection_fields() -> None:
    defaults = downstream_candidate_defaults("prescreen")

    assert defaults["post_retrieval_decision"] == ""
    assert defaults["post_retrieval_publication_format"] == ""
    assert defaults["post_retrieval_run_id"] == ""


def candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "doi": "10.example/stable-include",
                "study_title": "Stable paper",
                "pdf_local_path": "/kept/stable.pdf",
                "prescreen_retained_for_extraction_candidate": True,
                "literature_source_family": "primary",
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready",
                "graph_inclusion_status": "represented",
                "current_pipeline_status": "graph_represented",
            },
            {
                "doi": "10.example/new-include",
                "study_title": "Newly included paper",
                "pdf_local_path": "/kept/new.pdf",
                "prescreen_retained_for_extraction_candidate": False,
                "literature_source_family": "stale",
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "stale_exclusion",
                "graph_inclusion_status": "not_reached",
                "current_pipeline_status": "old_exclusion",
            },
            {
                "doi": "10.example/new-exclude",
                "study_title": "Newly excluded paper",
                "pdf_local_path": "/kept/excluded.pdf",
                "prescreen_retained_for_extraction_candidate": True,
                "literature_source_family": "primary",
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready",
                "graph_inclusion_status": "represented",
                "current_pipeline_status": "graph_represented",
            },
            {
                "doi": "10.example/stable-exclude",
                "study_title": "Still excluded paper",
                "pdf_local_path": "/kept/still-excluded.pdf",
                "prescreen_retained_for_extraction_candidate": False,
                "literature_source_family": "stale",
                "retained_for_extraction_candidate": False,
                "extraction_route_status": "context_only",
                "graph_inclusion_status": "not_reached",
                "current_pipeline_status": "old_exclusion",
            },
        ]
    )


def prescreen_updates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "doi": "10.example/stable-include",
                "prescreen_retained_for_extraction_candidate": True,
                "prescreen_decisions": "retain",
            },
            {
                "doi": "10.example/new-include",
                "prescreen_retained_for_extraction_candidate": True,
                "prescreen_decisions": "retain",
            },
            {
                "doi": "10.example/new-exclude",
                "prescreen_retained_for_extraction_candidate": False,
                "prescreen_decisions": "exclude",
            },
            {
                "doi": "10.example/stable-exclude",
                "prescreen_retained_for_extraction_candidate": False,
                "prescreen_decisions": "exclude",
            },
        ]
    )


def test_prescreen_reconciliation_preserves_only_stable_includes_and_keeps_source_data() -> None:
    previous = {"10.example/stable-include", "10.example/new-exclude"}
    current = {"10.example/stable-include", "10.example/new-include"}

    out, summary = reconcile_candidate_frame(
        candidate_rows(),
        decision_updates=prescreen_updates(),
        update_defaults={
            "prescreen_retained_for_extraction_candidate": False,
            "prescreen_decisions": "",
        },
        stage="prescreen",
        previous_included_dois=previous,
        current_included_dois=current,
        pending_status="prescreen_retained_pending_model_screen",
        excluded_status="prescreen_excluded",
    )
    rows = out.set_index("doi")

    stable = rows.loc["10.example/stable-include"]
    assert stable["literature_source_family"] == "primary"
    assert stable["extraction_route_status"] == "ready"
    assert stable["graph_inclusion_status"] == "represented"
    assert stable["current_pipeline_status"] == "graph_represented"

    for doi in (
        "10.example/new-include",
        "10.example/new-exclude",
        "10.example/stable-exclude",
    ):
        row = rows.loc[doi]
        assert row["literature_source_family"] == ""
        assert not bool(row["retained_for_extraction_candidate"])
        assert row["extraction_route_status"] == ""
        assert row["graph_inclusion_status"] == ""
        assert row["pdf_local_path"].startswith("/kept/")
        assert row["study_title"]

    assert rows.loc["10.example/new-include", "current_pipeline_status"] == (
        "prescreen_retained_pending_model_screen"
    )
    assert rows.loc["10.example/new-exclude", "current_pipeline_status"] == "prescreen_excluded"
    assert summary["stable_included_dois"] == 1
    assert summary["newly_included_dois"] == 1
    assert summary["newly_excluded_dois"] == 1
    assert summary["downstream_reset_dois"] == 3


def test_later_stage_reconciliation_clears_only_fields_after_that_stage() -> None:
    frame = candidate_rows().iloc[[0]].copy()
    updates = pd.DataFrame([{"doi": "10.example/stable-include", "model_decision": "exclude"}])

    out, _ = reconcile_candidate_frame(
        frame,
        decision_updates=updates,
        update_defaults={"model_decision": ""},
        stage="model_screening",
        previous_included_dois={"10.example/stable-include"},
        current_included_dois=set(),
    )
    row = out.iloc[0]

    assert row["model_decision"] == "exclude"
    assert row["literature_source_family"] == "primary"
    assert bool(row["retained_for_extraction_candidate"])
    assert row["extraction_route_status"] == ""
    assert row["graph_inclusion_status"] == ""


def test_reconciler_filters_declared_active_views_but_not_historical_artifacts() -> None:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidate = root / "candidate.parquet"
        active_routes = root / "active_routes.parquet"
        active_tasks = root / "active_tasks.jsonl"
        historical = root / "historical_raw.jsonl"
        report = root / "report.json"
        candidate_rows().to_parquet(candidate, index=False)
        pd.DataFrame(
            [
                {"doi": "10.example/stable-include", "route": "keep"},
                {"doi": "10.example/new-include", "route": "replace"},
                {"doi": "10.example/new-exclude", "route": "remove"},
            ]
        ).to_parquet(active_routes, index=False)
        task_rows = [
            {"study_doi": "10.example/stable-include", "task": "keep"},
            {"study_doi": "10.example/new-include", "task": "replace"},
        ]
        active_tasks.write_text("".join(json.dumps(row) + "\n" for row in task_rows), encoding="utf-8")
        historical.write_text(json.dumps({"doi": "10.example/new-exclude"}) + "\n", encoding="utf-8")

        result = reconcile_workflow_decision(
            candidate_table=candidate,
            decision_updates=prescreen_updates(),
            update_defaults={
                "prescreen_retained_for_extraction_candidate": False,
                "prescreen_decisions": "",
            },
            stage="prescreen",
            previous_included_dois={"10.example/stable-include", "10.example/new-exclude"},
            current_included_dois={"10.example/stable-include", "10.example/new-include"},
            active_artifacts=[
                ActiveArtifact(active_routes, kind="parquet"),
                ActiveArtifact(active_tasks, kind="jsonl"),
            ],
            report_path=report,
        )

        routes = pd.read_parquet(active_routes)
        tasks = [json.loads(line) for line in active_tasks.read_text().splitlines()]
        historical_text = historical.read_text(encoding="utf-8")
        report_exists = report.exists()

    assert routes["doi"].tolist() == ["10.example/stable-include"]
    assert [row["study_doi"] for row in tasks] == ["10.example/stable-include"]
    assert historical_text == json.dumps({"doi": "10.example/new-exclude"}) + "\n"
    assert result["historical_artifact_policy"].startswith("preserved")
    assert report_exists
