from types import SimpleNamespace

from pipeline.fulltext.run_local_pdf_conversion_pipeline import source_identity_audit_command


def test_source_identity_audit_command_is_fail_closed(tmp_path) -> None:
    args = SimpleNamespace(
        python="python3",
        out_dir=str(tmp_path / "articles"),
        candidate_table=str(tmp_path / "candidate.parquet"),
        metadata_table=str(tmp_path / "metadata.parquet"),
        source_identity_audit_json=str(tmp_path / "audit.json"),
        source_identity_audit_csv=str(tmp_path / "audit.csv"),
        source_identity_unverified_dois=str(tmp_path / "unverified.txt"),
    )

    command = source_identity_audit_command(args)

    assert command[-1] == "--fail-on-unverified"
    assert "--artifact-dir" in command
    assert str(tmp_path / "articles") in command
