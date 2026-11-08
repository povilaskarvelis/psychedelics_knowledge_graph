import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.discovery.promote_search_run import canonicalize_records, promote
from pipeline.identity.abstracts import AbstractChecker
from pipeline.discovery import promote_search_run as promotion


def test_canonical_language_prefers_pubmed_over_longer_inferred_label():
    records = pd.DataFrame([
        {"provider": "openalex", "doi": "10.1000/language", "title": "Research on the claustrum", "language": "English"},
        {"provider": "pubmed", "doi": "10.1000/language", "title": "Research on the claustrum", "language": "chi"},
    ])
    assert canonicalize_records(records, AbstractChecker({}, {}, {}))[0]["language"] == "chi"


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


@pytest.mark.parametrize("failure_point", ["contexts", "unresolved", "history", "manifest"])
def test_interrupted_promotion_preserves_handoff_and_original_backup(tmp_path, monkeypatch, failure_point):
    run_dir = tmp_path / "run"
    write_complete_run(run_dir)
    records = pd.read_parquet(run_dir / "retrieved_records.parquet")
    records.loc[0, "abstract"] = (
        "We investigated psilocybin treatment in participants with depression. "
        "Participants received treatment and completed symptom assessments. "
        "The study measured clinical outcomes and adverse events during follow-up. "
        "Symptoms improved after treatment compared with baseline measurements. "
        "These results support further controlled studies to establish efficacy and safety "
        "in larger samples with longer follow-up periods."
    )
    records.to_parquet(run_dir / "retrieved_records.parquet", index=False)
    paths = {key: tmp_path / name for key, name in {
        "candidates_path": "candidates.parquet", "contexts_path": "contexts.parquet",
        "unresolved_path": "unresolved.parquet", "history_path": "history.json",
    }.items()}
    pd.DataFrame([{"doi": "10.1000/existing", "study_title": "Existing title",
                   "source_types": "paper_library", "source_count": 1}]).to_parquet(
        paths["candidates_path"], index=False)
    original = paths["candidates_path"].read_bytes()
    failed_path = {
        "contexts": paths["contexts_path"], "unresolved": paths["unresolved_path"],
        "history": paths["history_path"], "manifest": run_dir / "run_manifest.json",
    }[failure_point]
    parquet_writer = promotion.write_parquet_atomic
    json_writer = promotion.atomic_write_json

    def fail_parquet(path, frame):
        if path == failed_path:
            raise OSError("injected interruption")
        return parquet_writer(path, frame)

    def fail_json(path, payload):
        if path == failed_path:
            raise OSError("injected interruption")
        return json_writer(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(promotion, "write_parquet_atomic", fail_parquet)
        patch.setattr(promotion, "atomic_write_json", fail_json)
        with pytest.raises(OSError, match="injected interruption"):
            promote(run_dir=run_dir, **paths)

    assert "10.1000/new" in set(pd.read_parquet(paths["candidates_path"])["doi"])
    preview = promote(run_dir=run_dir, dry_run=True, **paths)
    assert preview["counts"]["new_candidate_dois"] == 1
    report = promote(run_dir=run_dir, **paths)
    assert report["counts"]["new_candidate_dois"] == 1
    assert report["counts"]["rediscovered_candidate_dois"] == 1
    assert report["counts"]["rediscovered_dois_with_restored_abstract"] == 1
    assert report["counts"]["screening_candidate_dois"] == 2
    assert (run_dir / "new_candidate_dois.txt").read_text() == "10.1000/new\n"
    assert (run_dir / "screening_candidate_dois.txt").read_text() == "10.1000/existing\n10.1000/new\n"
    assert (run_dir / "pre_promotion_backups" / "candidates.parquet").read_bytes() == original
    assert len(pd.read_parquet(paths["contexts_path"])) == 2
    assert len(pd.read_parquet(paths["unresolved_path"])) == 1
    assert len(json.loads(paths["history_path"].read_text())["runs"]) == 1
    assert promote(run_dir=run_dir, **paths) == report


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


def test_canonicalization_prefers_pubmed_abstract_over_long_openalex_text() -> None:
    long_openalex_text = "Introduction Methods Results Discussion References " + ("article text " * 500)
    records = pd.DataFrame(
        [
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W1",
                "doi": "10.1000/shared",
                "openalex_id": "W1",
                "title": "Shared paper",
                "abstract": long_openalex_text,
            },
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:1",
                "doi": "10.1000/shared",
                "pmid": "1",
                "title": "Shared paper",
                "abstract": "The actual bibliographic abstract.",
            },
        ]
    )

    canonical = canonicalize_records(records, AbstractChecker({}, {}, {}))

    assert len(canonical) == 1
    assert canonical[0]["abstract"] == "The actual bibliographic abstract."


def test_canonicalization_drops_contaminated_openalex_only_abstract() -> None:
    records = pd.DataFrame(
        [
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W1",
                "doi": "10.1000/fulltext",
                "openalex_id": "W1",
                "title": "A paper",
                "abstract": "Introduction Methods Results Discussion References " + ("article text " * 500),
            }
        ]
    )

    canonical = canonicalize_records(records, AbstractChecker({}, {}, {}))

    assert canonical[0]["abstract"] == ""


