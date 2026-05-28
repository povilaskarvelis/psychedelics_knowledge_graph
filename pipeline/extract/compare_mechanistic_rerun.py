#!/usr/bin/env python3
"""Compare a mechanistic extraction rerun against active old outputs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"


def norm(value: object) -> str:
    return str(value or "").strip()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
    return rows


def read_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def doi_key(row: dict) -> str:
    return norm(row.get("study_doi")).lower()


def route_for_result(row: dict) -> str:
    assessment = row.get("paper_assessment") if isinstance(row.get("paper_assessment"), dict) else {}
    return norm(assessment.get("route"))


def claims_for_results(rows: list[dict]) -> list[dict]:
    return [claim for row in rows for claim in (row.get("claims") or []) if isinstance(claim, dict)]


def summarize_results(rows: list[dict]) -> dict:
    claims = claims_for_results(rows)
    return {
        "papers": len(rows),
        "claims": len(claims),
        "routes": dict(Counter(route_for_result(row) for row in rows)),
        "claims_by_graph_entity_type": dict(Counter(norm(claim.get("graph_entity_type")) for claim in claims)),
        "claims_by_entity_role": dict(Counter(norm(claim.get("entity_role")) for claim in claims)),
        "claims_by_support": dict(Counter(norm(claim.get("support")) for claim in claims)),
        "claims_by_evidence_location": dict(Counter(norm(claim.get("evidence_location")) for claim in claims)),
        "unique_raw_entity_labels": len({norm(claim.get("raw_entity_label")).casefold() for claim in claims if norm(claim.get("raw_entity_label"))}),
        "unique_graph_entity_labels": len({norm(claim.get("graph_entity_label")).casefold() for claim in claims if norm(claim.get("graph_entity_label"))}),
    }


def summarize_graph_rows(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "by_graph_entity_type": dict(Counter(norm(row.get("graph_entity_type")) for row in rows)),
        "by_kg_entity_kind_override": dict(Counter(norm(row.get("kg_entity_kind_override")) for row in rows)),
        "by_entity_match_type": dict(Counter(norm(row.get("entity_match_type")) for row in rows)),
        "by_entity_registry_status": dict(Counter(norm(row.get("entity_registry_status")) for row in rows)),
        "unique_canonical_entities": len({norm(row.get("canonical_entity")).casefold() for row in rows if norm(row.get("canonical_entity"))}),
        "top_canonical_entities": Counter(norm(row.get("canonical_entity")) for row in rows if norm(row.get("canonical_entity"))).most_common(30),
    }


def rows_by_selected_doi(rows: list[dict], selected_dois: set[str], *, dataset: str = "") -> list[dict]:
    wanted_dataset = norm(dataset)
    return [
        row
        for row in rows
        if doi_key(row) in selected_dois and (not wanted_dataset or norm(row.get("dataset")) == wanted_dataset)
    ]


def compare_per_paper(selected_inputs: list[dict], old_results_by_doi: dict[str, dict], new_results_by_doi: dict[str, dict], old_graph: list[dict], new_graph: list[dict]) -> list[dict]:
    old_graph_by_doi: dict[str, list[dict]] = {}
    new_graph_by_doi: dict[str, list[dict]] = {}
    for row in old_graph:
        old_graph_by_doi.setdefault(doi_key(row), []).append(row)
    for row in new_graph:
        new_graph_by_doi.setdefault(doi_key(row), []).append(row)

    rows = []
    for input_row in selected_inputs:
        doi = doi_key(input_row)
        old_result = old_results_by_doi.get(doi, {})
        new_result = new_results_by_doi.get(doi, {})
        old_claims = old_result.get("claims") or []
        new_claims = new_result.get("claims") or []
        old_graph_rows = old_graph_by_doi.get(doi, [])
        new_graph_rows = new_graph_by_doi.get(doi, [])
        old_entities = {norm(row.get("canonical_entity")) for row in old_graph_rows if norm(row.get("canonical_entity"))}
        new_entities = {norm(row.get("canonical_entity")) for row in new_graph_rows if norm(row.get("canonical_entity"))}
        rows.append(
            {
                "study_doi": norm(input_row.get("study_doi")),
                "study_title": norm((input_row.get("paper_metadata") or {}).get("study_title")),
                "bucket": norm(input_row.get("bucket")),
                "old_route": route_for_result(old_result),
                "new_route": route_for_result(new_result),
                "old_claims": len(old_claims),
                "new_claims": len(new_claims),
                "old_graph_rows": len(old_graph_rows),
                "new_graph_rows": len(new_graph_rows),
                "new_graph_entity_types": dict(Counter(norm(row.get("graph_entity_type")) for row in new_graph_rows)),
                "new_canonical_entities_added": sorted(new_entities - old_entities)[:50],
                "old_canonical_entities_dropped": sorted(old_entities - new_entities)[:50],
            }
        )
    return rows


def markdown_summary(report: dict) -> str:
    old_g = report["old_graph_summary"]
    new_g = report["new_graph_summary"]
    old_r = report["old_result_summary"]
    new_r = report["new_result_summary"]
    parse = report.get("parse_summary", {})
    lines = [
        f"# {report['tag']} Comparison",
        "",
        "## Parse Health",
        f"- Selected papers: {report['selected_papers']}",
        f"- New parsed outputs: {new_r['papers']}",
        f"- Parse status counts: {parse.get('status_counts', {})}",
        f"- New route counts: {new_r['routes']}",
        "",
        "## Claim-Level Change",
        f"- Old claims: {old_r['claims']}",
        f"- New claims: {new_r['claims']}",
        f"- Old claim entity types: {old_r['claims_by_graph_entity_type']}",
        f"- New claim entity types: {new_r['claims_by_graph_entity_type']}",
        f"- Old entity roles: {old_r['claims_by_entity_role']}",
        f"- New entity roles: {new_r['claims_by_entity_role']}",
        "",
        "## Normalized Graph Change",
        f"- Old normalized graph rows: {old_g['rows']}",
        f"- New normalized graph rows: {new_g['rows']}",
        f"- Old graph entity types: {old_g['by_graph_entity_type']}",
        f"- New graph entity types: {new_g['by_graph_entity_type']}",
        f"- Old unique canonical entities: {old_g['unique_canonical_entities']}",
        f"- New unique canonical entities: {new_g['unique_canonical_entities']}",
        "",
        "## Top New Canonical Entities",
    ]
    lines.extend(f"- {name}: {count}" for name, count in new_g["top_canonical_entities"][:20])
    lines.extend(["", "## Per-Paper Rows With Largest New Graph Increase"])
    per_paper = sorted(report["per_paper"], key=lambda row: row["new_graph_rows"] - row["old_graph_rows"], reverse=True)
    for row in per_paper[:15]:
        lines.append(
            f"- {row['study_doi']}: old {row['old_graph_rows']} -> new {row['new_graph_rows']}; "
            f"types {row['new_graph_entity_types']}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="mechanistic_fulltext_rerun50_20260526")
    parser.add_argument("--selected-input-jsonl", default="")
    parser.add_argument("--old-output-jsonl", default=str(EXTRACTION_DIR / "extraction_v1_outputs.active_20260525.jsonl"))
    parser.add_argument("--old-graph-json", default=str(EXTRACTION_DIR / "mechanistic_graph_claims.json"))
    parser.add_argument("--new-output-jsonl", default="")
    parser.add_argument("--new-graph-json", default="")
    parser.add_argument("--parse-report-json", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    tag = norm(args.tag)
    selected_input_jsonl = Path(args.selected_input_jsonl or EXTRACTION_DIR / f"extraction_v1_pilot_inputs.{tag}.jsonl").resolve()
    new_output_jsonl = Path(args.new_output_jsonl or EXTRACTION_DIR / f"extraction_v1_outputs.{tag}.jsonl").resolve()
    new_graph_json = Path(args.new_graph_json or EXTRACTION_DIR / f"{tag}_mechanistic_graph_claims.json").resolve()
    parse_report_json = Path(args.parse_report_json or EXTRACTION_DIR / f"extraction_v1_report.{tag}.json").resolve()
    out_json = Path(args.out_json or EXTRACTION_DIR / f"{tag}_comparison_report.json").resolve()
    out_md = Path(args.out_md or EXTRACTION_DIR / f"{tag}_comparison_report.md").resolve()

    selected_inputs = read_jsonl(selected_input_jsonl)
    selected_dois = {doi_key(row) for row in selected_inputs if doi_key(row)}
    old_results = rows_by_selected_doi(read_jsonl(Path(args.old_output_jsonl).resolve()), selected_dois, dataset="mechanistic")
    new_results = rows_by_selected_doi(read_jsonl(new_output_jsonl), selected_dois, dataset="mechanistic")
    old_graph = rows_by_selected_doi(read_json_array(Path(args.old_graph_json).resolve()), selected_dois)
    new_graph = rows_by_selected_doi(read_json_array(new_graph_json), selected_dois)
    old_by_doi = {doi_key(row): row for row in old_results}
    new_by_doi = {doi_key(row): row for row in new_results}

    report = {
        "tag": tag,
        "inputs": {
            "selected_input_jsonl": str(selected_input_jsonl),
            "old_output_jsonl": str(Path(args.old_output_jsonl).resolve()),
            "old_graph_json": str(Path(args.old_graph_json).resolve()),
            "new_output_jsonl": str(new_output_jsonl),
            "new_graph_json": str(new_graph_json),
            "parse_report_json": str(parse_report_json),
        },
        "selected_papers": len(selected_inputs),
        "missing_old_outputs": sorted(selected_dois - set(old_by_doi)),
        "missing_new_outputs": sorted(selected_dois - set(new_by_doi)),
        "parse_summary": read_json_object(parse_report_json).get("summary", {}),
        "old_result_summary": summarize_results(old_results),
        "new_result_summary": summarize_results(new_results),
        "old_graph_summary": summarize_graph_rows(old_graph),
        "new_graph_summary": summarize_graph_rows(new_graph),
        "per_paper": compare_per_paper(selected_inputs, old_by_doi, new_by_doi, old_graph, new_graph),
    }
    write_json(out_json, report)
    out_md.write_text(markdown_summary(report), encoding="utf-8")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
