"""Actual public-health estimates survive the public browser projection."""
import json
from pathlib import Path
import pandas as pd
from pipeline.publish.export_evidence_payload import load_findings, detail_bootstrap_payload, OPTIONAL_REAL_WORLD_OBSERVATION_FIELDS


def test_native_real_world_estimate_and_context_reach_paper_detail(tmp_path):
    native = json.loads((Path(__file__).parent / "fixtures/real_world_observation_saved_rows.json").read_text())[1]
    asserted = {field: native[field] for field in OPTIONAL_REAL_WORLD_OBSERVATION_FIELDS}
    pd.DataFrame([{"finding_id": "real-world-exact", "paper_id": "paper-real-world", "source_name": "routed_extractions",
                   "study_doi": native["study_doi"], "domain": "real_world_public_health", "compound": native["compound"],
                   "entity_label": "Population use & trends", "raw_row_json": "{}", "effect_size": native["effect_size"],
                   **asserted}]).to_parquet(tmp_path / "findings.parquet", index=False)
    findings = load_findings(tmp_path, require_author_identities=False)
    payload = detail_bootstrap_payload(findings, "2026-10-31T00:00:00Z", tmp_path, "primary")
    row = {k: payload["values"][v] for k, v in zip(payload["fields"], payload["rows"][0])}
    for field, value in asserted.items():
        assert row[field] == value
    assert row["effect_size"] == "Descriptive counts and percentages"
    assert "125/249" in row["estimate_value"]
    assert "raw_row_json" not in row


def test_older_tables_do_not_require_new_real_world_columns(tmp_path):
    pd.DataFrame([{"finding_id": "old", "paper_id": "old", "source_name": "routed_extractions",
                   "study_doi": "10.1000/old", "domain": "real_world_public_health", "compound": "MDMA",
                   "entity_label": "Population use & trends", "raw_row_json": "{}"}]).to_parquet(tmp_path / "findings.parquet", index=False)
    findings = load_findings(tmp_path, require_author_identities=False)
    payload = detail_bootstrap_payload(findings, "2026-10-31T00:00:00Z", tmp_path, "primary")
    row = {k: payload["values"][v] for k, v in zip(payload["fields"], payload["rows"][0])}
    assert all(row[field] is None for field in OPTIONAL_REAL_WORLD_OBSERVATION_FIELDS)
