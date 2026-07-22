#!/usr/bin/env python3
"""Build a paper-complete review extraction evaluation cohort.

The normal routed batch runner selects individual paper-domain tasks. This
utility selects review papers first, then exports every ready review-domain
task for each selected DOI. It is retained only to reproduce historical v1
evaluation cohorts. The generic batch API now rejects these task files; all new
review extraction uses the paper-centered review-relationship pipeline.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import task_has_registered_profile
    from pipeline.extract.run_route_extraction import text_depth_for_task
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import task_has_registered_profile
    from pipeline.extract.run_route_extraction import text_depth_for_task


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_OUT_ROOT = ROOT / "data" / "processed" / "evaluation"
REVIEW_SCHEMA_PROFILE = "review_coverage_schema"
STRUCTURED_REVIEW_TYPES = {"systematic_review", "scoping_review", "umbrella_review"}
EVALUATION_DOMAINS = (
    "clinical_outcome",
    "safety_tolerability",
    "molecular_target",
    "molecular_pathway_readout",
    "brain_system",
    "cognitive_behavioral",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_public_health",
)

# A robust review cohort should emphasize full text while retaining an explicit
# abstract-only stratum, cover structured and narrative reviews, and include
# both narrow and broad multi-domain papers.
STRATUM_WEIGHTS = {
    ("article_text", "narrative", "1_2"): 0.126,
    ("article_text", "narrative", "3_4"): 0.162,
    ("article_text", "narrative", "5_plus"): 0.072,
    ("article_text", "structured", "1_2"): 0.084,
    ("article_text", "structured", "3_4"): 0.108,
    ("article_text", "structured", "5_plus"): 0.048,
    ("abstract_only", "narrative", "1_2"): 0.084,
    ("abstract_only", "narrative", "3_4"): 0.108,
    ("abstract_only", "narrative", "5_plus"): 0.048,
    ("abstract_only", "structured", "1_2"): 0.056,
    ("abstract_only", "structured", "3_4"): 0.072,
    ("abstract_only", "structured", "5_plus"): 0.032,
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_doi(value: object) -> str:
    return normalize(value).lower()


def route_domain(task: dict) -> str:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    return normalize(contract.get("domain_route", "")) or normalize(context.get("domain_route", ""))


def source_type(task: dict) -> str:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    return (
        normalize(contract.get("source_type", ""))
        or normalize(context.get("source_type", ""))
        or normalize(context.get("primary_secondary_source_type", ""))
        or "review"
    )


def review_kind(review_type: str) -> str:
    return "structured" if review_type in STRUCTURED_REVIEW_TYPES else "narrative"


def route_count_bin(route_count: int) -> str:
    if route_count <= 2:
        return "1_2"
    if route_count <= 4:
        return "3_4"
    return "5_plus"


def task_sort_key(task: dict) -> tuple[int, str, str]:
    context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    try:
        priority = int(context.get("route_priority", 999))
    except (TypeError, ValueError):
        priority = 999
    return (priority, route_domain(task), normalize(task.get("route_id", "")))


@dataclass(frozen=True)
class ReviewCandidate:
    doi: str
    title: str
    study_year: str
    review_type: str
    text_depth: str
    domains: tuple[str, ...]
    tasks: tuple[dict, ...]

    @property
    def kind(self) -> str:
        return review_kind(self.review_type)

    @property
    def route_bin(self) -> str:
        return route_count_bin(len(self.tasks))

    @property
    def stratum(self) -> tuple[str, str, str]:
        return (self.text_depth, self.kind, self.route_bin)


def build_review_candidates(tasks: list[dict]) -> tuple[list[ReviewCandidate], list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
        if normalize(contract.get("schema_profile", "")) != REVIEW_SCHEMA_PROFILE:
            continue
        doi = normalized_doi(task.get("study_doi", ""))
        if doi:
            grouped[doi].append(task)

    candidates: list[ReviewCandidate] = []
    exclusions: list[dict] = []
    for doi, doi_tasks in sorted(grouped.items()):
        reasons: list[str] = []
        if any(normalize(task.get("task_status", "")) != "ready_for_model" for task in doi_tasks):
            reasons.append("not_all_review_routes_ready")
        if any(not task_has_registered_profile(task) for task in doi_tasks):
            reasons.append("review_route_not_registered")

        domains = [route_domain(task) for task in doi_tasks]
        if any(not domain for domain in domains):
            reasons.append("missing_domain_route")
        if len(set(domains)) != len(domains):
            reasons.append("duplicate_domain_route")

        depths = {text_depth_for_task(task) for task in doi_tasks}
        if len(depths) != 1:
            reasons.append("mixed_text_depth_across_routes")

        route_ids = [normalize(task.get("route_id", "")) for task in doi_tasks]
        if any(not route_id for route_id in route_ids) or len(set(route_ids)) != len(route_ids):
            reasons.append("missing_or_duplicate_route_id")

        if reasons:
            exclusions.append({"doi": doi, "reasons": sorted(set(reasons)), "review_route_count": len(doi_tasks)})
            continue

        ordered_tasks = tuple(sorted(doi_tasks, key=task_sort_key))
        metadata = ordered_tasks[0].get("paper_metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        candidates.append(
            ReviewCandidate(
                doi=doi,
                title=normalize(metadata.get("study_title", "")),
                study_year=normalize(metadata.get("study_year", "")),
                review_type=source_type(ordered_tasks[0]),
                text_depth=next(iter(depths)),
                domains=tuple(route_domain(task) for task in ordered_tasks),
                tasks=ordered_tasks,
            )
        )
    return candidates, exclusions


def stratum_targets(cohort_size: int) -> dict[tuple[str, str, str], int]:
    raw = {key: weight * cohort_size for key, weight in STRATUM_WEIGHTS.items()}
    targets = {key: math.floor(value) for key, value in raw.items()}
    remainder = cohort_size - sum(targets.values())
    ranked = sorted(raw, key=lambda key: (-(raw[key] - targets[key]), key))
    for key in ranked[:remainder]:
        targets[key] += 1
    return targets


def tie_rank(seed: int, doi: str) -> str:
    return hashlib.sha256(f"{seed}:{doi}".encode("utf-8")).hexdigest()


def select_review_cohort(
    candidates: list[ReviewCandidate],
    *,
    cohort_size: int,
    seed: int,
    include_dois: list[str],
    min_domain_papers: int,
) -> tuple[list[ReviewCandidate], dict]:
    if cohort_size <= 0:
        raise ValueError("cohort_size must be positive")
    by_doi = {candidate.doi: candidate for candidate in candidates}
    forced_dois = list(dict.fromkeys(normalized_doi(doi) for doi in include_dois if normalized_doi(doi)))
    missing_forced = [doi for doi in forced_dois if doi not in by_doi]
    if missing_forced:
        raise ValueError(f"Included DOI(s) are not eligible paper-complete reviews: {', '.join(missing_forced)}")
    if len(forced_dois) > cohort_size:
        raise ValueError("Included DOI count exceeds cohort_size")

    targets = stratum_targets(cohort_size)
    selected = [by_doi[doi] for doi in forced_dois]
    selected_dois = set(forced_dois)
    stratum_counts = Counter(candidate.stratum for candidate in selected)
    overfilled = [key for key, count in stratum_counts.items() if count > targets.get(key, 0)]
    if overfilled:
        labels = [f"{key}:{stratum_counts[key]}>{targets.get(key, 0)}" for key in overfilled]
        raise ValueError(f"Included DOI(s) overfill cohort strata: {', '.join(labels)}")

    domain_counts = Counter(domain for candidate in selected for domain in set(candidate.domains))
    remaining = [candidate for candidate in candidates if candidate.doi not in selected_dois]

    while len(selected) < cohort_size:
        eligible = [
            candidate
            for candidate in remaining
            if stratum_counts[candidate.stratum] < targets.get(candidate.stratum, 0)
        ]
        if not eligible:
            raise ValueError("Not enough eligible candidates to satisfy cohort strata")

        def selection_key(candidate: ReviewCandidate) -> tuple[int, int, int, str]:
            candidate_domains = set(candidate.domains)
            deficit_gain = sum(max(0, min_domain_papers - domain_counts[domain]) for domain in candidate_domains)
            unseen_gain = sum(1 for domain in candidate_domains if domain_counts[domain] == 0)
            return (-deficit_gain, -unseen_gain, -len(candidate_domains), tie_rank(seed, candidate.doi))

        chosen = min(eligible, key=selection_key)
        selected.append(chosen)
        selected_dois.add(chosen.doi)
        stratum_counts[chosen.stratum] += 1
        domain_counts.update(set(chosen.domains))
        remaining = [candidate for candidate in remaining if candidate.doi != chosen.doi]

    undercovered = {
        domain: domain_counts[domain]
        for domain in EVALUATION_DOMAINS
        if domain_counts[domain] < min_domain_papers
    }
    if undercovered:
        detail = ", ".join(f"{domain}={count}" for domain, count in undercovered.items())
        raise ValueError(f"Selected cohort does not meet the minimum domain-paper coverage: {detail}")

    selected.sort(key=lambda candidate: candidate.doi)
    report = {
        "cohort_size": len(selected),
        "task_count": sum(len(candidate.tasks) for candidate in selected),
        "included_dois": forced_dois,
        "stratum_targets": {"|".join(key): value for key, value in sorted(targets.items())},
        "stratum_counts": {"|".join(key): value for key, value in sorted(stratum_counts.items())},
        "by_text_depth": dict(Counter(candidate.text_depth for candidate in selected)),
        "by_review_kind": dict(Counter(candidate.kind for candidate in selected)),
        "by_review_type": dict(Counter(candidate.review_type for candidate in selected)),
        "by_route_count_bin": dict(Counter(candidate.route_bin for candidate in selected)),
        "by_route_count": dict(Counter(str(len(candidate.tasks)) for candidate in selected)),
        "papers_by_domain": dict(Counter(domain for candidate in selected for domain in set(candidate.domains))),
        "tasks_by_domain": dict(Counter(domain for candidate in selected for domain in candidate.domains)),
    }
    return selected, report


def cohort_row(candidate: ReviewCandidate, included_dois: set[str]) -> dict:
    return {
        "doi": candidate.doi,
        "study_title": candidate.title,
        "study_year": candidate.study_year,
        "review_type": candidate.review_type,
        "review_kind": candidate.kind,
        "text_depth": candidate.text_depth,
        "route_count": len(candidate.tasks),
        "route_count_bin": candidate.route_bin,
        "routed_domains": list(candidate.domains),
        "known_issue_seed": candidate.doi in included_dois,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_annotation_files(out_dir: Path, selected: list[ReviewCandidate]) -> None:
    paper_fields = [
        "doi",
        "study_title",
        "review_type",
        "text_depth",
        "routed_domains",
        "gold_main_question",
        "gold_scope_summary",
        "source_text_quality",
        "annotator",
        "annotation_status",
        "notes",
    ]
    paper_rows = [
        {
            "doi": candidate.doi,
            "study_title": candidate.title,
            "review_type": candidate.review_type,
            "text_depth": candidate.text_depth,
            "routed_domains": "|".join(candidate.domains),
            "gold_main_question": "",
            "gold_scope_summary": "",
            "source_text_quality": "",
            "annotator": "",
            "annotation_status": "not_started",
            "notes": "",
        }
        for candidate in selected
    ]
    write_csv(out_dir / "paper_annotations.csv", paper_fields, paper_rows)

    relationship_fields = [
        "doi",
        "relationship_id",
        "compound_or_class",
        "entity",
        "entity_type",
        "gold_domain",
        "paper_level_prominence",
        "prominence_basis",
        "summary_statement",
        "evidence_locator",
        "expected_graph_anchor_kind",
        "should_be_graph_visible",
        "annotator",
        "notes",
    ]
    relationship_rows = [
        {
            "doi": candidate.doi,
            "relationship_id": "",
            "compound_or_class": "",
            "entity": "",
            "entity_type": "",
            "gold_domain": "",
            "paper_level_prominence": "",
            "prominence_basis": "",
            "summary_statement": "",
            "evidence_locator": "",
            "expected_graph_anchor_kind": "",
            "should_be_graph_visible": "",
            "annotator": "",
            "notes": "",
        }
        for candidate in selected
    ]
    write_csv(out_dir / "relationship_annotations.csv", relationship_fields, relationship_rows)

    readme = """# Paper-complete review evaluation

