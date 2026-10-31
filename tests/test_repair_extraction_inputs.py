import copy
from pipeline.extract.repair_extraction_inputs import source_repair_decision, plan_recovery, repository_abstract


def test_source_holds_are_projected_to_ledger_and_all_routes_idempotently(tmp_path):
    import json
    import pandas as pd
    from pipeline.extract.repair_extraction_inputs import reconcile_source_holds
    owner = tmp_path / "pipeline/extract/manual_extraction_route_overrides.json"
    owner.parent.mkdir(parents=True)
    owner.write_text(json.dumps({"records": [{"doi": "10.1000/held", "manual_action": "hold_source_review", "manual_reason": "Report mismatch"}]}))
    corpus = tmp_path / "data/processed/corpus"
    corpus.mkdir(parents=True)
    candidates = pd.DataFrame([{"doi": doi, "retained_for_extraction_candidate": True,
                                "extraction_route_status": "ready_for_abstract_extraction", "screening_decision": "include_in_scope"}
                               for doi in ("10.1000/held", "10.1000/unaffected")])
    candidates.to_parquet(corpus / "candidate_papers.parquet", index=False)
    routes = pd.DataFrame([{"doi": doi, "route_id": str(i), "route_action": "extract_from_abstract_only",
                           "retained_for_extraction_candidate": True, "domain_screening_decision": "include_in_scope"}
                          for i, doi in enumerate(("10.1000/held", "10.1000/held", "10.1000/unaffected"))])
    routes.to_parquet(corpus / "paper_extraction_routes.parquet", index=False)
    result = reconcile_source_holds(tmp_path)
    assert result["route_rows_changed"] == 2
    actual = pd.read_parquet(corpus / "candidate_papers.parquet")
    assert not actual.iloc[0]["retained_for_extraction_candidate"]
    assert actual.iloc[1]["retained_for_extraction_candidate"]
    assert actual["screening_decision"].tolist() == candidates["screening_decision"].tolist()
    actual_routes = pd.read_parquet(corpus / "paper_extraction_routes.parquet")
    pd.testing.assert_series_equal(actual_routes.iloc[2], routes.iloc[2])
    assert reconcile_source_holds(tmp_path)["route_rows_changed"] == 0


def evidence():
    task = {"study_doi": "10.1000/a"}
    native = {"pmid": "1", "dois": ["10.1000/a"], "title": "Actual report title",
              "abstract": "Authentic study abstract"}
    cr = {"title": ["Actual report title"]}
    return task, native, cr


def test_exact_doi_without_title_agreement_cannot_repair():
    t, n, c = evidence()
    c["title"] = ["Unrelated report on entirely different topic"]
    assert source_repair_decision(t, n, c)["action"] == "hold_source_review"


def test_missing_native_abstract_does_not_authenticate_foreign_provider_text():
    t, n, c = evidence()
    n["abstract"] = ""
    assert source_repair_decision(t, n, c)["action"] == "hold_source_review"


def test_native_doi_must_match_even_when_titles_agree():
    t, n, c = evidence()
    n["dois"] = ["10.1000/b"]
    assert source_repair_decision(t, n, c)["action"] == "hold_source_review"


def test_repair_preserves_identifiers_and_authentic_abstract():
    t, n, c = evidence()
    result = source_repair_decision(t, n, c)
    assert result["action"] == "repair_verified_metadata"
    assert result["fields"]["abstract"] == n["abstract"]
    assert result["doi"] == t["study_doi"]


def test_source_hold_covers_passing_sibling_routes_and_does_not_mutate_tasks():
    t, n, c = evidence()
    tasks = [{**t, "task_id": str(i), "route_id": str(i), "paper_metadata": {"pmid": "1"}} for i in range(2)]
    before = copy.deepcopy(tasks)
    n["abstract"] = ""
    failures = [{"study_doi": t["study_doi"], "route_id": "0", "error": "source-identity mismatch"}]
    result = plan_recovery(tasks, failures, {"1": n}, [{**c, "doi": t["study_doi"]}], "now")
    assert len(result["held_routes"]) == 2
    assert not result["retry_tasks"]
    assert tasks == before


def test_repository_requires_report_specific_identity_and_abstract(tmp_path):
    import pytest
    p = tmp_path / "source.html"
    p.write_text('<meta name="description" content="Not an abstract">')
    with pytest.raises(ValueError):
        repository_abstract(p)


def test_repository_abstract_must_match_native_identity():
    t, n, c = evidence()
    n["abstract"] = ""
    repo = {"doi": "10.1000/wrong", "title": n["title"], "abstract": "Foreign text"}
    assert source_repair_decision(t, n, c, repo)["action"] == "hold_source_review"


