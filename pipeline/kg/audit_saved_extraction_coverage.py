"""Read-only, release-scoped coverage accounting for every extraction family.

This reports processing locations, not scientific correctness or recommended
reruns. A task may produce several projections; report, task, object and edge
counts are deliberately separate. Graph areas overlap and share profiles.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.kg.assemble_combined_release import read_aliases, resolve_doi
from pipeline.kg.convert_routed_extractions_to_evidence_rows import result_items
from pipeline.kg.graph_view_contract import graph_view_definitions, record_matches_graph_view


def jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def output_objects(output: dict) -> list[dict]:
    result = output.get("result") or {}
    if isinstance(result.get("relationships"), list):
        return [x for x in result["relationships"] if isinstance(x, dict)]
    return result_items(result)[1]


def paper_disposition(normalized: int, main: int, audits: int) -> str:
    if main:
        return "main_graph"
    if normalized:
        return "detail_only"
    if audits:
        return "audit_only"
    return "no_converted_rows"


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def audit(release: Path, kg: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if (out / "summary.json").exists():
        raise FileExistsError("Use a new output directory; preserve completed audits")
    inputs = release / "inputs"
    alias_path = inputs / "doi_alias_registry.json"
    aliases = read_aliases(alias_path)
    canonical = lambda value: resolve_doi(value, aliases)
    scope_path = release / "selected_dois.txt"
    scope = {canonical(x.strip()) for x in scope_path.read_text().splitlines() if x.strip()}
    task_rows, task_keys, outputs_by_paper = [], set(), defaultdict(list)
    family_by_paper = defaultdict(set)
    files = [alias_path, scope_path]
    missing, duplicate, identity_conflicts = [], [], []
    for family in ("primary", "review", "meta"):
        task_path = inputs / f"{family}_tasks.jsonl"
        output_path = inputs / f"{family}_outputs.jsonl"
        files.extend([task_path, output_path])
        tasks = {}
        for task in jsonl(task_path):
            key = str(task.get("task_id", ""))
            doi = canonical(task.get("study_doi") or task.get("paper_metadata", {}).get("doi"))
            if doi not in scope:
                continue
            if key in tasks:
                raise ValueError(f"Duplicate task ID in {task_path}: {key}")
            tasks[key] = (doi, task.get("input_fingerprint", ""))
        seen = set()
        for output in jsonl(output_path):
            doi = canonical(output.get("study_doi"))
            if doi not in scope:
                continue
            key = str(output.get("task_id", ""))
            if key in seen:
                duplicate.append({"family": family, "task_id": key, "doi": doi})
            seen.add(key)
            if key not in tasks:
                missing.append({"family": family, "task_id": key, "doi": doi})
            elif tasks[key][0] != doi or (tasks[key][1] and output.get("input_fingerprint") and tasks[key][1] != output["input_fingerprint"]):
                identity_conflicts.append({"family": family, "task_id": key, "doi": doi})
            result = output.get("result") or {}
            row = {
                "doi": doi, "family": family, "task_id": key,
                "profile": output.get("prompt_profile") or family,
                "domain": result.get("domain_route", ""),
                "status": output.get("status", ""),
                "extraction_status": result.get("extraction_status", "not_used_by_contract"),
                "object_count": len(output_objects(output)),
            }
            task_rows.append(row)
            task_keys.add((family, key))
            outputs_by_paper[doi].append(row)
            family_by_paper[doi].add(family)
        for key in sorted(set(tasks) - seen):
            missing.append({"family": family, "task_id": key, "doi": tasks[key][0], "kind": "task_without_output"})

    f = pd.read_parquet(kg / "findings.parquet", columns=["study_doi", "domain", "graph_admission_status", "graph_admission_reason"])
    a = pd.read_parquet(kg / "normalization_audit.parquet", columns=["study_doi", "domain", "normalization_status"])
    e = pd.read_parquet(kg / "evidence_edges.parquet", columns=["study_doi", "domain", "entity_kind", "entity_label", "graph_admission_status", "access_level"])
    for frame in (f, a, e):
        frame["study_doi"] = frame.study_doi.map(canonical)
        unexpected = set(frame.study_doi) - scope
        if unexpected:
            raise ValueError(f"Normalized rows outside selected report cohort: {sorted(unexpected)[:10]}")
    files.extend(kg / name for name in ("findings.parquet", "normalization_audit.parquet", "evidence_edges.parquet"))
    normalized = Counter(f.study_doi)
    main = Counter(f.loc[f.graph_admission_status.eq("main_graph"), "study_doi"])
    audits = Counter(a.study_doi)
    audit_reasons = {d: dict(Counter(g.normalization_status)) for d, g in a.groupby("study_doi")}
    detail_reasons = {d: dict(Counter(g.graph_admission_reason)) for d, g in f.loc[f.graph_admission_status.ne("main_graph")].groupby("study_doi")}
    views = graph_view_definitions()
    area_rows, paper_areas, paper_main_areas = [], defaultdict(set), defaultdict(set)
    edge_records = e.fillna("").to_dict("records")
    # Cache only semantic combinations; do not infer area from a shared profile.
    signatures = {}
    for edge in edge_records:
        sig = (edge["entity_kind"], edge["entity_label"], edge["domain"])
        if sig not in signatures:
            signatures[sig] = [v["id"] for v in views if record_matches_graph_view(edge, v["id"])]
        edge["areas"] = signatures[sig]
        for area in edge["areas"]:
            paper_areas[edge["study_doi"]].add(area)
            if edge["graph_admission_status"] == "main_graph":
                paper_main_areas[edge["study_doi"]].add(area)
    for view in views:
        for family in ("primary", "review", "meta"):
            rows = [x for x in edge_records if view["id"] in x["areas"] and family in family_by_paper[x["study_doi"]]]
            ids = {x["study_doi"] for x in rows}
            mids = {x["study_doi"] for x in rows if x["graph_admission_status"] == "main_graph"}
            area_rows.append({"area": view["id"], "label": view["label"], "response_family": family, "reports_with_area_evidence": len(ids), "reports_with_main_area_evidence": len(mids), "area_detail_only_reports": len(ids - mids), "edge_rows": len(rows)})

    papers = []
    for doi in sorted(scope):
        outs = outputs_by_paper[doi]
        papers.append({"doi": doi, "response_families": sorted(family_by_paper[doi]), "disposition": paper_disposition(normalized[doi], main[doi], audits[doi]), "tasks": len(outs), "objects": sum(x["object_count"] for x in outs), "empty_tasks": sum(x["object_count"] == 0 for x in outs), "extraction_statuses": dict(Counter(x["extraction_status"] for x in outs)), "finding_rows": normalized[doi], "main_finding_rows": main[doi], "audit_rows": audits[doi], "audit_reasons": audit_reasons.get(doi, {}), "detail_reasons": detail_reasons.get(doi, {}), "areas_with_normalized_evidence": sorted(paper_areas[doi]), "areas_with_main_evidence": sorted(paper_main_areas[doi])})
    by_profile = []
    for family, profile in sorted({(x["family"], x["profile"]) for x in task_rows}):
        rows = [x for x in task_rows if (x["family"], x["profile"]) == (family, profile)]
        by_profile.append({"family": family, "profile": profile, "tasks": len(rows), "reports": len({x["doi"] for x in rows}), "objects": sum(x["object_count"] for x in rows), "empty_tasks": sum(x["object_count"] == 0 for x in rows), "empty_statuses": dict(Counter(x["extraction_status"] for x in rows if x["object_count"] == 0))})
    domain_reasons = []
    for domain in sorted(set(f.domain) | set(a.domain)):
        af = a[a.domain.eq(domain)]; df = f[f.domain.eq(domain) & f.graph_admission_status.ne("main_graph")]
        domain_reasons.append({"domain": domain, "audit_rows": len(af), "audit_reports": af.study_doi.nunique(), "audit_statuses": dict(Counter(af.normalization_status)), "detail_rows": len(df), "detail_reports": df.study_doi.nunique(), "detail_reasons": dict(Counter(df.graph_admission_reason))})
    summary = {"schema_version": "saved_extraction_coverage_audit_v1", "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "release": str(release.resolve()), "kg": str(kg.resolve()), "reports": len(scope), "tasks": len(task_rows), "objects": sum(x["object_count"] for x in task_rows), "paper_dispositions": dict(Counter(x["disposition"] for x in papers)), "missing_output_reports": sorted(scope - set(outputs_by_paper)), "task_join_issues": {"missing": missing, "duplicates": duplicate, "identity_conflicts": identity_conflicts}, "profiles": by_profile, "domain_hold_reasons": domain_reasons, "input_hashes": {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, "meaning": "Processing counts, not error rates or scientific judgments. Area memberships and response families can overlap; domains/profiles are not graph-view synonyms. Main admission and normalized detail are separate. No source, model, screening or graph changes."}
    summary["response_status_counts"] = dict(Counter(x["status"] for x in task_rows))
    summary["reports_without_saved_objects"] = sum(x["objects"] == 0 for x in papers)
    summary["reports_with_objects_but_no_converted_rows"] = sum(x["objects"] > 0 and x["disposition"] == "no_converted_rows" for x in papers)
    summary["reports_with_multiple_response_families"] = [x["doi"] for x in papers if len(x["response_families"]) > 1]
    summary["audit_implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary["graph_view_contract_sha256"] = hashlib.sha256((Path(__file__).resolve().parents[2] / "schema/graph_view_contract.json").read_bytes()).hexdigest()
    write_jsonl(out / "papers.jsonl", papers)
    write_jsonl(out / "tasks.jsonl", task_rows)
    write_json(out / "area_family_counts.json", area_rows)
    write_json(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--kg", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.release, args.kg, args.out)
    print(json.dumps({key: result[key] for key in ("reports", "tasks", "objects", "paper_dispositions", "missing_output_reports", "task_join_issues")}))


if __name__ == "__main__":
    main()