This isolated cohort contains every current routed review-domain task for each
selected paper. It does not modify the active KG.

## Annotation

1. Complete one row per paper in `paper_annotations.csv`.
2. In `relationship_annotations.csv`, duplicate the paper's starter row once
   for every substantially discussed compound/class-entity relationship.
3. Use `paper_level_prominence`: `paper_defining`, `major_supporting_topic`,
   `secondary_context`, or `exclude_peripheral`.
4. Base prominence on the title/abstract scope, review objective, dedicated
   sections, tables/figures, repeated synthesis, and review-level conclusions.
5. Annotate full-text and abstract-only papers separately; abstract-only rows
   describe abstract-visible coverage rather than complete article coverage.

After model results are parsed, compare routing, extraction, paper-level
prominence, normalization, and final graph visibility as separate stages.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def build_outputs(
    *,
    tasks_jsonl: Path,
    out_dir: Path,
    cohort_id: str,
    cohort_size: int,
    seed: int,
    include_dois: list[str],
    min_domain_papers: int,
    exclude_dois: list[str] | None = None,
) -> dict:
    tasks = read_jsonl(tasks_jsonl)
    candidates, exclusions = build_review_candidates(tasks)
    excluded = {normalized_doi(doi) for doi in (exclude_dois or []) if normalized_doi(doi)}
    included = {normalized_doi(doi) for doi in include_dois if normalized_doi(doi)}
    overlap = sorted(excluded & included)
    if overlap:
        raise ValueError(f"DOI(s) cannot be both included and excluded: {', '.join(overlap)}")
    candidates = [candidate for candidate in candidates if candidate.doi not in excluded]
    selected, selection = select_review_cohort(
        candidates,
        cohort_size=cohort_size,
        seed=seed,
        include_dois=include_dois,
        min_domain_papers=min_domain_papers,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    cohort_rows = [cohort_row(candidate, included) for candidate in selected]
    selected_tasks = [task for candidate in selected for task in candidate.tasks]

    write_jsonl(out_dir / "cohort.jsonl", cohort_rows)
    write_jsonl(out_dir / "route_extraction_tasks.jsonl", selected_tasks)
    (out_dir / "selected_dois.txt").write_text("\n".join(candidate.doi for candidate in selected) + "\n", encoding="utf-8")
    write_annotation_files(out_dir, selected)

    manifest = {
        "schema_version": "review_paper_complete_evaluation_v1",
        "generated_at_utc": now_utc(),
        "cohort_id": cohort_id,
        "status": "ready_for_batch_prepare",
        "inputs": {
            "tasks_jsonl": str(tasks_jsonl.resolve()),
            "cohort_size": cohort_size,
            "seed": seed,
            "include_dois": [normalized_doi(doi) for doi in include_dois],
            "excluded_doi_count": len(excluded),
            "min_domain_papers": min_domain_papers,
        },
        "candidate_counts": {
            "eligible_papers": len(candidates),
            "excluded_papers": len(exclusions),
        },
        "selection": selection,
        "completeness_checks": {
            "selected_papers": len(selected),
            "exported_tasks": len(selected_tasks),
            "expected_tasks_from_papers": sum(len(candidate.tasks) for candidate in selected),
            "all_selected_review_routes_exported": len(selected_tasks)
            == sum(len(candidate.tasks) for candidate in selected),
            "unique_exported_route_ids": len({normalize(task.get('route_id', '')) for task in selected_tasks}),
            "unique_exported_dois": len({normalized_doi(task.get('study_doi', '')) for task in selected_tasks}),
        },
        "outputs": {
            "cohort_jsonl": str((out_dir / "cohort.jsonl").resolve()),
            "tasks_jsonl": str((out_dir / "route_extraction_tasks.jsonl").resolve()),
            "selected_dois_txt": str((out_dir / "selected_dois.txt").resolve()),
            "paper_annotations_csv": str((out_dir / "paper_annotations.csv").resolve()),
            "relationship_annotations_csv": str((out_dir / "relationship_annotations.csv").resolve()),
            "readme": str((out_dir / "README.md").resolve()),
        },
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS_JSONL)
    parser.add_argument("--cohort-id", default="review_paper_complete_50")
    parser.add_argument("--cohort-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260711)
    parser.add_argument("--include-doi", action="append", default=[])
    parser.add_argument(
        "--exclude-dois-file",
        type=Path,
        default=None,
        help="Optional text file with one DOI per line; these papers are not eligible for selection.",
    )
    parser.add_argument("--min-domain-papers", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cohort_id = normalize(args.cohort_id) or "review_paper_complete_50"
    out_dir = args.out_dir or (DEFAULT_OUT_ROOT / cohort_id)
    exclude_dois = (
        args.exclude_dois_file.read_text(encoding="utf-8").splitlines()
        if args.exclude_dois_file
        else []
    )
    manifest = build_outputs(
        tasks_jsonl=args.tasks_jsonl,
        out_dir=out_dir,
        cohort_id=cohort_id,
        cohort_size=args.cohort_size,
        seed=args.seed,
        include_dois=args.include_doi,
        min_domain_papers=args.min_domain_papers,
        exclude_dois=exclude_dois,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
