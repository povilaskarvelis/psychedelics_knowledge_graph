from pathlib import Path

from pipeline.fulltext import run_pdf_retrieval_pipeline as runner


def test_pdf_retrieval_pipeline_runs_standard_recovery_after_direct_download(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {"exports": 0}

    def fake_download_routed_pdfs(**kwargs):
        calls["download_kwargs"] = kwargs
        return {
            "counts": {"status": {"download_failed": 1}, "candidate_rows_changed": 1},
            "route_rebuild": {"performed": True},
        }

    def fake_export_manual_pdf_queue(**kwargs):
        calls["exports"] = int(calls["exports"]) + 1
        return {"rows": 2 if calls["exports"] == 1 else 1, "output_csv": str(kwargs["output_csv"])}

    def fake_recover_pdf_landing_pages(**kwargs):
        calls["recovery_kwargs"] = kwargs
        return {
            "counts": {"status": {"downloaded": 1}, "candidate_rows_changed": 1},
            "route_rebuild": {"performed": True},
        }

    monkeypatch.setattr(runner, "download_routed_pdfs", fake_download_routed_pdfs)
    monkeypatch.setattr(runner, "export_manual_pdf_queue", fake_export_manual_pdf_queue)
    monkeypatch.setattr(runner, "recover_pdf_landing_pages", fake_recover_pdf_landing_pages)

    report = runner.run_pdf_retrieval_pipeline(
        route_table=tmp_path / "routes.parquet",
        metadata_table=tmp_path / "metadata.parquet",
        candidate_table=tmp_path / "candidate_papers.parquet",
        pdf_dir=tmp_path / "pdfs",
        prescreen_table=tmp_path / "prescreen.parquet",
        domain_routing_table=None,
        fulltext_dir=tmp_path / "fulltext",
        route_summary_json=tmp_path / "summary.json",
        route_counts_csv=tmp_path / "counts.csv",
        manual_queue_csv=tmp_path / "manual.csv",
        manual_queue_txt=tmp_path / "manual.txt",
        direct_report_path=tmp_path / "direct.json",
        recovery_report_path=tmp_path / "recovery.json",
        report_path=tmp_path / "pipeline.json",
        alternate_pdf_sources={"pmc", "openalex", "semantic_scholar"},
        alternate_pdf_min_title_score=0.35,
        attempt_log_every=0,
        candidate_log_every=0,
        progress_every=0,
    )

    assert calls["exports"] == 2
    assert calls["download_kwargs"]["rebuild_routes_after"] is True
    assert calls["download_kwargs"]["alternate_pdf_sources"] == {"pmc", "openalex", "semantic_scholar"}
    assert calls["download_kwargs"]["alternate_pdf_min_title_score"] == 0.35
    assert calls["recovery_kwargs"]["standard_recovery_only"] is True
    assert calls["recovery_kwargs"]["apply"] is True
    assert report["alternate_pdf_sources"] == ["openalex", "pmc", "semantic_scholar"]
    assert report["standard_recovery"]["status"] == {"downloaded": 1}
    assert report["manual_queue_final"]["rows"] == 1
    assert Path(report["manual_queue_csv"]).name == "manual.csv"