def test_canonicalization_rejects_wrong_openalex_work_joined_by_corrupt_doi() -> None:
    records = pd.DataFrame(
        [
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W2281695666",
                "doi": "10.1007/s00213-022-06272-9",
                "openalex_id": "W2281695666",
                "title": "Sesión del 11 de mayo de 1925",
                "publication_year": "1885",
                "publication_date": "1885-01-01",
            },
            {
                "provider": "openalex",
                "provider_record_id": "openalex:W4309412689",
                "doi": "10.1007/s00213-022-06272-9",
                "openalex_id": "W4309412689",
                "title": "The effect of ketamine and D-cycloserine on the high frequency resting EEG spectrum in humans",
                "publication_year": "2022",
                "publication_date": "2022-11-19",
            },
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:36401646",
                "doi": "10.1007/s00213-022-06272-9",
                "pmid": "36401646",
                "title": "The effect of ketamine and D-cycloserine on the high frequency resting EEG spectrum in humans",
                "publication_year": "2023",
                "publication_date": "2023-01-01",
            },
        ]
    )

    canonical = canonicalize_records(records, AbstractChecker({}, {}, {}))

    assert len(canonical) == 1
    assert canonical[0]["title"].startswith("The effect of ketamine")
    assert canonical[0]["publication_year"] == "2023"
    assert canonical[0]["publication_date"] == "2023-01-01"
    assert canonical[0]["openalex_id"] == "W4309412689"
    assert canonical[0]["pmid"] == "36401646"


ABSTRACT_WORDS = " ".join(f"term{index}" for index in range(60))


def test_fields_come_from_one_record_and_another_works_abstract_is_not_used() -> None:
    # OpenAlex built work W37597153 from PubMed record 37597153 and attached another article's title and abstract.
    doi = "10.1007/s12325-023-02623-w"
    records = pd.DataFrame([
        {"provider": "openalex", "provider_record_id": "openalex:W37597153", "doi": doi, "openalex_id": "W37597153",
         "title": "Ketamine and resting-state connectivity", "publication_year": "2011", "authors": "Ketamine A",
         "abstract": "Ketamine altered connectivity. " + ABSTRACT_WORDS},
        {"provider": "pubmed", "provider_record_id": "pmid:37597153", "doi": doi, "pmid": "37597153",
         "title": "Cost of CAR-T cell therapy in multiple myeloma", "publication_year": "2023", "authors": "Myeloma B"},
    ])
    [row] = canonicalize_records(records, AbstractChecker({}, {}, {}))
    assert (row["title"], row["publication_year"], row["authors"]) == (
        "Cost of CAR-T cell therapy in multiple myeloma", "2023", "Myeloma B",
    )
    assert row["abstract"] == ""


def test_a_legacy_openalex_record_alone_supplies_no_abstract() -> None:
    def record(work: str) -> dict:
        return {"provider": "openalex", "provider_record_id": f"openalex:{work}", "doi": "10.1016/j.jad.2020.01.001",
                "openalex_id": work, "title": "Psilocybin for depression", "abstract": ABSTRACT_WORDS}

    legacy = canonicalize_records(pd.DataFrame([record("W37597153")]), AbstractChecker({}, {}, {}))
    current = canonicalize_records(pd.DataFrame([record("W4309412689")]), AbstractChecker({}, {}, {}))
    assert legacy[0]["abstract"] == "" and legacy[0]["title"] == "Psilocybin for depression"
    assert current[0]["abstract"] == ABSTRACT_WORDS


def test_a_doi_that_names_no_work_is_not_promoted() -> None:
    records = pd.DataFrame([{"provider": "openalex", "provider_record_id": "openalex:W1", "doi": "10.13039/501100000780",
                             "openalex_id": "W1", "title": "Ketamine and dorsal raphe stimulation"}])
    [row] = canonicalize_records(records, AbstractChecker({}, {}, {}))
    assert row["doi"] == "" and row["resolution_status"] == "doi_names_no_work:funder:10.13039/501100000780"


def test_rediscovery_fills_blank_fields_only_from_the_same_work() -> None:
    candidates = pd.DataFrame([{"doi": "10.1016/j.jad.2020.01.001", "study_title": "Psilocybin for depression",
                                "authors": "", "source_types": "", "abstract": ""}])
    other_work = {"doi": "10.1016/j.jad.2020.01.001", "title": "Cost of CAR-T cell therapy", "authors": "Other A"}
    same_work = {**other_work, "title": "Psilocybin for depression", "authors": "Same B"}
    merged, _, _ = promotion.merge_candidates(candidates, [other_work], run_id="r", protocol_id="p", promoted_at="t")
    assert merged.loc[0, "authors"] == ""
    merged, _, _ = promotion.merge_candidates(candidates, [same_work], run_id="r", protocol_id="p", promoted_at="t")
    assert merged.loc[0, "authors"] == "Same B"
