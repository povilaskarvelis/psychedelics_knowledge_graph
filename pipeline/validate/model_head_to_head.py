"""Paired, isolated model evaluation with durable responses and bounded spending.

Inputs are frozen cases.jsonl, never canonical corpus outputs. A raw SDK response
is fsynced before text, usage, validation, or cost calculation is attempted.
Restart reprocesses saved responses without calling either provider again.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MODELS = {"luna": "gpt-6-luna", "gemini": "gemini-3-flash-preview"}


def rows(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def strip_descriptions(value, property_map=False):
    if isinstance(value, list):
        return [strip_descriptions(v) for v in value]
    if not isinstance(value, dict):
        return value
    return {k: strip_descriptions(v, k == "properties") for k, v in value.items()
            if property_map or k != "description"}


def strict_schema(schema):
    from jsonschema import Draft7Validator
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
    for key in ("items", "anyOf", "oneOf", "allOf"):
        if key in out:
            out[key] = strict_schema(out[key])
    return out


def restore(value, schema):
    """Remove wire-only absent values, including optional all-null objects.

    Applied identically to both providers. Required objects and genuinely
    nullable scientific fields retain their original null semantics.
    """
    from jsonschema import Draft7Validator
    if isinstance(value, list):
        return [restore(v, schema.get("items", {})) for v in value]
    if not isinstance(value, dict):
        return value
    props, required = schema.get("properties", {}), schema.get("required", [])
    out = {}
    for key, item in value.items():
        field = props.get(key, {})
        normalized = restore(item, field)
        optional = key not in required
        if optional and item is None and not Draft7Validator(field).is_valid(None):
            continue
        if optional and normalized == {} and not field.get("required"):
            continue
        out[key] = normalized
    return out


def usage_fields(raw, arm):
    if arm == "gemini":
        usage = raw.get("usage_metadata") or {}
        # Missing mandatory usage is unknown spend, never silently zero cost.
        if usage.get("prompt_token_count") is None or usage.get("candidates_token_count") is None:
            raise ValueError("Missing mandatory Gemini billing usage")
        return dict(usage=usage, input_tokens=usage["prompt_token_count"],
                    output_tokens=usage["candidates_token_count"] + (usage.get("thoughts_token_count") or 0),
                    cached_tokens=usage.get("cached_content_token_count") or 0,
                    cache_write_tokens=0, reasoning_tokens=usage.get("thoughts_token_count") or 0)
    usage = raw.get("usage") or {}
    if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        raise ValueError("Missing mandatory OpenAI billing usage")
    details = usage.get("input_tokens_details") or {}
    return dict(usage=usage, input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                cached_tokens=details.get("cached_tokens") or 0,
                cache_write_tokens=details.get("cache_write_tokens") or 0,
                reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)


def cost(row, uncached=False):
    i, o = row["input_tokens"], row["output_tokens"]
    if row["arm"] == "gemini":
        rate_in, rate_cache, rate_out = .50, .05, 3.00
    else:
        rate_in, rate_cache, rate_out = .10, .01, .50
        if i > 272000:
            rate_in, rate_cache, rate_out = .20, .02, .75
    cached = 0 if uncached else row.get("cached_tokens", 0)
    writes = 0 if uncached else row.get("cache_write_tokens", 0)
    if cached + writes > i:
        raise ValueError("Inconsistent usage: cache reads plus writes exceed input")
    return ((i - cached - writes) * rate_in + cached * rate_cache + writes * rate_in * 1.25 + o * rate_out) / 1e6


def reservation(case, arm, max_output):
    # UTF-8 bytes conservatively bound text token count; allow wire overhead.
    n = len((case["system_instruction"] + case["content"] + json.dumps(case["openai_schema"])).encode()) + 4096
    row = dict(arm=arm, input_tokens=n, output_tokens=max_output,
               cache_write_tokens=n if arm == "luna" else 0)
    return cost(row)


def raw_text(raw, arm):
    if arm == "gemini":
        return "".join(p.get("text", "") for c in raw.get("candidates", [])
                       for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))
    return "".join(p.get("text", "") for item in raw.get("output", [])
                   for p in item.get("content", []) if p.get("type") == "output_text")


def analyze_response(case, arm, envelope):
    from jsonschema import Draft7Validator
    from pipeline.extract import run_route_extraction as primary
    from pipeline.extract import run_review_relationship_extraction as review
    from pipeline.extract import run_meta_analysis_v2_batch_api as meta
    from pipeline.review import run_domain_routing as screening
    raw = envelope["response"]
    row = {k: case[k] for k in ("case_id", "input_sha256", "family", "study_doi", "text_depth")}
    row.update(arm=arm, requested_model=MODELS[arm], returned_model=raw.get("model", raw.get("model_version")),
               latency_seconds=envelope["latency_seconds"], status="error", **usage_fields(raw, arm))
    row["estimated_cost_usd"] = cost(row)
    row["uncached_equivalent_cost_usd"] = cost(row, uncached=True)
    row["raw_text"] = raw_text(raw, arm)
    try:
        if arm == "luna" and raw.get("status") != "completed":
            raise ValueError(f"OpenAI incomplete: {raw.get('incomplete_details')}")
        if arm == "gemini" and (not raw.get("candidates") or any(c.get("finish_reason") != "STOP" for c in raw["candidates"])):
            raise ValueError("Gemini did not finish with STOP")
        parsed, _ = primary.parse_json_response(row["raw_text"])
        row["raw_schema_errors"] = [e.message for e in Draft7Validator(case["original_schema"]).iter_errors(parsed)]
        result = restore(parsed, case["original_schema"])
        qa = []
        if case["family"] == "primary":
            profile = primary.profile_for_task(case["task"])
            result = primary.inject_route_identity_fields(result, case["task"], profile)
            for reject in (primary.reject_source_identity_mismatch_warnings, primary.reject_inconsistent_recommendation_tones, primary.reject_inconsistent_primary_categories):
                try:
                    reject(result)
                except ValueError as error:
                    qa.append(str(error))
        elif case["family"] == "review":
            result = review.inject_fixed_fields(result, case["task"])
            qa = review.bundle_semantic_errors(result)
        elif case["family"] == "meta":
            result, normalizations = meta.normalize_model_result(result, case["text_depth"])
            row["normalizations"] = normalizations
            source = case["content"].split("ARTICLE_TEXT:\n", 1)[-1] if case["text_depth"] == "article_text" else case["content"].split("ABSTRACT_TEXT:\n", 1)[-1]
            qa = meta.semantic_qa_flags(result, case["text_depth"]) + meta.result_quality_flags(result, source)
        else:
            screening.validate_response_payload(result)
            if result["screening_decision"] == "exclude_out_of_scope" and result["domain_tags"]:
                qa.append("excluded_record_has_domain_tags")
        primary.reject_corrupt_output_text(result)
        errors = [e.message for e in Draft7Validator(case["original_schema"]).iter_errors(result)]
        row.update(result=result, schema_errors=errors, qa_flags=qa, status="schema_error" if errors else "ok")
    except Exception as error:
        row.update(error=str(error)[:2000], error_type=type(error).__name__)
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--max-cost-usd", type=float, default=8)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--arms", nargs="+", choices=tuple(MODELS), default=["luna"],
                   help="Providers to call; use --arms luna for Luna-only prompt evaluations")
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--reprocess-only", action="store_true")
    p.add_argument("--retry-unbilled", action="store_true", help="Explicitly retry recorded HTTP 400 attempts; preserve original attempt files")
    a = p.parse_args()
    out = a.run_dir.resolve()
    with (out / "controller.lock").open("a") as process_lock:
        fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_locked(a, out)


def run_locked(a, out):
    cases = rows(out / "cases.jsonl")
    by_id = {c["case_id"]: c for c in cases}
    # Recover saved raw responses locally before scheduling any new requests.
    for path in sorted((out / "responses").glob("*.json")):
        env = json.loads(path.read_text())
        case = by_id[env["case_id"]]
        if case["input_sha256"] != env["input_sha256"]:
            raise ValueError("Frozen input changed after a request")
        atomic_json(out / "results" / path.name, analyze_response(case, env["arm"], env))
    for path in sorted((out / "requests").glob("*.json")):
        if not (out / "responses" / path.name).exists() and not (out / "errors" / path.name).exists():
            raise RuntimeError(f"Unknown billed request {path.name}; no new calls until reconciled")
        error_path = out / "errors" / path.name
        if error_path.exists() and not (out / "responses" / path.name).exists():
            if not json.loads(error_path.read_text()).get("known_unbilled"):
                raise RuntimeError(f"Unresolved billed attempt {path.name}; retained reservation")
    previous = [json.loads(p.read_text()) for p in (out / "results").glob("*.json")]
    if a.reprocess_only:
        print(json.dumps(dict(reprocessed=len(previous), cost=sum(r["estimated_cost_usd"] for r in previous))))
        return
    from pipeline.extract import run_route_extraction as primary
    arms = tuple(dict.fromkeys(a.arms))
    env = primary.load_dotenv(ROOT / ".env")
    if any(arm != "luna" for arm in arms):
        raise ValueError("Gemini is retired. Historical responses can be replayed with --reprocess-only; new calls are Luna only.")
    from openai import OpenAI
    clients = {"luna": OpenAI(api_key=env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", ""), max_retries=0, timeout=240)}
    selected = cases
    if a.pilot:
        selected = [next(c for c in cases if c["family"] == family) for family in ("screening", "primary", "review", "meta")
                    if any(c["family"] == family for c in cases)]
    random.Random(20261016).shuffle(selected)
    jobs = []
    for index, case in enumerate(selected):
        for arm in (arms if index % 2 else tuple(reversed(arms))):
            key = digest([case["input_sha256"], arm, "low" if arm == "luna" else 0])[:24]
            if a.retry_unbilled:
                attempt = 1
                while (out / "requests" / f"{key}.json").exists():
                    error_path = out / "errors" / f"{key}.json"
                    if not error_path.exists() or json.loads(error_path.read_text()).get("http_status") != 400:
                        break
                    attempt += 1
                    key = digest([case["input_sha256"], arm, "explicit_unbilled_retry", attempt])[:24]
            if not (out / "requests" / f"{key}.json").exists():
                jobs.append((case, arm, key))
    lock = threading.Lock()
    carried_cost = json.loads((out / "carried_cost.json").read_text())["estimated_cost_usd"] if (out / "carried_cost.json").exists() else 0
    spent = sum(r["estimated_cost_usd"] for r in previous) + carried_cost
    reserved = 0.0
    stopped = False

    def one(job):
        nonlocal spent, reserved, stopped
        case, arm, key = job
        max_output = (2048 if arm == "luna" else 512) if case["family"] == "screening" else (32768 if case["family"] == "meta" else 16384)
        upper = reservation(case, arm, max_output)
        with lock:
            if stopped or spent + reserved + upper > a.max_cost_usd:
                return
            reserved += upper
            atomic_json(out / "requests" / f"{key}.json", dict(case_id=case["case_id"], arm=arm,
                input_sha256=case["input_sha256"], reservation_usd=upper, max_output_tokens=max_output,
                created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
        started = time.monotonic()
        response_saved = False
        try:
            if arm == "luna":
                output_format = {"type": "json_object"} if case.get("schema_mode") == "prompt" else {"type": "json_schema", "name": "paper_evidence", "strict": True, "schema": case["openai_schema"]}
                response = clients[arm].responses.create(model=MODELS[arm], instructions=case["system_instruction"], input=case["content"],
                    reasoning={"effort": "low"}, max_output_tokens=max_output, store=False,
                    text={"format": output_format})
            else:
                raise ValueError("Retired provider: new calls are Luna only")
            envelope = dict(case_id=case["case_id"], input_sha256=case["input_sha256"], arm=arm,
                            latency_seconds=round(time.monotonic() - started, 3), response=response.model_dump(mode="json"))
            atomic_json(out / "responses" / f"{key}.json", envelope)
            response_saved = True
            row = analyze_response(case, arm, envelope)
            atomic_json(out / "results" / f"{key}.json", row)
            with lock:
                spent += row["estimated_cost_usd"]
                reserved -= upper
                print(f"{arm} {case['family']} {row['status']} ${row['estimated_cost_usd']:.5f}; total ${spent:.4f}", flush=True)
        except Exception as error:
            message = str(error)
            for secret in secrets.values():
                if secret:
                    message = message.replace(secret, "[REDACTED]")
            code = getattr(error, "status_code", getattr(error, "code", None))
            known_unbilled = not response_saved and code in (400, 401, 403, 404, 429)
            atomic_json(out / "errors" / f"{key}.json", dict(case_id=case["case_id"], arm=arm, error=message[:1000],
                http_status=code, response_saved=response_saved, known_unbilled=known_unbilled, reservation_usd=upper))
            with lock:
                stopped = True
                if known_unbilled:
                    reserved -= upper
                # Otherwise retain the reservation for unknown billing.
                print(f"STOP: {arm} {case['family']}: {message[:350]}", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for future in as_completed(pool.submit(one, job) for job in jobs):
            future.result()
    print(json.dumps(dict(saved_responses=len(list((out / "responses").glob("*.json"))),
        estimated_cost_usd=spent, unresolved_reservations_usd=reserved, stopped=stopped)))


if __name__ == "__main__":
    main()
