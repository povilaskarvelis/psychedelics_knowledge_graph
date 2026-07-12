from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.extract.build_review_paper_complete_evaluation import (
    EVALUATION_DOMAINS,
    build_outputs,
    build_review_candidates,
    select_review_cohort,
)


def review_task(
    doi: str,
    domain: str,
    *,
    depth: str = "article_text",
    review_type: str = "review",
    status: str = "ready_for_model",
) -> dict:
    access = "full_text_seen" if depth == "article_text" else "abstract_only"
    mode = "full_text_packet" if depth == "article_text" else "abstract"
    return {
        "task_id": f"task-{doi}-{domain}",
        "route_id": f"route-{doi}-{domain}",
        "study_doi": doi,
        "task_status": status,
        "paper_metadata": {
            "doi": doi,
            "study_title": f"Review {doi}",
            "study_year": "2026",
        },
        "route_context": {
            "route_id": f"route-{doi}-{domain}",
            "domain_route": domain,
            "source_type": review_type,
            "route_priority": 20,
        },
        "extraction_contract": {
            "prompt_profile": "secondary_review_coverage",
            "schema_profile": "review_coverage_schema",
            "domain_route": domain,
            "source_type": review_type,
            "access_level": access,
        },
        "text_source": {"mode": mode, "access_level": access},
        "content": {"title": f"Review {doi}", "abstract": "Review abstract."},
    }


def synthetic_candidates() -> list[dict]:
    tasks = []
    domain_index = 0
    for depth in ("article_text", "abstract_only"):
        for review_type in ("review", "systematic_review"):
            for route_count in (2, 3, 5):
                for paper_index in range(8):
                    doi = f"10.1000/{depth}-{review_type}-{route_count}-{paper_index}"
                    domains = []
                    for offset in range(route_count):
                        domains.append(EVALUATION_DOMAINS[(domain_index + offset) % len(EVALUATION_DOMAINS)])
                    domain_index += 1
                    tasks.extend(
                        review_task(doi, domain, depth=depth, review_type=review_type)
                        for domain in domains
                    )
    return tasks


def test_candidate_builder_requires_every_review_route_to_be_ready() -> None:
    tasks = [
        review_task("10.1000/ready", "clinical_outcome"),
        review_task("10.1000/ready", "safety_tolerability"),
        review_task("10.1000/incomplete", "clinical_outcome"),
        review_task("10.1000/incomplete", "brain_system", status="needs_expected_fulltext_packet"),
    ]

    candidates, exclusions = build_review_candidates(tasks)

    assert [candidate.doi for candidate in candidates] == ["10.1000/ready"]
    assert exclusions == [
        {
            "doi": "10.1000/incomplete",
            "reasons": ["not_all_review_routes_ready"],
            "review_route_count": 2,
        }
    ]


def test_selection_is_deterministic_and_keeps_forced_paper_complete() -> None:
    candidates, exclusions = build_review_candidates(synthetic_candidates())
    assert exclusions == []
    forced = candidates[0]

    selected_a, report_a = select_review_cohort(
        candidates,
        cohort_size=24,
        seed=7,
        include_dois=[forced.doi],
        min_domain_papers=1,
    )
    selected_b, report_b = select_review_cohort(
        candidates,
        cohort_size=24,
        seed=7,
        include_dois=[forced.doi],
        min_domain_papers=1,
    )

    assert [candidate.doi for candidate in selected_a] == [candidate.doi for candidate in selected_b]
    assert forced.doi in {candidate.doi for candidate in selected_a}
    selected_forced = next(candidate for candidate in selected_a if candidate.doi == forced.doi)
    assert len(selected_forced.tasks) == len(forced.tasks)
    assert report_a == report_b
    assert report_a["cohort_size"] == 24


def test_build_outputs_exports_all_selected_tasks_and_annotation_templates(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    tasks = synthetic_candidates()
    tasks_path.write_text("".join(json.dumps(task) + "\n" for task in tasks), encoding="utf-8")
    candidates, _ = build_review_candidates(tasks)
    forced = candidates[0]

    manifest = build_outputs(
        tasks_jsonl=tasks_path,
        out_dir=tmp_path / "evaluation",
        cohort_id="test_cohort",
        cohort_size=24,
        seed=9,
        include_dois=[forced.doi],
        min_domain_papers=1,
    )

    exported_tasks = [json.loads(line) for line in (tmp_path / "evaluation" / "route_extraction_tasks.jsonl").read_text().splitlines()]
    cohort_rows = [json.loads(line) for line in (tmp_path / "evaluation" / "cohort.jsonl").read_text().splitlines()]

    assert manifest["completeness_checks"]["all_selected_review_routes_exported"] is True
    assert len(cohort_rows) == 24
    assert len(exported_tasks) == sum(row["route_count"] for row in cohort_rows)
    assert (tmp_path / "evaluation" / "paper_annotations.csv").exists()
    assert (tmp_path / "evaluation" / "relationship_annotations.csv").exists()
    assert (tmp_path / "evaluation" / "README.md").exists()


def test_build_outputs_can_exclude_an_existing_cohort(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    tasks = synthetic_candidates()
    tasks_path.write_text("".join(json.dumps(task) + "\n" for task in tasks), encoding="utf-8")
    candidates, _ = build_review_candidates(tasks)
    excluded = {candidates[0].doi}

    build_outputs(
        tasks_jsonl=tasks_path,
        out_dir=tmp_path / "evaluation",
        cohort_id="disjoint_cohort",
        cohort_size=24,
        seed=11,
        include_dois=[],
        min_domain_papers=1,
        exclude_dois=sorted(excluded),
    )

    cohort_rows = [
        json.loads(line)
        for line in (tmp_path / "evaluation" / "cohort.jsonl").read_text().splitlines()
    ]
    assert excluded.isdisjoint({row["doi"] for row in cohort_rows})


def test_missing_forced_doi_fails_loudly() -> None:
    candidates, _ = build_review_candidates(synthetic_candidates())
    with pytest.raises(ValueError, match="not eligible"):
        select_review_cohort(
            candidates,
            cohort_size=24,
            seed=1,
            include_dois=["10.1000/missing"],
            min_domain_papers=1,
        )