def test_materialization_withholds_passing_route_for_source_held_report(tmp_path, monkeypatch):
    import json
    from pipeline.extract import run_route_extraction_batch_api as batch
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    owner = tmp_path / "pipeline/extract/manual_extraction_route_overrides.json"
    owner.parent.mkdir(parents=True)
    owner.write_text(json.dumps({"records": [{"doi": "10.1000/held", "manual_action": "hold_source_review"}]}))
    run = tmp_path / "run"
    run.mkdir()
    rows = [{"route_id": "bad", "study_doi": "10.1000/held", "status": "ok"},
            {"route_id": "good", "study_doi": "10.1000/good", "status": "ok"}]
    for filename in ("route_extraction_raw.jsonl", "route_extraction_outputs.jsonl"):
        (run / filename).write_text("".join(json.dumps(r) + "\n" for r in rows))
    batch.materialize_run_projection_from_batch_files(run)
    raw = [json.loads(x) for x in (run / "route_extraction_raw.jsonl").read_text().splitlines()]
    outputs = [json.loads(x) for x in (run / "route_extraction_outputs.jsonl").read_text().splitlines()]
    assert raw[0]["status"] == "source_hold"
    assert raw[0]["pre_source_hold_status"] == "ok"
    assert [r["route_id"] for r in outputs] == ["good"]


def test_materialization_does_not_republish_old_input_after_source_repair(tmp_path, monkeypatch):
    import json
    from pipeline.extract import run_route_extraction_batch_api as batch
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    old = {"route_id": "r", "input_fingerprint": "old", "status": "ok"}
    for name in ("route_extraction_raw.jsonl", "route_extraction_outputs.jsonl"):
        (run / name).write_text(json.dumps(old) + "\n")
    (run / "input_replacements.json").write_text(json.dumps({"routes": [{"route_id": "r", "replacement_fingerprint": "new"}]}))
    batch.materialize_run_projection_from_batch_files(run)
    assert not (run / "route_extraction_outputs.jsonl").read_text()
    assert json.loads((run / "route_extraction_raw.jsonl").read_text())["status"] == "source_repair_pending"


def test_collector_replays_existing_parse_without_network_or_submission(tmp_path, monkeypatch):
    import json
    from pipeline import llm
    from pipeline.extract.repair_extraction_inputs import collect_retry
    monkeypatch.setattr(llm, "client", lambda *a: (_ for _ in ()).throw(AssertionError("network prohibited")))
    job, report = tmp_path / "job.json", tmp_path / "parsed.json"
    job.write_text(json.dumps({"job_name": "existing-job"}))
    report.write_text(json.dumps({"summary": {"status_counts": {"ok": 1}}}))
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"run_id": "r", "batch_id": "batch_1", "tasks_path": str(tmp_path / "tasks"),
                                  "paths": {"job_json": str(job), "parse_report_json": str(report)}}))
    result = collect_retry(receipt)
    assert result["status"] == "parsed"
    assert result["summary"]["status_counts"] == {"ok": 1}


def test_registry_collection_uses_native_fields_and_retains_wrong_id_for_gate(tmp_path):
    import json
    from pipeline.extract.repair_extraction_inputs import collect_registry_evidence
    xml = tmp_path / "native.xml"
    xml.write_text('''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>
    <Article><ArticleTitle>Actual report title</ArticleTitle><Abstract><AbstractText>Native findings</AbstractText></Abstract>
    <Journal><Title>Native journal</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
    <Language>eng</Language></Article></MedlineCitation><PubmedData><ArticleIdList>
    <ArticleId IdType="doi">10.1000/wrong</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>''')
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "crossref.json").write_text(json.dumps({"message": {"DOI": "10.1000/a", "title": ["Actual report title"]}}))
    tasks = [{"study_doi": "10.1000/a", "paper_metadata": {"pmid": "1", "abstract": "Foreign findings", "pmcid": "BAD"}}]
    out = tmp_path / "evidence"
    result = collect_registry_evidence(tasks, out, pubmed_xml_paths=[xml], crossref_cache=cache, offline=True)
    assert result["native_records"] == 1
    native = json.loads((out / "native_records.json").read_text())["1"]
    assert native["abstract"] == "Native findings"
    assert native["pmcid"] == ""
    assert native["dois"] == ["10.1000/wrong"]
    assert source_repair_decision(tasks[0], native, {"title": ["Actual report title"]})["action"] == "hold_source_review"
