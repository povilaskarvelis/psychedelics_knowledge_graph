from pathlib import Path

import pandas as pd

from pipeline.discovery.run_citation_expansion import (
    CitationClient,
    build_parser,
    load_seeds,
    run,
)


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params or {}})
        return self.responses.pop(0)


def test_citing_expansion_reconciles_the_provider_count() -> None:
    work = {
        "id": "https://openalex.org/W2",
        "doi": "https://doi.org/10.1000/citing",
        "display_name": "Citing report",
        "ids": {"openalex": "https://openalex.org/W2"},
    }
    http = FakeHttpClient(
        [
            {"meta": {"count": 1}, "results": []},
            {"meta": {"next_cursor": None}, "results": [work]},
        ]
    )
    provider = CitationClient(http, api_key="secret")

    records = provider.citing(
        "W1",
        from_date="2026-01-01",
        to_date="2026-12-31",
        maximum=10,
    )

    assert len(records) == 1
    assert http.calls[0]["params"]["filter"].startswith("cites:W1")
    assert http.calls[1]["params"]["cursor"] == "*"


def test_plan_only_uses_reviewed_seeds_and_stays_bounded(tmp_path: Path) -> None:
    seeds_path = tmp_path / "candidate_papers.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/known",
                "openalex_id": "https://openalex.org/W1",
                "study_title": "Known report",
                "flag_in_known_study_set": True,
            },
            {
                "doi": "10.1000/not-reviewed",
                "openalex_id": "https://openalex.org/W9",
                "study_title": "Unreviewed report",
                "flag_in_known_study_set": False,
            },
        ]
    ).to_parquet(seeds_path, index=False)
    args = build_parser().parse_args(
        [
            "--run-id", "citation_plan",
            "--run-root", str(tmp_path / "runs"),
            "--seed-source", str(seeds_path),
            "--seed-flag-column", "flag_in_known_study_set",
            "--max-seeds", "1",
            "--directions", "references,citing",
            "--from-date", "2000-01-01",
            "--to-date", "2026-12-31",
            "--plan-only",
        ]
    )

    manifest = run(args)

    assert manifest["status"] == "planned"
    assert manifest["counts"]["seeds"] == 1
    assert manifest["counts"]["query_executions"] == 2
    plan = pd.read_parquet(tmp_path / "runs" / "citation_plan" / "search_plan.parquet")
    assert set(plan["direction"]) == {"references", "citing"}


def test_cli_requires_explicit_seed_cohort_and_bound() -> None:
    parser = build_parser()
    try:
        parser.parse_args(["--run-id", "citation_plan"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("citation expansion accepted an implicit seed cohort")


def test_seed_loader_honors_maximum(tmp_path: Path) -> None:
    path = tmp_path / "seeds.parquet"
    pd.DataFrame(
        [
            {"doi": f"10.1000/{index}", "openalex_id": f"W{index}", "flag": True}
            for index in range(5)
        ]
    ).to_parquet(path, index=False)

    seeds = load_seeds(path, flag_column="flag", max_seeds=2)

    assert len(seeds) == 2
