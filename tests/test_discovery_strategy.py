import datetime as dt
from copy import deepcopy
import json
from pathlib import Path

from pipeline.discovery.strategy import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_STRATEGY_PATH,
    build_definitions,
    build_search_plan,
    load_strategy,
    openalex_compound_identity_query,
    openalex_compound_terms,
    parse_validation_allowlists,
)


def test_first_update_uses_overlap_and_recovers_exact_post_baseline_compound_delta(tmp_path: Path) -> None:
    plan, metadata = build_search_plan(
        strategy_path=DEFAULT_STRATEGY_PATH,
        config_path=DEFAULT_CONFIG_PATH,
        history_path=tmp_path / "missing_history.json",
        mode="update",
        providers=["pubmed", "openalex"],
        datasets=["mechanistic", "disorder", "general"],
        layers=["core", "scope"],
        end_date="2026-07-15",
        today=dt.date(2026, 7, 15),
    )

    assert metadata["coverage_start_date"] == "2026-05-14"
    assert metadata["coverage_end_date"] == "2026-07-15"
    assert not metadata["include_openalex_index_updates"]
    assert metadata["openalex_index_update_limitation"]
    assert metadata["scope_delta"]["allowed_compounds"] == [
        "4-AcO-DMT",
        "4-HO-MET",
        "4-HO-MiPT",
        "5-MeO-MiPT",
        "DOC",
        "2C-C",
        "2C-D",
        "2C-P",
        "25CN-NBOH",
        "Alpha-methyltryptamine",
        "25I-NBOH",
        "25B-NBOH",
        "25C-NBOH",
    ]
    delta_rows = [row for row in plan if row.layer == "scope_delta"]
    assert delta_rows
    assert len(delta_rows) == 26
    assert {row.search_type for row in delta_rows} == {"historical_compound_identity"}
    assert {row.dataset for row in delta_rows} == {"general"}
    assert {row.start_date for row in delta_rows} == {"1800-01-01"}
    assert {row.date_basis for row in delta_rows} == {"publication"}
    assert {row.date_basis for row in plan if row.provider == "openalex"} == {"publication"}
    assert "entrez" in {row.date_basis for row in plan if row.provider == "pubmed"}
    assert metadata["advances_standard_update_coverage"]
    assert metadata["establishes_scope_baseline"]


