"""Luna-only structured Responses and Batch transport shared by the pipeline."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft7Validator

DEFAULT_MODEL = "gpt-6-luna"
REASONING_EFFORT = "low"
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}
PIPELINE_STATE = Path(__file__).resolve().parents[1] / "data/processed/corpus/model_pipeline_state.json"


def require_screening_complete():
    if PIPELINE_STATE.exists():
        state = json.loads(PIPELINE_STATE.read_text())
        if state.get("screening_status") != "complete":
            raise RuntimeError("Fresh Luna screening must finish before extraction can be prepared or run")
        for addition in state.get("screening_scope_additions", {}).values():
            if addition.get("screening_status") != "complete":
                raise RuntimeError("The current Luna screening scope addition must finish before extraction can be prepared or run")


def reject_retired_provenance(value):
    if isinstance(value, list):
        for item in value:
            reject_retired_provenance(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"model", "domain_routing_model", "screening_model"} and isinstance(item, str) and "gemini" in item.lower():
                raise ValueError("Retired model provenance cannot be reused in a fresh Luna extraction")
            reject_retired_provenance(item)


def token_cost(usage, *, batch=False):
    i, o = usage["input_tokens"], usage["output_tokens"]
    rate_in, rate_cache, rate_out = (0.20, 0.02, 0.75) if i > 272000 else (0.10, 0.01, 0.50)
    details = usage.get("input_tokens_details") or {}
    cached, writes = details.get("cached_tokens", 0), details.get("cache_write_tokens", 0)
    if cached + writes > i:
        raise ValueError("Cache usage exceeds input usage")
    return ((i-cached-writes)*rate_in + cached*rate_cache + writes*rate_in*1.25 + o*rate_out) / 1e6 * (0.5 if batch else 1)


def reservation_cost(body, *, batch=False):
    # UTF-8 bytes bound text tokens, with extra room for wire-schema overhead.
    n = len(json.dumps(body, ensure_ascii=False).encode()) + 4096
    return token_cost(dict(input_tokens=n, output_tokens=body["max_output_tokens"],
                           input_tokens_details={"cache_write_tokens": n}), batch=batch)


@contextmanager
def budget_ledger():
    if not PIPELINE_STATE.exists():
        yield None
        return
    state = json.loads(PIPELINE_STATE.read_text())
    if not state.get("model_api_budget_usd"):
        yield None
        return
    path = Path(state["queue"]).parent.parent / "budget.json"
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(path.read_text()) if path.exists() else {"limit_usd": state["model_api_budget_usd"], "entries": {}}
        yield ledger
        atomic_json(path, ledger)


def reserve_budget(key, ceiling, *, allow_reservation_overcommit=False):
    with budget_ledger() as ledger:
        if ledger is None:
            return
        if key in ledger["entries"]:
            raise RuntimeError("A prior paid attempt/reservation exists; reconcile it before retrying")
        # Explicitly authorized concurrent dispatch can use settled spending
        # rather than hypothetical maximum output for every unfinished job.
        # Keep all reservations in the ledger and preserve the default guard.
        committed = (
            sum(e.get("actual_usd", 0) for e in ledger["entries"].values())
            if allow_reservation_overcommit
            else sum(e.get("actual_usd", e["reserved_usd"]) for e in ledger["entries"].values())
        )
        if committed + ceiling > ledger["limit_usd"]:
            raise RuntimeError(f"Model API budget would exceed ${ledger['limit_usd']:.2f}; no request submitted")
        ledger["entries"][key] = {"reserved_usd": ceiling}
        if allow_reservation_overcommit:
            ledger["entries"][key]["reservation_overcommit_user_authorized"] = True


def settle_budget(key, actual):
    with budget_ledger() as ledger:
        if ledger is not None and key in ledger["entries"]:
            ledger["entries"][key]["actual_usd"] = actual


def require_luna(model: str = DEFAULT_MODEL) -> str:
    if model != DEFAULT_MODEL:
        raise ValueError(f"This pipeline is configured exclusively for {DEFAULT_MODEL}; received {model!r}")
    return model


def client(api_key: str):
    from openai import OpenAI
    return OpenAI(api_key=api_key, max_retries=0, timeout=240)


def strict_schema(schema):
    """Make optional scientific fields nullable on the wire, preserving their contract."""
    out = copy.deepcopy(schema)
    if isinstance(out, list):
        return [strict_schema(v) for v in out]
    if not isinstance(out, dict):
        return out
    for key in ("$schema", "$id"):
        out.pop(key, None)
    if "const" in out:
        out["enum"] = [out.pop("const")]
    if "properties" in out:
        required = set(out.get("required", []))
        props = {}
        for key, value in out["properties"].items():
            wire = strict_schema(value)
            if key not in required and not Draft7Validator(value).is_valid(None):
                wire = {"anyOf": [wire, {"type": "null"}]}
            props[key] = wire
        out.update(properties=props, required=list(props), additionalProperties=False)
    for key in ("items", "anyOf", "oneOf", "allOf", "$defs", "definitions"):
        if key in out:
            if key in {"$defs", "definitions"}:
                out[key] = {k: strict_schema(v) for k, v in out[key].items()}
            else:
                out[key] = strict_schema(out[key])
    return out


def restore(value, schema):
    """Remove only absent optional values introduced by the strict wire schema."""
    if isinstance(value, list):
        return [restore(v, schema.get("items", {})) for v in value]
    if not isinstance(value, dict):
        return value
    props, required = schema.get("properties", {}), schema.get("required", [])
    out = {}
    for key, item in value.items():
        field = props.get(key, {})
        normalized = restore(item, field)
        if key not in required:
            if item is None and not Draft7Validator(field).is_valid(None):
                continue
            if normalized == {} and not field.get("required"):
                continue
        out[key] = normalized
    return out


def generation_config(*, system_instruction, schema, schema_mode="native", temperature=0,
                      max_output_tokens=16384, thinking_budget=None, reasoning_effort=REASONING_EFFORT):
    # Temperature and the previous provider's thinking budget are not sent to Responses.
    return dict(instructions=system_instruction, schema=schema, schema_mode=schema_mode,
                max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort)


def request_body(*, model, contents, config):
    require_luna(model)
    fmt = ({"type": "json_object"} if config["schema_mode"] == "prompt" else
           {"type": "json_schema", "name": "paper_evidence", "strict": True,
            "schema": strict_schema(config["schema"])})
    return dict(model=model, instructions=config["instructions"], input=contents,
                reasoning={"effort": config.get("reasoning_effort", REASONING_EFFORT)},
                max_output_tokens=config["max_output_tokens"], store=False, text={"format": fmt})


def response_text(response):
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    return "".join(part.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for part in item.get("content", [])
                   if part.get("type") == "output_text")


def validate_response(response):
    if response.get("status") != "completed":
        raise ValueError(f"Luna response did not complete: {response.get('incomplete_details') or response.get('status')}")
    require_luna(response.get("model", ""))
    usage = response.get("usage") or {}
    if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        raise ValueError("Luna response has missing billing usage")
    if not response_text(response):
        raise ValueError("Luna returned no output text (or refused the request)")
    return usage


def generate_structured(api_client, *, model, contents, config, raw_path=None):
    body = request_body(model=model, contents=contents, config=config)
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if raw_path is None:
        base = (Path(json.loads(PIPELINE_STATE.read_text())["queue"]).parent.parent
                if PIPELINE_STATE.exists() else PIPELINE_STATE.parents[2] / "model_calls")
        raw_path = base / "responses" / (fingerprint + ".json")
    else:
        raw_path = Path(raw_path)
        raw_path = raw_path.with_name(raw_path.stem + "." + fingerprint[:16] + raw_path.suffix)
    budget_key = str(raw_path)
    if raw_path.exists():
        raw = json.loads(raw_path.read_text())
    else:
        reserve_budget(budget_key, reservation_cost(body))
        response = api_client.responses.create(**body)
        raw = response.model_dump(mode="json")
        atomic_json(raw_path, raw)
    if (raw.get("usage") or {}).get("input_tokens") is not None and raw["usage"].get("output_tokens") is not None:
        settle_budget(budget_key, token_cost(raw["usage"]))
    usage = validate_response(raw)
    text = response_text(raw)
    parsed = restore(json.loads(text), config["schema"])
    return SimpleNamespace(text=json.dumps(parsed, ensure_ascii=False), usage=usage, raw=raw)


def usage_dict(response):
    return response.usage


def reconciled_rows(manifest, path):
    """Never join asynchronous responses by position or silently accept missing tasks."""
    from collections import Counter
    expected = [r["key"] for r in manifest["records"]]
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    actual = [batch_line_key(r, i) for i, r in enumerate(rows, 1)]
    if len(set(expected)) != len(expected) or Counter(actual) != Counter(expected):
        raise ValueError("Batch result reconciliation failed: missing, duplicate or unexpected custom_id")
    return rows


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def batch_line(key, body):
    require_luna(body["model"])
    return dict(custom_id=key, method="POST", url="/v1/responses", body=body)


def batch_line_key(row, fallback_index):
    return str(row.get("custom_id") or row.get("key") or
               row.get("metadata", {}).get("key") or f"row-{fallback_index}")


def batch_line_response(row):
    return row.get("response", {}).get("body", {}) if isinstance(row.get("response"), dict) else {}


def batch_line_error(row):
    if row.get("error"):
        return json.dumps(row["error"], ensure_ascii=False)
    response = row.get("response") or {}
    if response.get("status_code") != 200:
        return f"Batch request HTTP {response.get('status_code')}: {response.get('body', {})}"
    body = response.get("body", {})
    try:
        validate_response(body)
    except ValueError as e:
        return str(e)
    return ""


def submit(api_client, *, requests_path, job_path, metadata, allow_reservation_overcommit=False):
    """Durable reservation and idempotency prevent accidental duplicate paid submissions."""
    requests_path, job_path = Path(requests_path), Path(job_path)
    if job_path.exists():
        previous = json.loads(job_path.read_text())
        if previous.get("job_name"):
            return previous
        raise RuntimeError(f"Submission outcome needs reconciliation; refusing to resubmit {job_path}")
    digest = hashlib.sha256(requests_path.read_bytes()).hexdigest()
    count = 0
    ceiling = 0.0
    for line in requests_path.open():
        row = json.loads(line)
        require_luna(row["body"]["model"])
        if row["url"] != "/v1/responses" or not row.get("custom_id"):
            raise ValueError("Invalid Responses batch request")
        count += 1
        ceiling += reservation_cost(row["body"], batch=True)
    if not count or count > 50000 or requests_path.stat().st_size > 200_000_000:
        raise ValueError("Batch must contain 1–50,000 requests and be at most 200 MB")
    reserve_budget(str(job_path), ceiling, allow_reservation_overcommit=allow_reservation_overcommit)
    atomic_json(job_path, dict(status="submitting", input_sha256=digest))
    with requests_path.open("rb") as f:
        uploaded = api_client.files.create(file=f, purpose="batch")
    atomic_json(job_path, dict(status="uploaded", input_sha256=digest, input_file_id=uploaded.id))
    job = api_client.batches.create(input_file_id=uploaded.id, endpoint="/v1/responses",
                                    completion_window="24h", metadata=metadata,
                                    extra_headers={"Idempotency-Key": digest})
    payload = dict(status="submitted", job_name=job.id, model=DEFAULT_MODEL,
                   input_sha256=digest, uploaded_file=uploaded.model_dump(mode="json"),
                   batch_job=job.model_dump(mode="json"))
    atomic_json(job_path, payload)
    with budget_ledger() as ledger:
        if ledger is not None and str(job_path) in ledger["entries"]:
            ledger["entries"][str(job_path)]["job_name"] = job.id
    return payload


def download(api_client, job, output_path):
    """Keep successes AND per-request errors, including partial terminal batches."""
    if job.status not in TERMINAL_STATES:
        raise ValueError(f"Batch is still {job.status}")
    content = b""
    for file_id in (job.output_file_id, job.error_file_id):
        if file_id:
            data = api_client.files.content(file_id).content
            content += data + (b"\n" if data and not data.endswith(b"\n") else b"")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)
    costs, unknown = [], False
    for line in content.splitlines():
        row = json.loads(line)
        response = row.get("response") or {}
        usage = (response.get("body") or {}).get("usage") or {}
        if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            costs.append(token_cost(usage, batch=True))
        elif response.get("status_code") not in {400, 401, 403, 404, 422, 429} and (row.get("error") or {}).get("code") not in {"batch_expired", "batch_cancelled", "request_cancelled"}:
            unknown = True
    if not content and getattr(job.request_counts, "completed", 0):
        unknown = True
    with budget_ledger() as ledger:
        if ledger is not None:
            for entry in ledger["entries"].values():
                if entry.get("job_name") == job.id:
                    if unknown:
                        entry["billing_reconciliation_required"] = True
                    else:
                        entry["actual_usd"] = sum(costs)
    return dict(state=job.status, output_file_id=job.output_file_id, error_file_id=job.error_file_id)
