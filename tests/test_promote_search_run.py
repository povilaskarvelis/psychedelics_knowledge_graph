import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.discovery.promote_search_run import promote


def write_complete_run(run_dir: Path, *, complete: bool = True) -> None:
    run_dir.mkdir(parents=True)
    manifest = {
        "run_id": "test_run",
        "protocol_id": "protocol_v2",
        "status": "complete" if complete else "paused_budget",
        "completion_gate_passed": complete,
        "mode": "update",
        "coverage_start_date": "2026-06-01",
        "coverage_end_date": "2026-07-15",
        "strategy_hash": "strategy",
        "scope_hash": "scope",
        "scope_snapshot": {"allowed_compounds": ["Psilocybin"]},
        "providers": ["pubmed", "openalex"],
        "datasets": ["mechanistic"],
        "layers": ["core"],
        "advances_standard_update_coverage": True,
        "establishes_scope_baseline": True,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    records = pd.DataFrame(
        [
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:1",
                "doi": "10.1000/existing",
                "pmid": "1",
                "pmcid": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "title": "Existing title",
                "authors": "A Author",
                "publication_year": "2025",
                "publication_date": "2025-01-01",
                "journal": "Journal",
                "publication_type": "article",
                "language": "eng",
                "abstract": "",
                "discovery_search_ids": "search_existing",
                "discovery_execution_ids": "exec_existing",
            },
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W2",
                "doi": "10.1000/new",
                "pmid": "",
                "pmcid": "",
                "openalex_id": "W2",
                "semantic_scholar_id": "",
                "title": "New candidate",
                "authors": "B Author",
                "publication_year": "2026",
                "publication_date": "2026-07-01",
                "journal": "Journal",
                "publication_type": "article",
                "language": "eng",
                "abstract": "New abstract",
                "discovery_search_ids": "search_new",
                "discovery_execution_ids": "exec_new",
            },
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W3",
                "doi": "",
                "pmid": "",
                "pmcid": "",
                "openalex_id": "W3",
                "semantic_scholar_id": "",
                "title": "Older report without DOI",
                "authors": "C Author",
                "publication_year": "1962",
                "publication_date": "1962",
                "journal": "Old Journal",
                "publication_type": "article",
                "language": "eng",
                "abstract": "",
                "discovery_search_ids": "search_old",
                "discovery_execution_ids": "exec_old",
            },
        ]
    )
    records.to_parquet(run_dir / "retrieved_records.parquet", index=False)
    hits = pd.DataFrame(
        [
            {
                "provider_record_id": "pmid:1",
                "doi": "10.1000/existing",
                "compound": "Psilocybin",
                "entity": "5-HT2A",
                "entity_type": "target",
                "search_id": "search_existing",
            },
            {
                "provider_record_id": "openalex:W2",
                "doi": "10.1000/new",
                "compound": "Psilocybin",
                "entity": "5-HT2A",
                "entity_type": "target",
                "search_id": "search_new",
            },
        ]
    )
    hits.to_parquet(run_dir / "provider_hits.parquet", index=False)


def test_promotion_adds_doi_candidates_and_preserves_no_doi_records(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_complete_run(run_dir)
    candidates_path = tmp_path / "candidate_papers.parquet"
    contexts_path = tmp_path / "candidate_contexts.parquet"
    unresolved_path = tmp_path / "unresolved.parquet"
    history_path = tmp_path / "history.json"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/existing",
                "study_title": "Existing title",
                "source_types": "paper_library",
                "source_count": 1,
                "flag_in_discovery_ledger": False,
                "flag_in_discovery_queue": False,
                "flag_in_discovery_report": False,
            }
        ]
    ).to_parquet(candidates_path, index=False)

    report = promote(
        run_dir=run_dir,
        candidates_path=candidates_path,
        contexts_path=contexts_path,
        unresolved_path=unresolved_path,
        history_path=history_path,
    )

    assert report["counts"]["new_candidate_dois"] == 1
    assert report["counts"]["rediscovered_candidate_dois"] == 1
    assert report["counts"]["unresolved_records"] == 1
    candidates = pd.read_parquet(candidates_path).set_index("doi")
    assert set(candidates.index) == {"10.1000/existing", "10.1000/new"}
    assert candidates.loc["10.1000/new", "current_pipeline_status"] == "discovered_pending_metadata"
    assert "living_discovery" in candidates.loc["10.1000/existing", "source_types"]
    unresolved = pd.read_parquet(unresolved_path)
    assert unresolved.loc[0, "openalex_id"] == "W3"
    assert unresolved.loc[0, "resolution_status"] == "needs_identifier_resolution"
    contexts = pd.read_parquet(contexts_path)
    assert len(contexts) == 2
    history = json.loads(history_path.read_text())
    assert history["runs"][0]["status"] == "promoted"
    assert history["runs"][0]["advances_standard_update_coverage"]
    assert history["runs"][0]["establishes_scope_baseline"]
    assert (run_dir / "pre_promotion_backups" / "candidate_papers.parquet").exists()

    second = promote(
        run_dir=run_dir,
        candidates_path=candidates_path,
        contexts_path=contexts_path,
        unresolved_path=unresolved_path,
        history_path=history_path,
    )
    assert second == report


def test_promotion_refuses_incomplete_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_complete_run(run_dir, complete=False)
    candidates = tmp_path / "candidate.parquet"
    pd.DataFrame([{"doi": "10.1000/a"}]).to_parquet(candidates, index=False)

    with pytest.raises(RuntimeError, match="Refusing promotion"):
        promote(run_dir=run_dir, candidates_path=candidates)


def test_promotion_refuses_composite_component(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_complete_run(run_dir)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["promotable_independently"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    candidates = tmp_path / "candidate.parquet"
    pd.DataFrame([{"doi": "10.1000/a"}]).to_parquet(candidates, index=False)

    with pytest.raises(RuntimeError, match="composite baseline"):
        promote(run_dir=run_dir, candidates_path=candidates)