def test_promoted_history_advances_update_window_with_overlap(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "prior",
                        "protocol_id": "psychedelics_kg_living_search_v3",
                        "status": "promoted",
                        "advances_standard_update_coverage": True,
                        "establishes_scope_baseline": True,
                        "coverage_end_date": "2026-07-01",
                        "strategy_hash": "prior_strategy_hash",
                        "scope_snapshot": parse_validation_allowlists(DEFAULT_CONFIG_PATH),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _plan, metadata = build_search_plan(
        history_path=history,
        mode="update",
        providers=["pubmed"],
        datasets=["mechanistic"],
        layers=["core"],
        end_date="2026-07-15",
    )

    assert metadata["coverage_start_date"] == "2026-06-17"
    assert not any(metadata["scope_delta"].values())
    assert not metadata["advances_standard_update_coverage"]
    assert metadata["strategy_changed_since_last_promoted"]
    assert metadata["historical_recovery_recommended"]


def test_partial_promoted_run_does_not_advance_standard_update_window(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "partial",
                        "protocol_id": "psychedelics_kg_living_search_v3",
                        "status": "promoted",
                        "coverage_end_date": "2026-07-01",
                        "advances_standard_update_coverage": False,
                        "establishes_scope_baseline": False,
                        "scope_snapshot": parse_validation_allowlists(DEFAULT_CONFIG_PATH),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _plan, metadata = build_search_plan(
        history_path=history,
        mode="update",
        providers=["pubmed"],
        datasets=["mechanistic"],
        layers=["core"],
        end_date="2026-07-15",
    )

    assert metadata["coverage_start_date"] == "2026-05-14"
    assert metadata["scope_delta"]["allowed_compounds"]
    assert not metadata["advances_standard_update_coverage"]


def test_provider_queries_use_provider_specific_surfaces_and_explicit_targeted_pairs() -> None:
    strategy = deepcopy(load_strategy(DEFAULT_STRATEGY_PATH))
    strategy["targeted_pairs"] = [
        {
            "compound": "DOI",
            "entity_type": "target",
            "entity": "5-HT2A",
            "rationale": "Known-relevant miss requiring a focused provider query.",
        }
    ]
    scope = parse_validation_allowlists(DEFAULT_CONFIG_PATH)
    definitions, _delta = build_definitions(
        strategy,
        scope,
        providers=["pubmed", "openalex"],
        layers=["core", "targeted_pairs"],
        history={"runs": [{"status": "promoted", "scope_snapshot": scope}]},
        include_scope_delta=False,
    )

    pubmed_core = next(row for row in definitions if row.provider == "pubmed" and row.layer == "core")
    assert "[Text Word]" in pubmed_core.query
    assert "[MeSH Terms]" in pubmed_core.query

    pubmed_doi = next(
        row
        for row in definitions
        if row.provider == "pubmed" and row.layer == "targeted_pairs" and row.compound == "DOI"
    )
    assert "2,5-dimethoxy-4-iodoamphetamine" in pubmed_doi.query
    assert "DOI[Text Word]" not in pubmed_doi.query

    openalex_pair = next(
        row
        for row in definitions
        if row.provider == "openalex" and row.layer == "targeted_pairs" and row.compound == "DOI"
    )
    assert openalex_pair.search_surface == "title_and_abstract"
    assert all(
        row.search_surface == "title_and_abstract"
        for row in definitions
        if row.provider == "openalex"
    )
    assert "," not in openalex_pair.query
    assert max(
        len(row.query) for row in definitions if row.provider == "openalex"
    ) <= strategy["providers"]["openalex"]["max_search_query_chars"]

    pairs = [row for row in definitions if row.layer == "targeted_pairs"]
    assert len(pairs) == 2
    assert {row.module_id for row in pairs} == {"targeted_target_pair"}


def test_openalex_alias_policy_removes_spaced_short_codes() -> None:
    aliases = openalex_compound_terms("2C-C")
    assert "2C-C" in aliases
    assert "2c c" not in aliases
    assert "4-chloro-2,5-dimethoxyphenethylamine" in aliases
    assert "DOC" not in openalex_compound_terms("DOC")
    assert "2,5-dimethoxy-4-chloroamphetamine" in openalex_compound_terms("DOC")
    doc_query = openalex_compound_identity_query(load_strategy(DEFAULT_STRATEGY_PATH), "DOC")
    assert "DOC AND" in doc_query
    assert "chloroamphetamine" in doc_query


def test_standard_plans_do_not_generate_a_cartesian_pair_grid(tmp_path: Path) -> None:
    update, update_metadata = build_search_plan(
        history_path=tmp_path / "missing.json",
        mode="update",
        end_date="2026-07-15",
    )
    full, full_metadata = build_search_plan(
        history_path=tmp_path / "missing.json",
        mode="full",
        end_date="2026-07-15",
    )

    assert len(update) == 371
    assert len(full) == 232
    assert not any(row.layer == "targeted_pairs" for row in update + full)
    assert not update_metadata["query_generation_policy"]["automatic_pair_grid"]
    assert not full_metadata["query_generation_policy"]["automatic_pair_grid"]
    assert {row.search_surface for row in update if row.provider == "openalex"} == {
        "title_and_abstract"
    }


def test_plan_size_guard_blocks_accidental_query_explosion(tmp_path: Path) -> None:
    strategy = deepcopy(load_strategy(DEFAULT_STRATEGY_PATH))
    strategy["planning"]["max_query_executions"] = 10
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps(strategy), encoding="utf-8")

    try:
        build_search_plan(
            strategy_path=path,
            history_path=tmp_path / "missing.json",
            mode="full",
            end_date="2026-07-15",
        )
    except ValueError as error:
        assert "max_query_executions=10" in str(error)
    else:
        raise AssertionError("Expected the plan-size guard to reject the oversized plan")


def test_full_plan_does_not_duplicate_scope_delta_layer(tmp_path: Path) -> None:
    plan, metadata = build_search_plan(
        history_path=tmp_path / "missing.json",
        mode="full",
        providers=["pubmed"],
        datasets=["mechanistic"],
        layers=["core", "scope"],
        end_date="2026-07-15",
    )

    assert plan
    assert not any(row.layer == "scope_delta" for row in plan)
    assert metadata["execution_counts"]["by_layer"]["scope_delta"] == 0
