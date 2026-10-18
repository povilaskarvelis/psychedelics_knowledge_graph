import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from jsonschema import Draft7Validator

from pipeline import llm
from pipeline.review import run_domain_routing as screening
from pipeline.review.run_deterministic_prescreen import build_prescreen_decisions


def response(text='{"required": 1, "optional": null}'):
    return dict(status="completed", model="gpt-6-luna", usage=dict(input_tokens=100, output_tokens=20),
                output=[dict(type="message", content=[dict(type="output_text", text=text)])])


def test_production_prompt_is_exact_evaluated_v5():
    # Pin the evaluated bytes without depending on ignored local run artifacts.
    evaluated_sha256 = "d4255c6e0263d3c45fe371344cdd1447d6a8170de48506ff66277e62b967ac07"
    assert hashlib.sha256(screening.SCREENING_PROMPT_PATH.read_bytes()).hexdigest() == evaluated_sha256


def test_wire_contract_restores_absent_optional_fields_without_losing_zero():
    schema = dict(type="object", required=["required"], properties={
        "required": {"type": "integer"}, "optional": {"type": "string"},
        "nullable": {"type": ["integer", "null"]}})
    wire = llm.strict_schema(schema)
    value = dict(required=0, optional=None, nullable=None)
    assert Draft7Validator(wire).is_valid(value)
    restored = llm.restore(value, schema)
    assert restored == dict(required=0, nullable=None)
    assert Draft7Validator(schema).is_valid(restored)


def test_retired_models_cannot_reenter_through_cli_or_task_metadata():
    with pytest.raises(ValueError, match="exclusively"):
        llm.require_luna("gemini-3-flash-preview")
    with pytest.raises(ValueError, match="provenance"):
        llm.reject_retired_provenance([{"route_context": {"domain_routing_model": "gemini-3-flash-preview"}}])


def test_incomplete_paid_response_is_saved_and_replayed_without_a_second_call(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "PIPELINE_STATE", tmp_path / "no-state")
    raw = response()
    raw["status"] = "incomplete"
    api = Mock()
    api.responses.create.return_value.model_dump.return_value = raw
    config = llm.generation_config(system_instruction="Task", schema={"type": "object", "properties": {}}, max_output_tokens=100)
    for _ in range(2):
        with pytest.raises(ValueError, match="did not complete"):
            llm.generate_structured(api, model="gpt-6-luna", contents="Source", config=config, raw_path=tmp_path / "raw.json")
    assert api.responses.create.call_count == 1
    saved = next(tmp_path.glob("raw.*.json"))
    assert json.loads(saved.read_text())["status"] == "incomplete"


def test_batch_key_reconciliation_accepts_reordering_and_preserves_errors(tmp_path):
    manifest = {"records": [{"key": "a"}, {"key": "b"}]}
    path = tmp_path / "results.jsonl"
    rows = [{"custom_id": "b", "error": {"code": "batch_expired"}},
            {"custom_id": "a", "response": {"status_code": 200, "body": response()}}]
    path.write_text("".join(json.dumps(r)+"\n" for r in rows))
    assert llm.reconciled_rows(manifest, path) == rows
    assert llm.batch_line_error(rows[0])
    assert not llm.batch_line_error(rows[1])
    path.write_text(json.dumps(rows[0])+"\n")
    with pytest.raises(ValueError, match="reconciliation"):
        llm.reconciled_rows(manifest, path)


def test_budget_counts_inflight_reservations_and_settles_actual_usage(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(dict(model_api_budget_usd=1, queue=str(tmp_path / "screening/queue.json"))))
    monkeypatch.setattr(llm, "PIPELINE_STATE", state)
    llm.reserve_budget("batch-a", 0.8)
    with pytest.raises(RuntimeError, match="budget"):
        llm.reserve_budget("batch-b", 0.3)
    llm.settle_budget("batch-a", 0.1)
    llm.reserve_budget("batch-b", 0.3)
    with pytest.raises(RuntimeError, match="prior paid"):
        llm.reserve_budget("batch-b", 0.3)
    a = json.loads((tmp_path / "budget.json").read_text())
    assert a["entries"]["batch-a"]["actual_usd"] == 0.1
    assert a["entries"]["batch-b"]["reserved_usd"] == 0.3


def test_extraction_gate_stays_closed_until_screening_complete(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(dict(screening_status="prepared")))
    monkeypatch.setattr(llm, "PIPELINE_STATE", state)
    with pytest.raises(RuntimeError, match="must finish"):
        llm.require_screening_complete()
    state.write_text(json.dumps(dict(screening_status="complete")))
    llm.require_screening_complete()


def test_cleanup_only_preserves_format_language_and_text_gates_but_opens_topic():
    abstract = "This original ecological study reports plant growth and soil measurements in a controlled experiment. " * 7
    rows = [dict(doi="10.example/topic", study_title="Plant growth", abstract=abstract, publication_type="journal article", language="en"),
            dict(doi="10.example/preprint", study_title="Plant growth", abstract=abstract, publication_type="preprint", language="en"),
            dict(doi="10.example/thesis", study_title="A dissertation", abstract=abstract, publication_type="dissertation", language="en"),
            dict(doi="10.example/missing", study_title="Plant growth", abstract="", publication_type="journal article", language="en")]
    result = build_prescreen_decisions(pd.DataFrame(rows), pd.DataFrame(), run_id="test", generated_at_utc="now", cleanup_only=True)
    decisions = {r["doi"]: r for r in result}
    assert decisions["10.example/topic"]["prescreen_decision"] == "retain"
    assert all(decisions[d]["prescreen_decision"] == "exclude" for d in ("10.example/preprint", "10.example/thesis", "10.example/missing"))
