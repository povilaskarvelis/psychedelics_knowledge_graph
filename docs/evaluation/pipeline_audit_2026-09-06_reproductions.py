"""Offline diagnostic reproductions for the 6 September 2026 pipeline audit.

These assert the observed defects, not the desired behavior. They use temporary
fixtures and mocked network clients; they never modify corpus or release data.
Run from any directory with the project's Python environment.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd


def jats_information_loss() -> dict:
    from pipeline.fulltext.build_llm_evidence_packets import build_packet
    from pipeline.extract.io_utils import text_parts_from_packet

    xml = """<article><front><article-meta><abstract><p>Study abstract.</p>
    </abstract></article-meta></front><body><sec><title>Results</title>
    <p>Results are shown in Table 1 and Figure 1.</p>
    <table-wrap id="t1"><label>Table 1</label><caption><p>Values in milliseconds.</p></caption>
    <table><tr><th>Arm</th><th>Change</th></tr><tr><td>A</td><td>5</td></tr></table>
    <table-wrap-foot><fn><p>Negative values denote improvement.</p></fn></table-wrap-foot>
    </table-wrap><fig id="f1"><label>Figure 1</label>
    <caption><p>No difference from placebo.</p></caption></fig></sec></body></article>"""
    artifact = {"study_doi": "10.1000/jats", "best_backend": "europepmc_fulltext_xml",
                "extractions": [{"backend": "europepmc_fulltext_xml", "status": "ok",
                                 "text": xml, "metadata": {"format": "jats_xml"}}]}
    packet = build_packet("articles", Path("fixture.json"), artifact, {},
                          max_chunk_chars=4000, overlap_chars=0,
                          max_chunks_per_paper=0, max_references=100, packet_profile="full")
    text = "\n".join(text_parts_from_packet(packet))
    omitted = [s for s in ["Values in milliseconds.", "Negative values denote improvement.",
                           "No difference from placebo."] if s not in text]
    assert len(packet["tables"]) == 1 and len(packet["figures"]) == 0 and len(omitted) == 3
    return {"tables": len(packet["tables"]), "figures": len(packet["figures"]),
            "omitted_source_passages": omitted, "model_input": text}


def scoped_route_table_replacement() -> dict:
    from pipeline.extract.build_extraction_routes import build_extraction_routes

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dois = ["10.1000/a", "10.1000/b"]
        (root / "screening.json").write_text('{"overrides": []}')
        pd.DataFrame([{"doi": d, "study_title": "Psychedelic trial", "abstract": "Trial abstract.",
                       "publication_type": "Journal Article"} for d in dois]).to_parquet(root / "c.parquet")
        pd.DataFrame([{"doi": d, "prescreen_decision": "retain",
                       "retained_for_extraction_candidate": True} for d in dois]).to_parquet(root / "p.parquet")
        pd.DataFrame([{"doi": d, "retained_for_extraction_candidate": True,
                       "screening_decision": "include_in_scope", "domain_route": "clinical_outcome",
                       "all_domain_tags": "clinical_outcome", "paper_type_group": "primary",
                       "paper_type": "primary"} for d in dois]).to_parquet(root / "d.parquet")
        kwargs = dict(candidate_table=root / "c.parquet", metadata_table=root / "missing.parquet",
                      prescreen_table=root / "p.parquet", domain_table=root / "d.parquet",
                      manual_overrides_path=None, screening_overrides_path=root / "screening.json",
                      manual_fulltext_access_overrides_path=None, doi_alias_registry_path=None,
                      fulltext_dir=root / "fulltext", paper_root=root / "papers",
                      output_table=root / "routes.parquet", summary_json=root / "summary.json",
                      counts_csv=root / "counts.csv", update_candidate_table=False)
        build_extraction_routes(**kwargs)
        before = pd.read_parquet(root / "routes.parquet")["doi"].tolist()
        build_extraction_routes(**kwargs, scoped_dois={dois[0]})
        after = pd.read_parquet(root / "routes.parquet")["doi"].tolist()
        assert set(before) == set(dois) and set(after) == {dois[0]}
        return {"before_dois": before, "after_scoped_build_dois": after}


def interrupted_discovery_promotion() -> dict:
    import pipeline.discovery.promote_search_run as module
    from test_promote_search_run import write_complete_run

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run = root / "run"
        write_complete_run(run)
        candidate = root / "candidate.parquet"
        contexts = root / "contexts.parquet"
        pd.DataFrame([{"doi": "10.1000/existing", "study_title": "Existing title",
                       "source_types": "paper_library", "source_count": 1}]).to_parquet(candidate)
        kwargs = dict(run_dir=run, candidates_path=candidate, contexts_path=contexts,
                      unresolved_path=root / "unresolved.parquet", history_path=root / "history.json")
        real_write = module.write_parquet_atomic

        def fail_context_write(path, frame):
            if path == contexts:
                raise OSError("injected interruption after candidate commit")
            return real_write(path, frame)

        with patch.object(module, "write_parquet_atomic", side_effect=fail_context_write):
            try:
                module.promote(**kwargs)
            except OSError:
                pass
            else:
                raise AssertionError("Failure injection did not run")
        after_interruption = pd.read_parquet(candidate)["doi"].tolist()
        report = module.promote(**kwargs)
        handoff = (run / "new_candidate_dois.txt").read_text()
        backup = pd.read_parquet(run / "pre_promotion_backups" / candidate.name)["doi"].tolist()
        assert "10.1000/new" in after_interruption and handoff == ""
        assert "10.1000/new" in backup
        return {"after_interruption": after_interruption, "retry_counts": report["counts"],
                "retry_new_candidate_dois_file": handoff, "backup_after_retry": backup}


def batch_model_mismatch() -> dict:
    import pipeline.extract.run_route_extraction_batch_api as module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = {"requests_jsonl": root / "requests.jsonl", "manifest_json": root / "manifest.json",
                 "job_json": root / "job.json"}
        paths["requests_jsonl"].write_text("{}\n")
        expected = "task-configured-model"
        paths["manifest_json"].write_text(json.dumps({"records": [{"model": expected}]}))
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(name="jobs/fake", model_dump=lambda **_: {"name": "jobs/fake"})

        client = SimpleNamespace(
            files=SimpleNamespace(upload=lambda **_: SimpleNamespace(
                name="files/fake", model_dump=lambda **_: {"name": "files/fake"})),
            batches=SimpleNamespace(create=create))
        args = SimpleNamespace(model="", run_id="audit", batch_id="batch_001", display_name="audit")
        with patch.object(module, "batch_paths", return_value=paths), \
             patch.object(module, "api_key_from_env", return_value="fake"), \
             patch.object(module.genai, "Client", return_value=client):
            module.submit_batch(args)
        assert captured["model"] != expected
        return {"manifest_model": expected, "submitted_model": captured["model"]}


def repeated_stale_reprocessing() -> dict:
    from pipeline.extract.run_routed_extraction_batch import (
        attempted_task_keys, stale_input_fingerprint_task_keys,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows = [{"route_id": "r1", "task_id": "old", "input_fingerprint": "old", "status": "ok"},
                {"route_id": "r1", "task_id": "new", "input_fingerprint": "new", "status": "ok"}]
        for filename in ["route_extraction_outputs.jsonl", "route_extraction_raw.jsonl"]:
            (root / filename).write_text("".join(json.dumps(row) + "\n" for row in rows))
        task = {"route_id": "r1", "task_id": "new", "input_fingerprint": "new"}
        attempted = attempted_task_keys(root)
        stale = stale_input_fingerprint_task_keys(root, [task])
        effective = attempted - stale
        assert "r1" not in effective
        return {"latest_output_matches_current_task": True, "stale_routes": sorted(stale),
                "effective_completed_routes": sorted(effective)}


def mutable_secondary_packet() -> dict:
    from pipeline.extract.build_review_relationship_tasks import build_task, packet_text_fingerprint
    from pipeline.extract.run_review_relationship_extraction import source_text_for_task
    from pipeline.extract.run_meta_analysis_v2_batch_api import source_text_for_task as meta_source_text

    cohort = {"doi": "10.1000/packet", "text_depth": "article_text", "review_type": "review"}
    packet = {"packet_id": "articles:10.1000/packet", "study_doi": "10.1000/packet",
              "llm_chunks": [{"text": "Original source text."}]}
    task = build_task(cohort, {}, packet, Path("packets.jsonl"))
    changed = {**packet, "llm_chunks": [{"text": "Replacement source text."}]}
    current_hash, _ = packet_text_fingerprint(changed)
    review_text = source_text_for_task(task, changed)
    meta_text = meta_source_text(task, changed)
    assert current_hash != task["source"]["source_fingerprint"]
    assert "Replacement source text." in review_text and "Replacement source text." in meta_text
    return {"saved_source_fingerprint": task["source"]["source_fingerprint"],
            "actual_source_fingerprint": current_hash,
            "review_accepts_changed_source": True, "meta_accepts_changed_source": True}


def concurrent_candidate_updates() -> dict:
    import pipeline.ingest.candidate_status as module

    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "candidate.parquet"
        pd.DataFrame([{"doi": "10.1000/a", "value": "old"},
                      {"doi": "10.1000/b", "value": "old"}]).to_parquet(candidate)
        real_read = pd.read_parquet
        barrier = threading.Barrier(2)

        def synchronized_read(path, *args, **kwargs):
            frame = real_read(path, *args, **kwargs)
            if Path(path) == candidate:
                barrier.wait(timeout=10)
            return frame

        def update(doi):
            return module.apply_candidate_updates(candidate_table=candidate,
                updates=pd.DataFrame([{"doi": doi, "value": "new"}]))

        with patch.object(module.pd, "read_parquet", side_effect=synchronized_read):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports = list(pool.map(update, ["10.1000/a", "10.1000/b"]))
        final = real_read(candidate).to_dict("records")
        written = sum(row["value"] == "new" for row in final)
        assert written == 1 and all(report["updated_cells"] == 1 for report in reports)
        return {"successful_updates_reported": 2, "updates_persisted": written,
                "final_rows": final}


def schema_errors_not_retried() -> dict:
    from pipeline.extract.run_routed_extraction_batch import attempted_task_keys
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        row = {"route_id": "schema-failure", "task_id": "t1", "status": "schema_error"}
        for name in ["route_extraction_outputs.jsonl", "route_extraction_raw.jsonl"]:
            (root / name).write_text(json.dumps(row) + "\n")
        attempted = attempted_task_keys(root, retry_errors=True)
        assert "schema-failure" in attempted
        return {"retry_errors": True, "excluded_from_retry": sorted(attempted)}


def missing_batch_results_report_success() -> dict:
    import pipeline.extract.run_route_extraction_batch_api as module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        batch = root / "async_batches"
        batch.mkdir()
        paths = {"batch_dir": batch,
                 **{name: batch / filename for name, filename in {
                     "manifest_json": "batch_001_manifest.json",
                     "results_jsonl": "batch_001_results.jsonl",
                     "batch_raw_jsonl": "batch_001_raw.jsonl",
                     "batch_outputs_jsonl": "batch_001_outputs.jsonl",
                     "parse_report_json": "batch_001_parse_report.json",
                 }.items()}}
        paths["manifest_json"].write_text(json.dumps({"records": [
            {"key": "one", "task_id": "t1", "route_id": "r1"}]}))
        tasks_path = root / "tasks.jsonl"
        tasks_path.write_text(json.dumps({"task_id": "t1", "route_id": "r1"}) + "\n")
        run_paths = {"run_dir": root, "raw_jsonl": root / "route_extraction_raw.jsonl",
                     "outputs_jsonl": root / "route_extraction_outputs.jsonl"}
        args = SimpleNamespace(input_jsonl=tasks_path, env_file=root / "missing.env",
                               skip_rebuild=True, run_id="audit", batch_id="batch_001")
        with patch.object(module, "batch_paths", return_value=paths), \
             patch.object(module, "appendable_output_paths", return_value=run_paths):
            report = module.parse_batch_results(args)
        assert report["status"] == "ok" and report["summary"]["batch_result_rows"] == 0
        reserved = module.reserved_manifest_task_keys(batch)
        assert "r1" in reserved
        return {"expected_results": 1, "result_file_exists": False,
                "parsed_results": report["summary"]["batch_result_rows"],
                "reported_status": report["status"], "still_reserved_routes": sorted(reserved)}


def active_run_build_gate() -> dict:
    import pipeline.kg.build_evidence_tables as module

    # All build writes are replaced before the real CLI is invoked.
    active = json.loads((ROOT / "data/processed/extraction/active_routed_run.json").read_text())
    with patch.object(sys, "argv", ["build_evidence_tables.py", "--source-preset", "routed",
                                   "--run-id", active["run_id"]]), \
         patch.object(module, "build_tables", return_value={
             "source_preset": "routed", "tables": {}, "duckdb": {"status": "mocked"}
         }) as build:
        module.main()
    output_path = Path(build.call_args.kwargs["out_dir"]).resolve()
    assert output_path == (ROOT / active["kg_dir"]).resolve()
    return {"active_run_id": active["run_id"], "active_output_directory_accepted": True,
            "allow_current_overwrite_flag_supplied": False, "build_writes_mocked": True}


def worklist_conversion_omits_audit_refresh() -> dict:
    from collections import Counter
    import pipeline.fulltext.convert_routed_local_pdfs as module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        doi = "10.1000/convert"
        selection = root / "selection.parquet"
        prescreen = root / "prescreen.parquet"
        out = root / "articles"
        target = out / "converted.json"
        pd.DataFrame([{"doi": doi, "selected_for_downstream": True,
                       "fulltext_enrichment_needed": True,
                       "fulltext_enrichment_action": "convert_local_pdf"}]).to_parquet(selection)
        pd.DataFrame([{"doi": doi, "prescreen_decision": "retain"}]).to_parquet(prescreen)
        row = {"study_doi": doi, "pdf_path": str(root / "mock.pdf"), "artifact_path": str(target)}
        artifact = {"study_doi": doi, "best_backend": "pdftotext", "best_char_count": 1000,
                    "source_identity": {"verified": True}}
        with patch.object(module, "selected_pdf_rows", return_value=([row], Counter())), \
             patch.object(module, "convert_pdf", return_value=[]), \
             patch.object(module, "build_artifact", return_value=artifact), \
             patch.object(module, "should_write_artifact", return_value=(True, "written")), \
             patch.object(module, "refresh_source_identity_audit") as refresh:
            report = module.convert_routed_local_pdfs(
                selection_table=selection, prescreen_table=prescreen,
                route_table=root / "routes.parquet", candidate_table=root / "missing.parquet",
                metadata_table=root / "missing_metadata.parquet", fulltext_dir=root,
                out_dir=out, paper_root=root, report_path=root / "report.json",
                backend="pdftotext")
        assert target.exists() and not refresh.called
        return {"artifacts_written": report["counts"]["written"],
                "source_identity_audit_refreshed": refresh.called}


def main() -> None:
    probes = [jats_information_loss, scoped_route_table_replacement,
              interrupted_discovery_promotion, batch_model_mismatch,
              repeated_stale_reprocessing, mutable_secondary_packet,
              concurrent_candidate_updates, schema_errors_not_retried,
              missing_batch_results_report_success, active_run_build_gate,
              worklist_conversion_omits_audit_refresh]
    results = {}
    for probe in probes:
        with contextlib.redirect_stdout(io.StringIO()):
            results[probe.__name__] = probe()
    print(json.dumps({"audit": "pipeline_audit_2026-09-06", "offline": True,
                      "production_data_modified": False, "probes": results}, indent=2))


if __name__ == "__main__":
    main()
