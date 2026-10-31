"""Freeze a stratified paired source-check sample from graph comparison artifacts.

No network/model calls or eligibility mutations. Existing audit cases can be
excluded to form a fresh sample. Source packets preserve input provenance; their
presence is not a claim that a source has been reviewed.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import pandas as pd


def lines(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(comparison, normalization, out, seed, counts):
    from pipeline.fulltext.build_llm_evidence_packets import best_extraction
    from pipeline.review.audit_screening_correction_fulltext import article_body
    from pipeline.kg.graph_view_contract import record_matches_graph_view
    comparison, normalization, out = map(Path, (comparison, normalization, out))
    if (out / "sample.json").exists():
        raise FileExistsError("Frozen sample already exists; use a new output directory")
    out.mkdir(parents=True, exist_ok=True)
    old_cases = json.loads((comparison / "source_check_sample_frozen.json").read_text())
    excluded = {p["doi"].lower() for p in old_cases["papers"]}
    meta_cases = comparison / "seven_meta_lost_validated_source_packets.json"
    if meta_cases.exists():
        excluded.update(p["candidate"]["doi"].lower() for p in json.loads(meta_cases.read_text()))
    members = defaultdict(dict)
    for row in lines(comparison / "area_paper_membership.jsonl"):
        members[row["version"], row["family"], row["area"]][row["key"]] = row
    transitions = defaultdict(list)
    for row in lines(comparison / "paper_area_transitions.jsonl"):
        transitions[row["family"], row["direction"], row["area"]].append(row)
    areas = sorted({k[2] for k in members})
    used = set(excluded)
    sample, strata = [], []

    def rank(value):
        return hashlib.sha256(f"{seed}|{value}".encode()).hexdigest()

    for family, requested in counts.items():
        assert requested % 3 == 0
        for direction in ("removed", "added", "shared"):
            pools = {}
            for area in areas:
                if direction == "shared":
                    old, new = members["deployed", family, area], members["luna_preview", family, area]
                    pool = [{"family": family, "area": area, "direction": direction, "key": key,
                             "old": old[key], "new": new[key], "reason": "present_in_both"}
                            for key in set(old) & set(new)]
                else:
                    pool = transitions[family, direction, area]
                pools[area] = sorted(pool, key=lambda x: rank(f"{family}|{direction}|{area}|{x['key']}"))
                strata.append({"family": family, "direction": direction, "area": area, "pool_memberships": len(pool)})
            picked = 0
            order = sorted(areas, key=lambda a: rank(f"area-order|{family}|{direction}|{a}"))
            while picked < requested // 3:
                progress = False
                for area in order:
                    while pools[area]:
                        row = pools[area].pop(0)
                        doi = str((row.get("old") or row.get("new"))["doi"]).lower()
                        if doi in used:
                            continue
                        used.add(doi)
                        sample.append({**row, "doi": doi, "index": len(sample)})
                        picked += 1
                        progress = True
                        break
                    if picked == requested // 3:
                        break
                if not progress:
                    raise ValueError(f"Insufficient fresh unique papers: {family}/{direction} {picked}")
    picked_dois = {r["doi"] for r in sample}
    manifest = {"seed": seed, "requested_by_family": counts, "excluded_previous_cases": sorted(excluded),
                "design": "Equal change-direction quotas within family; round-robin areas, SHA256 rank, global report deduplication. Diagnostic stratified sample, not self-weighting population accuracy.",
                "strata": strata, "papers": sample,
                "input_sha256": {str(comparison / name): sha(comparison / name) for name in
                                 ("area_paper_membership.jsonl", "paper_area_transitions.jsonl", "source_check_sample_frozen.json")}}
    (out / "sample.json").write_text(json.dumps(manifest, indent=2) + "\n")
    candidate_path = normalization / "inputs/candidate_papers.parquet"
    columns = ["doi", "study_title", "abstract", "pmid", "pmcid"]
    candidate = {str(r["doi"]).lower(): r for r in pd.read_parquet(candidate_path, columns=columns).fillna("").to_dict("records") if str(r["doi"]).lower() in picked_dois}
    evidence = defaultdict(dict)
    for row in lines(comparison / "paper_evidence_index.jsonl"):
        if row["doi"] in picked_dois:
            evidence[row["doi"]][row["version"]] = row["findings"]
    routes = pd.read_parquet(normalization / "inputs/paper_extraction_routes.parquet").fillna("")
    route_by, paths = defaultdict(list), defaultdict(list)
    for row in routes.to_dict("records"):
        doi = str(row["doi"]).lower()
        if doi not in picked_dois:
            continue
        route_by[doi].append({k: row[k] for k in ("domain_route", "route_action", "domain_screening_reason", "source_type") if k in row})
        for p in str(row.get("fulltext_artifact_paths", "")).split("|"):
            if p and p not in paths[doi]:
                paths[doi].append(p)
    outputs = defaultdict(list)
    for family in ("primary", "review", "meta"):
        for row in lines(normalization / "inputs" / f"{family}_outputs.jsonl"):
            doi = str(row.get("study_doi", "")).lower()
            if doi in picked_dois:
                outputs[doi].append(row)
    (out / "bodies").mkdir(exist_ok=True)
    body_count = 0
    with (out / "source_packets.jsonl").open("w") as f, (out / "saved_model_outputs.jsonl").open("w") as m:
        for row in sample:
            doi, index = row["doi"], row["index"]
            source = None
            guessed = Path.cwd() / "data/processed/fulltext/articles" / (re.sub("[^a-z0-9]+", "_", doi).strip("_") + ".json")
            for path in [Path(p) for p in paths[doi]] + [guessed]:
                if not path.exists():
                    continue
                artifact = json.loads(path.read_text())
                if str(artifact.get("study_doi", "")).lower() != doi:
                    continue
                extraction = best_extraction(artifact)
                try:
                    body = article_body(extraction.get("text", ""), backend=extraction.get("backend"))
                except Exception:
                    continue
                if len(body) < 1000:
                    continue
                body_path = out / "bodies" / f"{index:03}.txt"
                body_path.write_text(body)
                source = {"path": str(body_path), "sha256": sha(body_path), "artifact": str(path),
                          "artifact_sha256": sha(path), "saved_doi": doi, "body_chars": len(body)}
                body_count += 1
                break
            def subset(version):
                all_rows = evidence[doi].get(version, [])
                selected = [r for r in all_rows if record_matches_graph_view(r, row["area"])]
                return selected or all_rows
            packet = {"index": index, "doi": doi, "family": row["family"], "area": row["area"],
                      "finding_selection": "Sampled-area findings when present; otherwise all indexed report findings. Absence is not whole-report or extraction absence.",
                      "change": row["direction"], "stage": row["reason"], "source_metadata": candidate.get(doi, {}),
                      "saved_body": source, "old_findings": subset("deployed"), "new_findings": subset("luna_preview"),
                      "routes": route_by[doi]}
            f.write(json.dumps(packet, ensure_ascii=False, default=str) + "\n")
            m.write(json.dumps({"index": index, "doi": doi, "outputs": outputs[doi]}, ensure_ascii=False) + "\n")
    summary = {"unique_papers": len(sample), "saved_bodies_available": body_count, "reviewed_papers": 0,
               "by_family": dict(Counter(x["family"] for x in sample)), "by_direction": dict(Counter(x["direction"] for x in sample)),
               "no_overlap_with_previous_sample": not (picked_dois & excluded), "candidate_sha256": sha(candidate_path)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--primary", type=int, default=300)
    parser.add_argument("--reviews", type=int, default=120)
    parser.add_argument("--meta", type=int, default=60)
    args = parser.parse_args()
    print(json.dumps(prepare(args.comparison, args.normalization, args.out, args.seed,
                             {"primary": args.primary, "reviews": args.reviews, "meta_analyses": args.meta}), indent=2))


if __name__ == "__main__":
    main()
