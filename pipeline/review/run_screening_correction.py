"""Freeze, validate and batch-screen a scoped correction without rewriting V5.

Model transport, strict Responses schemas, shared reservations and idempotent
submissions use pipeline.llm. New decisions remain staged until an independent
validation gate and the result audit have passed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline import llm
from pipeline.review import screening_contract as contract
from pipeline.review.run_domain_routing import normalize_payload, route_rows_from_parsed, load_dotenv
from pipeline.review.run_deterministic_prescreen import candidate_screening_row, publication_cleanup_exclusion_decision

DEFAULT_ROOT = ROOT / "data/processed/model_runs/luna_v5_20261017/screening_correction_20261019"
COHORT_PCP_RE = re.compile(r"\bphencyclidin\w*\b|\b(?:\d[- ]?(?:meo|ho|oxo)[- ]?)?pcp\b", re.I)
SOURCE_OBSERVATIONS = {
    "10.1016/j.vaa.2026.101349": {"publication_format": "conference_abstract", "evidence": "The title-matched publisher page explicitly labels this DOI Conference abstract.", "source": "manual_chrome_batches_20261019/batch_001/eligibility_audit_20261019.json"},
    "10.1055/a-2173-8063": {"language": "de", "evidence": "User inspected the source article and confirmed German full text. The English title is translated and publication_type is English Abstract.", "source": "manual_chrome_batches_20261019/batch_001/eligibility_audit_20261019.json"},
    "10.1017/s1092852923001384": {"publication_format": "conference_abstract", "evidence": "Publisher Information explicitly gives Type: Abstracts, CNS Spectrums 28(2), p.221.", "source": "https://www.cambridge.org/core/journals/cns-spectrums/article/review-of-the-taar1-agonist-ulotaront-part-ifrom-discovery-to-clinic/082F5932841D78005556333D620CF013"},
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    llm.atomic_json(Path(path), value)


def rows(path):
    path = Path(path)
    return [json.loads(l) for l in path.open() if l.strip()] if path.exists() else []


def write_rows(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    temp.replace(path)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(record, *, max_output_tokens=3072, retry_issues=None, system_instruction=None, reasoning_effort="low"):
    content = contract.prompt_for_record(record)
    if retry_issues:
        content += "\n\nValidation feedback for a new independent decision: " + ", ".join(retry_issues) + ". Re-read the source record. Copy exact contiguous quotations. Do not change a scientific judgment merely to avoid review; use needs_review if unresolved."
    return llm.request_body(model=llm.DEFAULT_MODEL, contents=content,
        config=llm.generation_config(system_instruction=system_instruction or contract.instruction(contract.V6), schema=contract.response_schema(contract.V6), max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort))


def hard_precheck(record):
    observation = record.get("verified_observation") or SOURCE_OBSERVATIONS.get(record.get("doi", ""), {})
    if observation.get("publication_format") in {"conference_abstract", "poster", "book", "book_chapter", "educational_digest", "news_summary"}:
        return {"status": "confirmed_cleanup_exclusion", "basis": "ineligible_publication", "reason": observation["evidence"]}
    if observation.get("language") and observation["language"].lower() not in {"en", "eng", "english"}:
        return {"status": "confirmed_cleanup_exclusion", "basis": "non_english_source", "reason": observation["evidence"]}
    doi = record.get("doi", "").lower()
    # These DOI families identify source formats, not topics. Publisher issue
    # contents verified the Canadian Paediatric Society abstract proceedings;
    # Journal Watch, Obstetric Anesthesia Digest and CHOICE are summaries.
    excluded_families = {
        "10.1056/jp": "NEJM Journal Watch educational summary (https://clinician.nejm.org/JP201004160000003)",
        "10.1097/01.aoa.": "Obstetric Anesthesia Digest summary of another published report",
        "10.5860/choice.": "CHOICE book review/citation record",
        "10.1093/pch/19.6.e35-": "2014 Canadian Paediatric Society meeting abstract (https://academic.oup.com/pch/issue/19/6)",
        "10.1093/jsxmed/qdag002.": "Journal of Sexual Medicine 23 Supplement 1 meeting abstract (https://academic.oup.com/jsm/issue/23/Supplement_1)",
    }
    for prefix, reason in excluded_families.items():
        if doi.startswith(prefix):
            return {"status": "confirmed_cleanup_exclusion", "basis": "ineligible_publication", "reason": reason}
    if record.get("identity_hold"):
        return {"status": "metadata_hold", "basis": "metadata_conflict", "reason": record["identity_hold"]}
    if str(record.get("post_retrieval_decision", "")).lower() == "exclude":
        return {"status": "confirmed_cleanup_exclusion", "basis": "ineligible_publication", "reason": record.get("post_retrieval_reason", "Confirmed source exclusion")}
    decision = publication_cleanup_exclusion_decision(candidate_screening_row(record))
    if decision:
        return {"status": "confirmed_cleanup_exclusion", "basis": "non_english_source" if decision["action"] == "exclude_non_english_language" else "ineligible_publication", "reason": decision["reason"], "evidence": decision.get("supporting_quote", "")}
    return None


def prepare(root: Path):
    if (root / "run.json").exists():
        return read(root / "run.json")
    base = root.parent
    source = ROOT / "data/processed/corpus/candidate_papers.parquet"
    candidate = pd.read_parquet(source).fillna("")
    routing = pd.read_parquet(ROOT / "data/processed/corpus/paper_domain_routing.parquet").drop_duplicates("doi")
    retained = set((root / "retained_scope.dois.txt").read_text().splitlines())
    previously_excluded = set(routing.loc[routing.screening_decision == "exclude_out_of_scope", "doi"])
    context = candidate.study_title + "\n" + candidate["abstract"]
    pcp = set(candidate.loc[candidate.doi.isin(previously_excluded) & context.str.contains(COHORT_PCP_RE, regex=True), "doi"])
    subset = candidate[candidate.doi.isin(retained | pcp)].copy()
    if set(subset.doi) != retained | pcp:
        raise ValueError("Missing correction-scope metadata")
    inputs = root / "inputs"
    inputs.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "data/processed/corpus/paper_domain_routing.parquet", inputs / "v5_routing.parquet")
    shutil.copy2(ROOT / "docs/screening/title_abstract_screening_v6.md", inputs / "title_abstract_screening_v6.md")
    save(inputs / "response_schema.json", contract.response_schema(contract.V6))
    save(inputs / "verified_source_observations.json", SOURCE_OBSERVATIONS)
    repair = {v["doi"]: v for f in (root / "metadata_repair").glob("*.json") if not f.name.endswith(".crossref.json") for v in [read(f)]}
    original = {r["doi"]: r for r in subset.to_dict("records")}
    fields = ["doi", "study_title", "study_year", "abstract", "publication_type", "language", "mesh_terms", "keywords", "study_journal", "journal_volume", "journal_issue", "journal_pages", "post_retrieval_decision", "post_retrieval_reason"]
    by_route = routing.set_index("doi")
    records, prechecks = [], []
    for doi in sorted(original):
        before = original[doi]
        record = {f: str(before.get(f, "")) for f in fields}
        record["cohort"] = "previously_retained" if doi in retained else "previously_excluded_pcp"
        record["original_primary_domain"] = str(by_route.loc[doi, "primary_domain"])
        if doi in repair:
            fixed = repair[doi]
            record["original_metadata_sha256"] = hashlib.sha256(json.dumps({f: before.get(f, "") for f in fields}, sort_keys=True).encode()).hexdigest()
            if fixed["status"] == "authoritative_title_and_abstract":
                record.update({k: v for k, v in fixed["fields"].items() if v})
                record["metadata_repair_provenance"] = fixed["provenance"]
            else:
                # Never retain the known foreign abstract merely because the
                # authentic title is plausibly psychedelic-related.
                record.update({k: v for k, v in fixed.get("fields", {}).items() if v and k != "abstract"})
                record["abstract"] = ""
                record["identity_hold"] = "Known title/abstract identity conflict; authoritative full abstract or verified source evidence still required."
                record["metadata_repair_provenance"] = fixed.get("provenance", [])
        if doi in SOURCE_OBSERVATIONS:
            record["verified_observation"] = SOURCE_OBSERVATIONS[doi]
            record["verified_source_context"] = SOURCE_OBSERVATIONS[doi]["evidence"]
        records.append(record)
        checked = hard_precheck(record)
        if checked:
            prechecks.append({"doi": doi, **checked})
    write_rows(inputs / "records.jsonl", records)
    save(inputs / "prechecks.json", prechecks)
    (inputs / "previously_excluded_pcp.dois.txt").write_text("\n".join(sorted(pcp)) + "\n")
    held = {r["doi"] for r in prechecks}
    known = set()
    manual = base / "fulltext_recovery_20261018/browser_full_pass_20261018/manual_chrome_batches_20261019"
    for batch in ["batch_001", "batch_002"]:
        audit = read(manual / batch / "eligibility_audit_20261019.json")
        known.update(r["doi"] for r in audit.get("user_flagged_records", audit.get("cases", [])))
        known.update(r["doi"] for r in audit.get("additional_confirmed_exclusions", []))
    known &= set(original)
    # A disjoint, fixed-seed sample is judged from source text before outputs
    # are opened. Old labels determine strata only, never the gold decisions.
    rng = random.Random(20261019)
    manual_seen = {p["doi"] for b in manual.glob("batch_*/manifest.json") for p in read(b)["papers"]}
    strata = defaultdict(list)
    for record in records:
        if record["doi"] in known | held | manual_seen:
            continue
        strata[(record["cohort"], record["original_primary_domain"])].append(record)
    fresh = []
    for cohort, target in [("previously_retained", 160), ("previously_excluded_pcp", 40)]:
        groups = [v[:] for (c, _), v in sorted(strata.items()) if c == cohort]
        for group in groups:
            rng.shuffle(group)
        selected = []
        while len(selected) < target and any(groups):
            for group in groups:
                if group and len(selected) < target:
                    selected.append(group.pop())
        fresh.extend(selected)
    known_records = [r for r in records if r["doi"] in known and r["doi"] not in held]
    pilot = [{**r, "validation_set": "known"} for r in known_records] + [{**r, "validation_set": "fresh"} for r in fresh]
    write_rows(inputs / "pilot_records.jsonl", pilot)
    state = {"run_id": "luna_v6_correction_20261019", "profile": contract.V6, "status": "prepared_validation", "prepared_at_utc": now(), "scope": {"previously_retained": len(retained), "previously_excluded_pcp": len(pcp), "total": len(records)}, "prechecks": dict(Counter(r["status"] for r in prechecks)), "pilot": {"known": len(known_records), "fresh": len(fresh), "total": len(pilot)}, "hashes": {"baseline_routing": fingerprint(inputs / "v5_routing.parquet"), "prompt": fingerprint(inputs / "title_abstract_screening_v6.md"), "records": fingerprint(inputs / "records.jsonl"), "pilot_records": fingerprint(inputs / "pilot_records.jsonl")}, "stages": {}, "budget_limit_usd": 100, "main_submission_requires_validation_pass": True, "promotion_requires_result_audit": True}
    save(root / "run.json", state)
    active = read(llm.PIPELINE_STATE)
    active.update(screening_status="correction_validation_pending", extraction_status="blocked_pending_screening_correction", screening_correction={"run_id": state["run_id"], "path": str(root), "status": state["status"]})
    save(llm.PIPELINE_STATE, active)
    return state


def prepare_stage(root: Path, stage: str, records: list[dict], *, max_bytes=180_000_000, feedback=None):
    state = read(root / "run.json")
    if stage in state["stages"]:
        return state["stages"][stage]
    prompt_path = root / "inputs/title_abstract_screening_v6.md"
    if not prompt_path.exists():
        prompt_path = ROOT / "docs/screening/title_abstract_screening_v6.md"
    if fingerprint(prompt_path) != state["hashes"]["prompt"]:
        raise ValueError("V6 prompt changed after run freeze")
    folder = root / stage
    folder.mkdir(exist_ok=True)
    parts, current, size = [], [], 0
    def flush():
        nonlocal current, size
        if not current:
            return
        n = len(parts) + 1
        name = f"part{n:03d}"
        requests_path = folder / (name + ".requests.jsonl")
        write_rows(requests_path, [a[0] for a in current])
        manifest = {"screening_profile": contract.V6, "prompt_sha256": state["hashes"]["prompt"], "input_sha256": fingerprint(requests_path), "records": [{"key": a[0]["custom_id"], "doi": a[1]["doi"], "record": a[1]} for a in current]}
        save(folder / (name + ".manifest.json"), manifest)
        parts.append({"name": name, "requests": len(current), "requests_path": str(requests_path), "manifest_path": str(folder / (name + ".manifest.json")), "job_path": str(folder / (name + ".job.json")), "output_path": str(folder / (name + ".output.jsonl")), "bytes": size, "input_sha256": manifest["input_sha256"], "reservation_usd": sum(llm.reservation_cost(a[0]["body"], batch=True) for a in current)})
        current, size = [], 0
    for record in records:
        key = stage + "-" + hashlib.sha256(record["doi"].encode()).hexdigest()[:20]
        body = request(record, retry_issues=(feedback or {}).get(record["doi"]), system_instruction=prompt_path.read_text().strip(), reasoning_effort=state.get("reasoning_effort", "low"), max_output_tokens=state.get("max_output_tokens", 3072))
        line = llm.batch_line(key, body)
        length = len((json.dumps(line, ensure_ascii=False) + "\n").encode())
        if current and (size + length > max_bytes or len(current) >= 50000):
            flush()
        current.append((line, record))
        size += length
    flush()
    stage_state = {"status": "prepared", "parts": parts, "requests": len(records), "prepared_at_utc": now(), "estimated_reservation_usd": sum(p["reservation_usd"] for p in parts)}
    state["stages"][stage] = stage_state
    save(root / "run.json", state)
    return stage_state


def api_client():
    values = load_dotenv(ROOT / ".env")
    key = values.get("OPENAI_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is unavailable")
    return llm.client(key)


def parse_part(part):
    manifest = read(part["manifest_path"])
    output = llm.reconciled_rows(manifest, part["output_path"])
    by_key = {a["key"]: a for a in manifest["records"]}
    parsed = []
    for i, line in enumerate(output, 1):
        key = llm.batch_line_key(line, i)
        record = by_key[key]["record"]
        item = {"doi": record["doi"], "key": key, "status": "error", "issues": [], "record": record, "parsed": {}}
        try:
            error = llm.batch_line_error(line)
            if error:
                raise ValueError(error)
            body = llm.batch_line_response(line)
            payload = json.loads(llm.response_text(body))
            contract.validate_schema(payload, contract.V6)
            issues = contract.validate_record(payload, record)
            item.update(parsed=payload, issues=issues, status="needs_review" if issues else "ok", usage=body["usage"], cost_usd=llm.token_cost(body["usage"], batch=True))
        except Exception as exc:
            item["issues"] = [str(exc)]
        parsed.append(item)
    return parsed


def advance_stage(root: Path, stage: str, *, submit: bool):
    state = read(root / "run.json")
    if submit and stage.startswith("main") and state.get("validation", {}).get("status") != "passed":
        raise ValueError("Main screening submission requires a passed independent validation gate")
    s = state["stages"][stage]
    client = api_client()
    all_done = True
    for part in s["parts"]:
        job_path = Path(part["job_path"])
        if not job_path.exists():
            all_done = False
            if submit:
                if fingerprint(part["requests_path"]) != part["input_sha256"]:
                    raise ValueError("Batch bytes changed after preparation")
                try:
                    job = llm.submit(client, requests_path=part["requests_path"], job_path=job_path, metadata={"stage": "screening_correction", "profile": contract.V6, "phase": stage})
                    print("SUBMITTED", stage, part["name"], part["requests"], job["job_name"], flush=True)
                except RuntimeError as exc:
                    if "budget would exceed" not in str(exc):
                        raise
                    print("WAITING_BUDGET", stage, part["name"], flush=True)
            continue
        job = read(job_path)
        if not job.get("job_name"):
            raise RuntimeError("Unknown batch submission outcome; reconcile before retrying: " + str(job_path))
        if not Path(part["output_path"]).exists():
            remote = client.batches.retrieve(job["job_name"])
            job.update(remote_state=remote.status, checked_at_utc=now(), request_counts=remote.request_counts.model_dump())
            save(job_path, job)
            if remote.status not in llm.TERMINAL_STATES:
                all_done = False
                continue
            llm.download(client, remote, part["output_path"])
        parsed_path = Path(part["output_path"]).with_name(part["name"] + ".parsed.jsonl")
        if not parsed_path.exists():
            write_rows(parsed_path, parse_part(part))
    # Reload to preserve stage descriptions prepared by another explicit action.
    state = read(root / "run.json")
    s = state["stages"][stage]
    completed = []
    for part in s["parts"]:
        parsed_path = Path(part["output_path"]).with_name(part["name"] + ".parsed.jsonl")
        if parsed_path.exists():
            completed.extend(rows(parsed_path))
    if all_done and len(completed) == s["requests"]:
        write_rows(root / stage / "results.jsonl", completed)
        s.update(status="complete", completed_at_utc=now(), status_counts=dict(Counter(a["status"] for a in completed)), cost_usd=sum(a.get("cost_usd", 0) for a in completed))
    else:
        s.update(status="running", completed_requests=len(completed))
    state["stages"][stage] = s
    save(root / "run.json", state)
    return s


def pilot_gate(root: Path):
    state = read(root / "run.json")
    gold_path = root / "inputs/pilot_gold.json"
    if not gold_path.exists():
        return {"status": "awaiting_independent_gold"}
    gold = {r["doi"]: r for r in read(gold_path)["records"]}
    outputs = {r["doi"]: r for r in rows(root / "pilot/results.jsonl")}
    outputs.update({r["doi"]: r for r in rows(root / "pilot_retry/results.jsonl")})
    outputs.update({r["doi"]: r for r in rows(root / "pilot_source_review/results.jsonl")})
    # Alias/consistency checks are versioned separately from immutable model
    # outputs. Re-evaluate cached parsing against the current tested validator.
    for actual in outputs.values():
        if actual.get("parsed"):
            contract.validate_schema(actual["parsed"], contract.V6)
            actual["issues"] = contract.validate_record(actual["parsed"], actual["record"])
            actual["status"] = "needs_review" if actual["issues"] else "ok"
    expected = {r["doi"] for r in rows(root / "inputs/pilot_records.jsonl")}
    prechecks_path = root / "inputs/source_format_prechecks.json"
    prechecks = {r["doi"]: r for r in read(prechecks_path)} if prechecks_path.exists() else {}
    if set(gold) != expected or set(outputs) != expected:
        raise ValueError("Pilot/gold DOI reconciliation failed")
    metrics, disagreements = {}, []
    groups = [g for g in ["known", "development", "fresh"] if any(r["validation_set"] == g for r in gold.values())]
    for group in groups:
        group_ids = [d for d in gold if gold[d]["validation_set"] == group]
        cm = Counter()
        held = 0
        for doi in group_ids:
            truth, actual = gold[doi]["decision"], outputs[doi]
            prediction = actual.get("parsed", {}).get("screening_decision", "error")
            checked = prechecks.get(doi) or hard_precheck(actual["record"])
            if checked and checked["status"] == "confirmed_cleanup_exclusion":
                prediction = "exclude_out_of_scope"
            elif actual["status"] != "ok":
                prediction = "needs_review"
                held += 1
            if truth in {"include_in_scope", "exclude_out_of_scope"}:
                cm[(truth, prediction)] += 1
            if truth != prediction:
                disagreements.append({"doi": doi, "validation_set": group, "gold": truth, "prediction": prediction, "gold_reason": gold[doi]["reason"], "model": actual.get("parsed", {}), "issues": actual["issues"]})
        tp = cm[("include_in_scope", "include_in_scope")]
        fp = cm[("exclude_out_of_scope", "include_in_scope")]
        positives = sum(n for (t, _), n in cm.items() if t == "include_in_scope")
        metrics[group] = {"papers": len(group_ids), "true_positive": tp, "false_positive": fp, "gold_positive": positives, "sensitivity_including_holds": tp / positives if positives else 1., "precision": tp / (tp + fp) if tp + fp else 1., "review_holds": held, "confusion": {t + " -> " + p: n for (t, p), n in cm.items()}}
    passed = not [a for a in disagreements if a["validation_set"] == "known" and a["gold"] != "needs_review"]
    passed &= all(m["sensitivity_including_holds"] >= .98 and m["precision"] >= .95 for g,m in metrics.items() if g != "known")
    report = {"status": "passed" if passed else "requires_review", "evaluated_at_utc": now(), "gold_sha256": fingerprint(gold_path), "validator_sha256":fingerprint(contract.__file__), "metrics": metrics, "disagreements": disagreements, "source_followup_papers":len(rows(root / "pilot_source_review/results.jsonl")), "method": "Source judgments frozen before inspecting each prompt's model results; known audit cases, development records and disjoint fresh strata reported separately. First-round gold and explicitly logged adjudication revisions are preserved. Sensitivity counts held known positives as not yet retained. Confirmed publication-format prechecks override model output. Any source-follow-up calls are counted separately from abstract-only decisions."}
    save(root / "pilot_validation.json", report)
    state["validation"] = {k: v for k, v in report.items() if k != "disagreements"}
    state["status"] = "validated_ready_for_main" if report["status"] == "passed" else "validation_requires_review"
    save(root / "run.json", state)
    return report


def main_records(root):
    exclude = {r["doi"] for r in read(root / "inputs/prechecks.json")}
    pilot = {r["doi"] for r in rows(root / "inputs/pilot_records.jsonl")}
    records = rows(root / "inputs/records.jsonl")
    prechecks_path = root / "inputs/source_format_prechecks.json"
    prior = {r["doi"]: r for r in read(prechecks_path)} if prechecks_path.exists() else {}
    prior.update({r["doi"]: {"doi": r["doi"], **p} for r in records if (p := hard_precheck(r))})
    checked = list(prior.values())
    save(root / "inputs/source_format_prechecks.json", checked)
    exclude.update(r["doi"] for r in checked)
    return [r for r in records if r["doi"] not in exclude | pilot]


def build_result_audit(root: Path):
    """Reconcile every scoped DOI and stage an audit; never promote on its own."""
    state = read(root / "run.json")
    if state.get("stages", {}).get("main", {}).get("status") != "complete":
        raise ValueError("Main screening is not complete")
    source = {r["doi"]: r for r in rows(root / "inputs/records.jsonl")}
    outcomes = {}
    for phase in ["pilot", "pilot_retry", "pilot_source_review", "main", "main_retry"]:
        for result in rows(root / phase / "results.jsonl"):
            outcomes[result["doi"]] = {**result, "phase": phase}
    prechecks_path = root / "inputs/source_format_prechecks.json"
    checked = read(prechecks_path) if prechecks_path.exists() else read(root / "inputs/prechecks.json")
    for check in checked:
        outcomes[check["doi"]] = {**check, "phase": "source_precheck", "record": source[check["doi"]]}
    if set(outcomes) != set(source):
        raise ValueError("Final correction-scope DOI reconciliation failed")
    gold = {r["doi"]:r for r in read(root / "inputs/pilot_gold.json")["records"]}
    final, review = [], []
    for doi, result in sorted(outcomes.items()):
        payload = result.get("parsed", {})
        issues = contract.validate_record(payload, source[doi]) if payload else []
        status = ("needs_review" if issues else "ok") if payload else result["status"]
        if status == "confirmed_cleanup_exclusion":
            decision = "exclude_out_of_scope"
        elif status in {"metadata_hold", "needs_review", "error"} or issues:
            decision = "needs_review"
        else:
            decision = payload["screening_decision"]
        if doi in gold and gold[doi]["decision"] == "needs_review":
            decision = "needs_review"
            issues.append("independent_source_review_unresolved")
        elif doi in gold and decision != gold[doi]["decision"]:
            decision = "needs_review"
            issues.append("independent_source_judgment_disagreement")
        row = {**result, "effective_decision": decision, "initial_validation_issues":result.get("issues", []), "issues": sorted(set(issues if payload else result.get("issues", [])))}
        final.append(row)
        # Source-based triage and all new exclusions remain visible to the
        # reviewer; the previous inclusion is never treated as ground truth.
        if decision == "needs_review" or (source[doi]["cohort"] == "previously_retained" and decision == "exclude_out_of_scope") or (source[doi]["cohort"] == "previously_excluded_pcp" and decision == "include_in_scope"):
            review.append(row)
    write_rows(root / "final_staged_results.jsonl", final)
    write_rows(root / "result_review_queue.jsonl", review)
    report = {"run_id": state["run_id"], "status": "ready_for_result_audit", "scoped_papers": len(source), "decisions": dict(Counter(r["effective_decision"] for r in final)), "by_cohort": {cohort:dict(Counter(r["effective_decision"] for r in final if r["record"]["cohort"] == cohort)) for cohort in ["previously_retained", "previously_excluded_pcp"]}, "review_queue_papers":len(review), "staged_sha256":fingerprint(root / "final_staged_results.jsonl"), "baseline_routing_sha256":state["hashes"]["baseline_routing"], "canonical_outputs_changed":False, "extraction_submitted":False}
    save(root / "result_audit_summary.json", report)
    return report


def controller(root: Path, *, submit: bool, watch: bool):
    lock = (root / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while True:
        state = read(root / "run.json")
        if "pilot" not in state["stages"]:
            prepare_stage(root, "pilot", rows(root / "inputs/pilot_records.jsonl"))
        pilot = advance_stage(root, "pilot", submit=submit)
        if pilot["status"] == "complete":
            unresolved = [r for r in rows(root / "pilot/results.jsonl") if r["status"] != "ok"]
            if unresolved:
                prepare_stage(root, "pilot_retry", [r["record"] for r in unresolved], feedback={r["doi"]: r["issues"] for r in unresolved})
                retry = advance_stage(root, "pilot_retry", submit=submit)
                if retry["status"] != "complete":
                    if not watch:
                        return
                    time.sleep(45)
                    continue
            source_records = root / "inputs/source_confirmation_records.jsonl"
            if source_records.exists():
                prepare_stage(root, "pilot_source_review", rows(source_records))
                confirmed = advance_stage(root, "pilot_source_review", submit=submit)
                if confirmed["status"] != "complete":
                    if not watch:
                        return
                    time.sleep(45)
                    continue
            gate = pilot_gate(root)
            if gate["status"] == "passed":
                active = read(llm.PIPELINE_STATE)
                if active.get("screening_correction", {}).get("path") == str(root.resolve()):
                    active["screening_status"] = "correction_screening_running"
                    active["screening_correction"]["status"] = "screening_running"
                    save(llm.PIPELINE_STATE, active)
                prepare_stage(root, "main", main_records(root))
                main = advance_stage(root, "main", submit=submit)
                if main["status"] == "complete":
                    unresolved = [r for r in rows(root / "main/results.jsonl") if r["status"] != "ok"]
                    if unresolved:
                        prepare_stage(root, "main_retry", [r["record"] for r in unresolved], feedback={r["doi"]:r["issues"] for r in unresolved})
                        retry = advance_stage(root, "main_retry", submit=submit)
                        if retry["status"] != "complete":
                            if not watch:
                                return
                            time.sleep(45)
                            continue
                    build_result_audit(root)
                    state = read(root / "run.json")
                    state["status"] = "main_results_ready_for_audit"
                    save(root / "run.json", state)
                    active = read(llm.PIPELINE_STATE)
                    if active.get("screening_correction", {}).get("path") == str(root.resolve()):
                        active["screening_status"] = "correction_results_ready_for_audit"
                        active["screening_correction"]["status"] = state["status"]
                        save(llm.PIPELINE_STATE, active)
                    print("MAIN_COMPLETE", main["requests"], main.get("status_counts"), flush=True)
                    return
            elif gate["status"] == "requires_review":
                active = read(llm.PIPELINE_STATE)
                if active.get("screening_correction", {}).get("path") == str(root.resolve()):
                    active["screening_status"] = "correction_validation_requires_review"
                    active["screening_correction"]["status"] = "validation_requires_review"
                    save(llm.PIPELINE_STATE, active)
                print("VALIDATION_REQUIRES_REVIEW", json.dumps(gate["metrics"]), flush=True)
                return
        if not watch:
            return
        time.sleep(45)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "prepare-pilot", "advance", "gate", "audit", "status"])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    args.root.mkdir(exist_ok=True, parents=True)
    if args.command == "prepare":
        result = prepare(args.root)
    elif args.command == "prepare-pilot":
        result = prepare_stage(args.root, "pilot", rows(args.root / "inputs/pilot_records.jsonl"))
    elif args.command == "advance":
        controller(args.root, submit=args.submit, watch=args.watch)
        result = read(args.root / "run.json")
    elif args.command == "gate":
        result = pilot_gate(args.root)
    elif args.command == "audit":
        result = build_result_audit(args.root)
    else:
        result = read(args.root / "run.json")
    print(json.dumps({k: v for k, v in result.items() if k not in {"hashes", "stages", "disagreements"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
