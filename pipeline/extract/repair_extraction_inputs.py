"""Plan reproducible source repairs and targeted retries without rescreening.

Inputs are saved task/validation records and native registry responses, not
model-generated replacement abstracts. ``plan`` is offline and never changes
canonical metadata, model outputs, prompts, or schemas. Its reviewable proposal
uses the existing metadata/route owners when applied by the caller.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
import gzip
import glob
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from pipeline.extract.build_extraction_tasks import task_from_route
from pipeline.extract.io_utils import read_jsonl, write_json
from pipeline.fulltext.source_identity import doi_equivalent, title_similarity
from pipeline.ingest.metadata_utils import strip_markup


def collect_registry_evidence(tasks: list[dict], out_dir: Path, *,
                              pubmed_xml_paths: list[Path] = (),
                              crossref_cache: Path | None = None, offline: bool = False) -> dict:
    """Collect native evidence for a bounded repair scope, caching raw responses.

    Cached PMIDs are lookup hints, never identity proof. The offline planner
    checks returned DOIs and publisher/native titles before using any fields.
    Unknown identifiers are left unresolved rather than guessed from titles.
    """
    from pipeline.ingest.metadata_utils import metadata_from_pubmed_article
    from pipeline.ingest.refresh_pubmed_publication_types import parse_pubmed_publication_types
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {t["study_doi"]: t["paper_metadata"] for t in tasks}
    pmids = {str(m.get("pmid", "")) for m in meta.values() if str(m.get("pmid", "")).isdigit()}
    native, failures = {}, []

    def consume_pubmed(path: Path) -> None:
        raw = path.read_bytes()
        if path.suffix == ".gz":
            raw = gzip.decompress(raw)
        records = parse_pubmed_publication_types(raw)
        articles = {a.findtext("MedlineCitation/PMID"): a for a in ET.fromstring(raw).findall(".//PubmedArticle")}
        for pmid in pmids & records.keys():
            record = records[pmid]
            fields = metadata_from_pubmed_article(articles[pmid], {})
            native[pmid] = {**fields, "pmid": pmid, "title": record.title,
                            "dois": list(record.dois), "abstract": record.abstract,
                            "source_path": str(path.resolve()), "source_xml_sha256": hashlib.sha256(raw).hexdigest()}

    for path in pubmed_xml_paths:
        consume_pubmed(path)
    missing = sorted(pmids - native.keys())
    if missing and not offline:
        for start in range(0, len(missing), 200):
            ids = missing[start:start + 200]
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(
                {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
            path = out_dir / ("pubmed_" + hashlib.sha256(",".join(ids).encode()).hexdigest()[:16] + ".xml")
            if not path.exists():
                with urllib.request.urlopen(url, timeout=40) as response:
                    path.write_bytes(response.read())
                time.sleep(.4)
            consume_pubmed(path)
    cached = {}
    if crossref_cache:
        for path in crossref_cache.glob("*.json"):
            value = json.loads(path.read_text()).get("message")
            if isinstance(value, dict) and value.get("DOI"):
                cached[value["DOI"].lower()] = path
    crossref = []
    for doi in meta:
        path = cached.get(doi.lower())
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        if path is None and not offline:
            path = out_dir / ("crossref_" + hashlib.sha256(doi.encode()).hexdigest()[:16] + ".json")
            try:
                if not path.exists():
                    request = urllib.request.Request(url, headers={"User-Agent": "PsychKG source-identity repair/1.0"})
                    with urllib.request.urlopen(request, timeout=40) as response:
                        path.write_bytes(response.read())
                    time.sleep(.25)
            except Exception as exc:
                failures.append({"doi": doi, "url": url, "error": str(exc)})
                continue
        if path is None:
            continue
        raw = path.read_bytes()
        value = json.loads(raw)["message"]
        if not doi_equivalent(value.get("DOI"), doi):
            failures.append({"doi": doi, "error": "Returned Crossref DOI does not match request"})
            continue
        crossref.append({"doi": doi, "title": value.get("title", []), "type": value.get("type"),
                         "source_path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "url": url})
    write_json(out_dir / "native_records.json", native)
    write_json(out_dir / "crossref_records.json", crossref)
    summary = {"papers": len(meta), "native_records": len(native), "crossref_records": len(crossref),
               "unreturned_pmids": sorted(pmids - native.keys()), "failures": failures, "offline": offline}
    write_json(out_dir / "evidence_summary.json", summary)
    return summary


def repository_abstract(path: Path) -> dict:
    """Read a Pure institutional abstract, separately from its venue metadata.

    Require citation identifiers and a dedicated abstract element; generic page
    descriptions, search snippets, and bibliography text are never abstracts.
    """
    from bs4 import BeautifulSoup
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.select_one('meta[name="citation_title"]')
    doi = soup.select_one('meta[name="citation_doi"]')
    block = soup.select_one('.rendering_researchoutput_abstractportal .textblock')
    if not all((title, doi, block)):
        raise ValueError("Source lacks report-specific citation identity or dedicated abstract")
    return {"doi": doi.get("content", ""), "title": title.get("content", ""),
            "abstract": block.get_text(" ", strip=True), "source_path": str(path.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest()}


def source_repair_decision(task: dict, native: dict, crossref: dict, repository: dict | None = None) -> dict:
    """Require independent report-title agreement before replacing source text.

    An exact DOI alone does not resolve registry collisions. Missing registry
    abstracts cannot authenticate an existing provider abstract. Keep such
    records held for normal retrieval/review rather than extracting foreign text.
    """
    doi = task["study_doi"]
    cr_titles = crossref.get("title") or []
    if isinstance(cr_titles, str):
        cr_titles = [cr_titles]
    native_doi_matches = any(doi_equivalent(x, doi) for x in native.get("dois", []))
    title_agrees = any((title_similarity(native.get("title"), strip_markup(x)) or 0) >= .85
                       for x in cr_titles)
    verified = native_doi_matches and title_agrees
    if not verified:
        return {"doi": doi, "action": "hold_source_review",
                "reason": "Native identifier/title and publisher DOI title do not jointly establish the report and its abstract."}
    abstract = str(native.get("abstract", "")).strip()
    if not abstract and repository and doi_equivalent(repository.get("doi"), doi) and (
        title_similarity(native.get("title"), repository.get("title")) or 0) >= .9:
        abstract = repository["abstract"]
    if not abstract:
        return {"doi": doi, "action": "hold_source_review",
                "reason": "Report identity agrees, but no authenticated abstract is available; the conflicting provider text cannot be reused."}
    fields = {"study_title": native["title"], "abstract": abstract, "pmid": native["pmid"]}
    if "pmcid" in native:
        fields["pmcid"] = native["pmcid"]
    for key in ("authors", "study_journal", "study_year", "publication_date", "publication_type", "language"):
        if native.get(key):
            fields[key] = native[key]
    return {"doi": doi, "action": "repair_verified_metadata", "fields": fields,
            "reason": "Native PubMed DOI/abstract and publisher-deposited Crossref title agree.",
            "native_source": native.get("source_path"), "native_xml_sha256": native.get("source_xml_sha256"),
            "crossref_source": crossref.get("source_path"), "crossref_sha256": crossref.get("sha256")}


def repaired_abstract_task(task: dict, fields: dict, at: str) -> dict:
    """Use the normal task builder/fingerprints and existing abstract contract."""
    doi = task["study_doi"]
    metadata = {**task["paper_metadata"], **fields}
    route = copy.deepcopy(task["route_context"])
    route.update(doi=doi, study_title=metadata["study_title"],
                 route_action="extract_from_abstract_only", access_tier="abstract_only",
                 source_text_state="abstract_only", source_identity_verified=False,
                 has_converted_full_text=False, fulltext_artifact_paths="", fulltext_char_count=0)
    return task_from_route(route, metadata_by_doi={doi: metadata}, packets_by_doi={},
                           generated_at_utc=at, include_packet_content=False)


def plan_recovery(tasks: list[dict], failures: list[dict], native: dict, crossref: list[dict], at: str,
                  repositories: dict | None = None) -> dict:
    failed = {r["route_id"]: r for r in failures}
    source_dois = {r["study_doi"] for r in failures if "source-identity mismatch" in r.get("error", "")}
    cr = {r["doi"]: r for r in crossref}
    decisions = {}
    for t in tasks:
        doi = t["study_doi"]
        if doi in source_dois and doi not in decisions:
            decisions[doi] = source_repair_decision(t, native.get(str(t["paper_metadata"].get("pmid", "")), {}), cr.get(doi, {}), (repositories or {}).get(doi))
            if (repositories or {}).get(doi):
                decisions[doi]["repository_abstract_provenance"] = repositories[doi]
    retries, lineage, holds = [], [], []
    for t in tasks:
        doi, route = t["study_doi"], t["route_id"]
        decision = decisions.get(doi)
        if decision and decision["action"] == "hold_source_review":
            holds.append({"study_doi": doi, "route_id": route, "task_id": t["task_id"], "reason": decision["reason"]})
            continue
        if not decision and route not in failed:
            continue
        new = repaired_abstract_task(t, decision["fields"], at) if decision else copy.deepcopy(t)
        retries.append(new)
        lineage.append({"study_doi": doi, "route_id": route, "original_task_id": t["task_id"],
                        "replacement_task_id": new["task_id"], "original_fingerprint": t["input_fingerprint"],
                        "replacement_fingerprint": new["input_fingerprint"],
                        "reason": "verified_source_repair_all_routes" if decision else "category_validation_retry",
                        "validation_error": failed.get(route, {}).get("error", "")})
    return {"version": "extraction_input_recovery_v1", "at_utc": at,
            "decisions": list(decisions.values()), "retry_tasks": retries, "lineage": lineage, "held_routes": holds,
            "summary": {"initial_failures": len(failures), "source_flagged_papers": len(source_dois),
                        "repaired_papers": sum(d["action"] == "repair_verified_metadata" for d in decisions.values()),
                        "held_papers": sum(d["action"] == "hold_source_review" for d in decisions.values()),
                        "retry_requests": len(retries), "held_routes": len(holds)}}


def apply_source_plan(plan: dict, plan_path: Path, root: Path) -> dict:
    """Apply reviewed proposals through existing owners, preserving prior rows.

    This intentionally does not rebuild scientific screening or the frozen main
    extraction release. Current metadata/task tables can be refreshed separately.
    """
    targets = {"metadata": root / "data/curated/paper_metadata_overrides.json",
               "holds": root / "pipeline/extract/manual_extraction_route_overrides.json"}
    backup = plan_path.parent / "apply_before"
    receipt = plan_path.with_name(plan_path.stem + "_application.json")
    if receipt.exists():
        return json.loads(receipt.read_text())
    for inp in plan.get("inputs", []):
        if hashlib.sha256(Path(inp["path"]).read_bytes()).hexdigest() != inp["sha256"]:
            raise ValueError("Recovery evidence changed after planning: " + inp["path"])
    for path in targets.values():
        dest = backup / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(path.read_bytes())
    payloads = {k: json.loads(p.read_text()) for k, p in targets.items()}
    for decision in plan["decisions"]:
        kind = "metadata" if decision["action"] == "repair_verified_metadata" else "holds"
        records = payloads[kind]["records"]
        old = next((r for r in records if r.get("doi") == decision["doi"]), None)
        if old is None:
            old = {"doi": decision["doi"]}
            records.append(old)
        if kind == "metadata":
            fields = old.setdefault("fields", {})
            clears = set(old.get("clear_fields", []))
            for key, value in decision["fields"].items():
                if str(value).strip():
                    fields[key] = value
                    clears.discard(key)
                else:
                    fields.pop(key, None)
                    clears.add(key)
            old["clear_fields"] = sorted(clears)
            old["evidence_basis"] = decision["reason"] + " Evidence: " + str(plan_path.resolve())
        else:
            old.update(manual_action="hold_source_review", manual_reason=decision["reason"],
                       evidence_artifact=str(plan_path.resolve()), reviewed_by="automated_identifier_and_title_gate")
    for kind, path in targets.items():
        temp = path.with_suffix(path.suffix + ".tmp")
        write_json(temp, payloads[kind])
        temp.replace(path)
    out = {"plan": str(plan_path.resolve()), "summary": plan["summary"],
           "owner_sha256_after": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in targets.items()}}
    out["handoff_reconciliation"] = reconcile_source_holds(root)
    write_json(receipt, out)
    return out


def reconcile_source_holds(root: Path) -> dict:
    """Project the existing hold owner into candidate and route eligibility.

    Holds must not remain selected when their outputs are withheld. Only
    downstream eligibility fields change; model screening and task/source
    fingerprints are preserved. Existing scientific outputs are never edited.
    """
    import pandas as pd
    from pipeline.ingest.candidate_status import apply_candidate_updates
    from pipeline.workflow.decision_state import write_parquet_atomic
    owner = root / "pipeline/extract/manual_extraction_route_overrides.json"
    candidates_path = root / "data/processed/corpus/candidate_papers.parquet"
    routes_path = root / "data/processed/corpus/paper_extraction_routes.parquet"
    if not all(p.exists() for p in (owner, candidates_path, routes_path)):
        return {"status": "no_materialized_handoff_tables"}
    holds = {r["doi"]: r for r in json.loads(owner.read_text()).get("records", [])
             if r.get("manual_action") == "hold_source_review"}
    updates = pd.DataFrame([{
        "doi": doi, "retained_for_extraction_candidate": False,
        "extraction_route_status": "hold_source_review",
        "extraction_route_reason": record["manual_reason"],
        "extraction_route_actions": "hold_source_review",
        "retained_extraction_route_count": 0,
    } for doi, record in holds.items()])
    if updates.empty:
        return {"status": "no_source_holds"}
    candidates = pd.read_parquet(candidates_path, columns=["doi"])
    missing = sorted(set(holds) - set(candidates["doi"]))
    if missing:
        raise ValueError("Source holds have no canonical candidate: " + str(missing))
    candidate_report = apply_candidate_updates(
        candidate_table=candidates_path, updates=updates,
        column_defaults={"retained_for_extraction_candidate": False,
                         "retained_extraction_route_count": 0})
    routes = pd.read_parquet(routes_path)
    mask = routes["doi"].isin(holds)
    changed = mask & ((routes["route_action"] != "hold_source_review") |
                      routes["retained_for_extraction_candidate"].astype(bool))
    routes.loc[mask, "route_action"] = "hold_source_review"
    routes.loc[mask, "retained_for_extraction_candidate"] = False
    if changed.any():
        write_parquet_atomic(routes, routes_path)
    summary_path = routes_path.with_name("paper_extraction_routes_summary.json")
    if summary_path.exists():
        from pipeline.extract.build_extraction_routes import build_summary, write_counts_csv
        previous = json.loads(summary_path.read_text())
        inputs = dict(previous.get("inputs", {}))
        inputs["manual_override_dois"] = len(json.loads(owner.read_text()).get("records", []))
        summary, counts = build_summary(routes.to_dict("records"), inputs=inputs)
        summary = {**previous, **summary, "candidate_table_update": candidate_report,
                   "source_review_holds_reconciled": len(holds)}
        write_json(summary_path, summary)
        write_counts_csv(routes_path.with_name("paper_extraction_routes_counts.csv"), counts)
    return {"status": "reconciled", "source_held_papers": len(holds),
            "candidate_updates": candidate_report, "route_rows_changed": int(changed.sum()),
            "held_route_rows": int(mask.sum()), "screening_changed": False}


def record_input_replacements(plan: dict, plan_path: Path, run_dir: Path) -> None:
    """Withhold stale answers until every repaired route has a fresh result."""
    replacements_path = run_dir / "input_replacements.json"
    replacements = json.loads(replacements_path.read_text()) if replacements_path.exists() else {"routes": []}
    by_route = {r["route_id"]: r for r in replacements["routes"]}
    by_route.update({r["route_id"]: r for r in plan["lineage"] if r["reason"] == "verified_source_repair_all_routes"})
    replacements.update(routes=list(by_route.values()), source_plan=str(plan_path.resolve()))
    write_json(replacements_path, replacements)


def revalidate_source_artifacts(plan: dict, tasks: list[dict], backup_dir: Path) -> list[dict]:
    """Re-evaluate cached source identities after a gate repair, retaining text.

    Only artifacts belonging to source-flagged reports are touched. This does not
    manufacture article text, delete PDFs, or promote a scientific decision.
    """
    from pipeline.fulltext.source_identity import evaluate_artifact_identity, augment_pdf_artifact_identity
    wanted = {r["doi"] for r in plan["decisions"]}
    seen, results = set(), []
    for task in tasks:
        if task["study_doi"] not in wanted:
            continue
        for value in task.get("text_source", {}).get("fulltext_artifact_paths", []):
            path = Path(value)
            if path in seen:
                continue
            seen.add(path)
            original = path.read_bytes()
            artifact = json.loads(original)
            identity = augment_pdf_artifact_identity(evaluate_artifact_identity(artifact), artifact,
                                                       requested_title=artifact.get("study_title", ""))
            # Existing explicit attestations/aliases must be reconciled through
            # their normal gate, never silently discarded by this generic pass.
            old = artifact.get("source_identity", {})
            if old.get("status") in {"verified_curated_pdf_hash", "verified_identity_override", "verified_related_doi"}:
                results.append({"path": str(path), "status": "existing_explicit_identity_relationship_requires_normal_gate"})
                continue
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (hashlib.sha256(str(path).encode()).hexdigest()[:12] + "_" + path.name)
            if not backup.exists():
                backup.write_bytes(original)
            artifact["source_identity"] = identity
            write_json(path, artifact)
            results.append({"path": str(path), "previous_status": old.get("status"),
                            "new_status": identity["status"], "source_bytes_retained": True,
                            "before_sha256": hashlib.sha256(original).hexdigest()})
    return results


def prepare_retry(plan: dict, plan_path: Path, run_id: str, batch_id: str) -> dict:
    """Prepare standard Luna Batch requests; never submit or retry implicitly."""
    import sys
    from pipeline import llm
    from pipeline.extract import run_route_extraction_batch_api as batch
    tasks_path = plan_path.parent / (batch_id + "_tasks.jsonl")
    argv = sys.argv
    sys.argv = [argv[0], "prepare", "--run-id", run_id, "--batch-id", batch_id,
                "--input-jsonl", str(tasks_path), "--model", "gpt-6-luna", "--retry-errors"]
    try:
        args = batch.normalize_common_args(batch.parse_args())
    finally:
        sys.argv = argv
    paths = batch.batch_paths(args)
    if any(paths[k].exists() for k in ("manifest_json", "requests_jsonl", "job_json")):
        raise ValueError("Retry namespace already exists; reconcile its receipts instead of preparing twice")
    record_input_replacements(plan, plan_path, paths["batch_dir"].parent)
    tasks_path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in plan["retry_tasks"]))
    manifest = batch.write_batch_requests(args)
    if len(manifest["records"]) != len(plan["retry_tasks"]):
        raise ValueError("Prepared selection does not match recovery plan")
    errors = {r["replacement_task_id"]: r for r in plan["lineage"]}
    by_key = {r["key"]: r for r in manifest["records"]}
    requests = []
    for row in read_jsonl(paths["requests_jsonl"]):
        lineage = errors[by_key[row["custom_id"]]["task_id"]]
        if lineage["reason"] == "category_validation_retry":
            row["body"]["input"] += (
                "\n\nVALIDATION RETRY: Re-extract from the same source using the unchanged schema. "
                "Correct the assignments, not merely the warnings. Never force an endpoint into an unrelated "
                "category. Use an accurate existing general/other category, or null when an optional field "
                "cannot be assigned accurately. Human experiments are not preclinical. Body temperature is "
                "not a cardiovascular endpoint; delirium does not establish a psychotic disorder; chemical "
                "stability and neurotransmitter changes do not establish toxicity. Clinical records/interviews "
                "must not become surveys or administrative registries without support. Keep explicit source "
                "descriptions and genuine uncertainties. Return no_extractable_scoped_evidence if the source "
                "has no evidence for this route. Existing validation failure: " + lineage["validation_error"])
        requests.append(row)
    paths["requests_jsonl"].write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests))
    result = {"run_id": run_id, "batch_id": batch_id, "requests": len(requests),
              "tasks_path": str(tasks_path.resolve()), "paths": {k: str(v) for k, v in paths.items()},
              "requests_sha256": hashlib.sha256(paths["requests_jsonl"].read_bytes()).hexdigest(),
              "maximum_reservation_usd": sum(llm.reservation_cost(r["body"], batch=True) for r in requests)}
    write_json(plan_path.parent / (batch_id + "_retry_receipt.json"), result)
    return result


def collect_retry(receipt_path: Path, *, wait: bool = False, poll_seconds: int = 30) -> dict:
    """Collect an existing paid job; this function never uploads or submits."""
    from pipeline import llm
    from pipeline.extract import run_route_extraction_batch_api as batch
    receipt = json.loads(receipt_path.read_text())
    paths = {k: Path(v) for k, v in receipt["paths"].items()}
    args = SimpleNamespace(run_id=receipt["run_id"], batch_id=receipt["batch_id"],
                           input_jsonl=Path(receipt["tasks_path"]), env_file=str(batch.DEFAULT_ENV),
                           model="gpt-6-luna", skip_rebuild=True)
    client = None
    progress_path = receipt_path.with_name(receipt_path.stem + "_collection.json")
    last = None
    while True:
        job_record = json.loads(paths["job_json"].read_text())
        if not job_record.get("job_name"):
            raise ValueError("Submission outcome needs reconciliation; no duplicate submission permitted")
        if paths["parse_report_json"].exists():
            report = json.loads(paths["parse_report_json"].read_text())
            progress = {"status": "parsed", "summary": report["summary"], "job_name": job_record["job_name"]}
            write_json(progress_path, progress)
            return progress
        try:
            if client is None:
                client = llm.client(batch.api_key_from_env(args, required=True))
            job = client.batches.retrieve(job_record["job_name"])
            job_record.update(state=job.status, batch_job=job.model_dump(mode="json"))
            write_json(paths["job_json"], job_record)
            progress = {"status": job.status, "job_name": job.id,
                        "request_counts": job.request_counts.model_dump() if job.request_counts else {}}
            write_json(progress_path, progress)
            if progress != last:
                print(json.dumps(progress), flush=True)
                last = progress
            if job.status in llm.TERMINAL_STATES:
                if not paths["results_jsonl"].exists():
                    job_record.update(llm.download(client, job, paths["results_jsonl"]))
                    write_json(paths["job_json"], job_record)
                report = batch.parse_batch_results(args)
                progress.update(status="parsed", summary=report["summary"])
                write_json(progress_path, progress)
                return progress
        except Exception as exc:
            # Only existing-job reads are retried. Never retry authentication,
            # parse/validation code failures, or ambiguous paid mutations here.
            code = getattr(exc, "status_code", None)
            transient = type(exc).__name__ in {"APIConnectionError", "APITimeoutError"} or code in {408, 429, 500, 502, 503, 504}
            write_json(progress_path, {"status": "transient_read_error" if transient else "action_needed",
                                       "error": str(exc), "job_name": job_record["job_name"]})
            if not wait or not transient:
                raise
        if not wait:
            return progress
        time.sleep(max(5, min(poll_seconds, 60)))


def main() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "evidence":
        p = argparse.ArgumentParser(description="Collect cached/native registry evidence for failed papers.")
        p.add_argument("evidence")
        p.add_argument("--tasks", type=Path, required=True)
        p.add_argument("--cached-pubmed-xml", action="append", default=[])
        p.add_argument("--crossref-cache", type=Path)
        p.add_argument("--out-dir", type=Path, required=True)
        p.add_argument("--offline", action="store_true")
        args = p.parse_args()
        paths = [Path(path) for pattern in args.cached_pubmed_xml for path in glob.glob(pattern)]
        print(json.dumps(collect_registry_evidence(read_jsonl(args.tasks), args.out_dir, pubmed_xml_paths=paths,
                                                   crossref_cache=args.crossref_cache, offline=args.offline), indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        p = argparse.ArgumentParser(description="Collect a previously submitted recovery batch; never submit.")
        p.add_argument("collect")
        p.add_argument("--receipt", type=Path, required=True)
        p.add_argument("--wait", action="store_true")
        args = p.parse_args()
        print(json.dumps(collect_retry(args.receipt, wait=args.wait), indent=2))
        return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tasks", type=Path, required=True)
    p.add_argument("--failures", type=Path, required=True)
    p.add_argument("--native-records", type=Path, required=True)
    p.add_argument("--crossref-records", type=Path, required=True)
    p.add_argument("--at-utc", required=True)
    p.add_argument("--repository-abstract", type=Path, action="append", default=[])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit("Preserving existing plan; choose a new output for a revised evidence set")
    repositories = {r["doi"]: r for r in map(repository_abstract, args.repository_abstract)}
    result = plan_recovery(read_jsonl(args.tasks), read_jsonl(args.failures),
                           json.loads(args.native_records.read_text()),
                           json.loads(args.crossref_records.read_text()), args.at_utc, repositories)
    result["inputs"] = [{"path": str(x.resolve()), "sha256": hashlib.sha256(x.read_bytes()).hexdigest()}
                        for x in (args.tasks, args.failures, args.native_records, args.crossref_records)]
    write_json(args.out, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
