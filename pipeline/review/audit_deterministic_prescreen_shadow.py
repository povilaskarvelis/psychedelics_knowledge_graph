#!/usr/bin/env python3
"""Shadow-audit the current deterministic abstract pre-screen.

The audit is read-only with respect to pipeline state. It recomputes current
deterministic decisions over previously screened rows, compares them with old
deterministic and LLM-screened decisions, and checks graph-producing DOIs for
potential false negatives.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from pipeline.review.run_local_llm_abstract_screening import (
        AMBIGUOUS_ACRONYM_SUPPORT_TERMS,
        AMBIGUOUS_CLASS_SUPPORT_TERMS,
        AMBIGUOUS_INTERVENTION_ACRONYMS,
        AMBIGUOUS_INTERVENTION_CLASS_TERMS,
        AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS,
        LSD_NON_PSYCH_ACRONYM_RE,
        LSD_PSYCH_SUPPORT_RE,
        SORTED_IN_SCOPE_INTERVENTION_TERMS,
        is_ketamine_only_acute_care_anesthesia_context,
        matched_targeted_intervention_terms,
    )
    from pipeline.review.triage_paper_library import load_json_array, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.run_local_llm_abstract_screening import (
        AMBIGUOUS_ACRONYM_SUPPORT_TERMS,
        AMBIGUOUS_CLASS_SUPPORT_TERMS,
        AMBIGUOUS_INTERVENTION_ACRONYMS,
        AMBIGUOUS_INTERVENTION_CLASS_TERMS,
        AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS,
        LSD_NON_PSYCH_ACRONYM_RE,
        LSD_PSYCH_SUPPORT_RE,
        SORTED_IN_SCOPE_INTERVENTION_TERMS,
        is_ketamine_only_acute_care_anesthesia_context,
        matched_targeted_intervention_terms,
    )
    from pipeline.review.triage_paper_library import load_json_array, normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
IN_SCOPE_TERM_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(term) for term in sorted(SORTED_IN_SCOPE_INTERVENTION_TERMS, key=len, reverse=True))})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
ACRONYM_SUPPORT_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(term) for term in sorted(AMBIGUOUS_ACRONYM_SUPPORT_TERMS, key=len, reverse=True))})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
CLASS_SUPPORT_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(term) for term in sorted(AMBIGUOUS_CLASS_SUPPORT_TERMS, key=len, reverse=True))})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
AMBIGUOUS_PSYCHIATRIC_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(term) for term in sorted(AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS, key=len, reverse=True))})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def load_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def norm_action(action: object) -> str:
    value = normalize(action)
    return value or "missing"


def action_is_retained(action: object) -> bool:
    return norm_action(action) != "exclude_obvious_irrelevant"


def dataset_key(dataset: object, doi: object) -> tuple[str, str]:
    return (normalize(dataset), normalize_doi(doi))


def dedupe_rows(rows: Iterable[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in rows:
        key = dataset_key(row.get("dataset", ""), row.get("study_doi", ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def load_paper_rows(paths: Iterable[Path]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in paths:
        if not path.exists():
            continue
        dataset = "mechanistic" if "mechanistic" in path.name else "disorder" if "disorder" in path.name else ""
        for row in load_json_array(path):
            doi = normalize_doi(row.get("study_doi", ""))
            if dataset and doi:
                out.setdefault((dataset, doi), row)
    return out


def rows_by_doi(rows: Iterable[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out.setdefault(doi, row)
    return out


def current_decision(dataset: str, row: dict, cache: dict[tuple[str, str], dict]) -> dict:
    doi = normalize_doi(row.get("study_doi", ""))
    key = (dataset, doi) if doi else ("", "")
    if key in cache:
        return cache[key]
    context = normalize(row.get("study_title", "")) + "\n" + normalize(row.get("abstract", ""))
    matches = fast_matched_in_scope_terms(context)
    if matches and is_ketamine_only_acute_care_anesthesia_context(
        context,
        matches,
        title=normalize(row.get("study_title", "")),
    ):
        decision = {
            "action": "exclude_obvious_irrelevant",
            "reason": (
                "Ketamine/esketamine/arketamine appears only in an acute procedural anesthesia or sedation "
                "context, without psychiatric, chronic pain, brain/cognition, safety, or mechanistic KG signals."
            ),
            "matched_terms": matches[:20],
        }
    elif matches:
        decision = {
            "action": "escalate",
            "reason": "in-scope compound/intervention term appears in title or abstract",
            "matched_terms": matches[:20],
        }
    elif AMBIGUOUS_PSYCHIATRIC_RE.search(context):
        decision = {"action": "escalate", "reason": "broad psychiatric treatment language needs LLM review"}
    else:
        decision = {
            "action": "exclude_obvious_irrelevant",
            "reason": "No in-scope psychedelic/ketamine/entactogen/dissociative compound or intervention term appears in the title/abstract.",
        }
    if doi:
        cache[key] = decision
    return decision


def fast_matched_in_scope_terms(context: str) -> list[str]:
    acronym_supported = bool(ACRONYM_SUPPORT_RE.search(context))
    class_supported = bool(CLASS_SUPPORT_RE.search(context))
    seen: set[str] = set()
    out: list[str] = []
    for match in IN_SCOPE_TERM_RE.finditer(context):
        term = normalize(match.group(0))
        key = term.lower()
        if key == "lsd" and LSD_NON_PSYCH_ACRONYM_RE.search(context) and not LSD_PSYCH_SUPPORT_RE.search(context):
            continue
        if key in AMBIGUOUS_INTERVENTION_ACRONYMS and not acronym_supported:
            continue
        if key in AMBIGUOUS_INTERVENTION_CLASS_TERMS and not class_supported:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    for term in matched_targeted_intervention_terms(context):
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def report_row_from_old_row(dataset: str, old_row: dict, paper_lookup: dict[str, dict]) -> dict:
    doi = normalize_doi(old_row.get("study_doi", ""))
    paper_row = paper_lookup.get(doi, {})
    if paper_row:
        return paper_row
    return {
        "study_doi": doi,
        "study_title": normalize(old_row.get("study_title", "")),
        "study_year": normalize(old_row.get("study_year", "")),
        "authors": normalize(old_row.get("authors", "")),
        "abstract": "",
    }


def matched_terms_string(decision: dict) -> str:
    terms = decision.get("matched_terms", [])
    return "|".join(str(term) for term in terms[:20]) if isinstance(terms, list) else ""


def audit_deterministic_report(path: Path, decision_cache: dict[tuple[str, str], dict]) -> tuple[dict, list[dict]]:
    payload = load_json_object(path)
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    dataset = normalize(payload.get("dataset", "")) or ("mechanistic" if "mechanistic" in path.name else "disorder")
    paper_db_path = Path(payload.get("inputs", {}).get("paper_db_json", ""))
    paper_lookup = rows_by_doi(load_json_array(paper_db_path)) if paper_db_path.exists() else {}
    counters: Counter[str] = Counter()
    deltas: list[dict] = []

    for old_row in rows:
        doi = normalize_doi(old_row.get("study_doi", ""))
        if not doi:
            counters["missing_doi"] += 1
            continue
        source_row = report_row_from_old_row(dataset, old_row, paper_lookup)
        old_action = norm_action(old_row.get("deterministic_prescreen_action", ""))
        decision = current_decision(dataset, source_row, decision_cache)
        new_action = norm_action(decision.get("action", ""))
        counters["rows"] += 1
        counters[f"old_{old_action}"] += 1
        counters[f"new_{new_action}"] += 1
        counters["has_abstract"] += int(bool(normalize(source_row.get("abstract", ""))))
        counters["changed"] += int(old_action != new_action)
        if action_is_retained(old_action) and not action_is_retained(new_action):
            counters["old_retained_new_excluded"] += 1
        if not action_is_retained(old_action) and action_is_retained(new_action):
            counters["old_excluded_new_retained"] += 1
        if old_action != new_action:
            deltas.append(
                {
                    "comparison": "old_deterministic_vs_current",
                    "report": str(path.relative_to(ROOT)),
                    "dataset": dataset,
                    "study_doi": doi,
                    "study_title": normalize(source_row.get("study_title", "")),
                    "old_action": old_action,
                    "new_action": new_action,
                    "has_abstract": bool(normalize(source_row.get("abstract", ""))),
                    "matched_terms": matched_terms_string(decision),
                    "new_reason": normalize(decision.get("reason", "")),
                }
            )

    summary = {
        "report": str(path.relative_to(ROOT)),
        "dataset": dataset,
        "old_summary": payload.get("summary", {}),
        **dict(counters),
    }
    return summary, deltas


def llm_row_flat(row: dict) -> dict:
    flat = row.get("flat", {})
    return flat if isinstance(flat, dict) else {}


def llm_row_doi(row: dict) -> str:
    flat = llm_row_flat(row)
    return normalize_doi(
        flat.get("study_doi", "")
        or row.get("input_row", {}).get("study_doi", "")
        or row.get("candidate_metadata", {}).get("study_doi", "")
    )


def llm_row_dataset(row: dict, path: Path, payload: dict) -> str:
    flat = llm_row_flat(row)
    return normalize(flat.get("dataset", "")) or normalize(payload.get("dataset", "")) or (
        "mechanistic" if "mechanistic" in path.name else "disorder"
    )


def llm_relevance(row: dict) -> str:
    flat = llm_row_flat(row)
    adjudication = row.get("adjudication", {})
    return normalize(flat.get("llm_relevance", "") or adjudication.get("relevance", ""))


def audit_llm_report(
    path: Path,
    all_paper_rows: dict[tuple[str, str], dict],
    decision_cache: dict[tuple[str, str], dict],
) -> tuple[dict, list[dict]]:
    payload = load_json_object(path)
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    counters: Counter[str] = Counter()
    deltas: list[dict] = []

    for row in rows:
        dataset = llm_row_dataset(row, path, payload)
        doi = llm_row_doi(row)
        if not dataset or not doi:
            counters["missing_dataset_or_doi"] += 1
            continue
        source_row = all_paper_rows.get((dataset, doi), {})
        if not source_row:
            input_row = row.get("input_row", {})
            flat = llm_row_flat(row)
            source_row = {
                "study_doi": doi,
                "study_title": normalize(flat.get("study_title", "") or input_row.get("study_title", "")),
                "abstract": normalize(flat.get("abstract", "") or input_row.get("abstract", "")),
            }
        decision = current_decision(dataset, source_row, decision_cache)
        new_action = norm_action(decision.get("action", ""))
        relevance = llm_relevance(row)
        old_pass = relevance in {"relevant", "uncertain"}
        new_retained = action_is_retained(new_action)
        counters["rows"] += 1
        counters[f"llm_{relevance or 'missing'}"] += 1
        counters[f"new_{new_action}"] += 1
        counters["old_llm_pass"] += int(old_pass)
        counters["old_llm_reject"] += int(relevance == "irrelevant")
        counters["old_llm_pass_new_excluded"] += int(old_pass and not new_retained)
        counters["old_llm_irrelevant_new_retained"] += int(relevance == "irrelevant" and new_retained)
        if (old_pass and not new_retained) or (relevance == "irrelevant" and new_retained):
            deltas.append(
                {
                    "comparison": "old_llm_vs_current_deterministic",
                    "report": str(path.relative_to(ROOT)),
                    "dataset": dataset,
                    "study_doi": doi,
                    "study_title": normalize(source_row.get("study_title", "")),
                    "llm_relevance": relevance,
                    "new_action": new_action,
                    "has_abstract": bool(normalize(source_row.get("abstract", ""))),
                    "matched_terms": matched_terms_string(decision),
                    "new_reason": normalize(decision.get("reason", "")),
                }
            )

    return {"report": str(path.relative_to(ROOT)), **dict(counters)}, deltas


def aggregate_unique_llm(
    paths: Iterable[Path],
    all_paper_rows: dict[tuple[str, str], dict],
    decision_cache: dict[tuple[str, str], dict],
) -> dict:
    by_key: dict[tuple[str, str], set[str]] = {}
    for path in paths:
        payload = load_json_object(path)
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            key = (llm_row_dataset(row, path, payload), llm_row_doi(row))
            if not key[0] or not key[1]:
                continue
            by_key.setdefault(key, set()).add(llm_relevance(row) or "missing")

    counters: Counter[str] = Counter()
    for key, relevances in by_key.items():
        dataset, doi = key
        source_row = all_paper_rows.get(key)
        counters["unique_dataset_dois"] += 1
        counters["any_llm_pass"] += int(bool(relevances & {"relevant", "uncertain"}))
        counters["all_llm_irrelevant"] += int(relevances == {"irrelevant"})
        counters["has_missing_or_failed_llm"] += int("missing" in relevances or "" in relevances)
        if not source_row:
            counters["missing_from_paper_libraries"] += 1
            continue
        decision = current_decision(dataset, source_row, decision_cache)
        retained = action_is_retained(decision.get("action", ""))
        counters["new_retained"] += int(retained)
        counters["new_excluded"] += int(not retained)
        counters["any_llm_pass_new_excluded"] += int(bool(relevances & {"relevant", "uncertain"}) and not retained)
        counters["all_llm_irrelevant_new_retained"] += int(relevances == {"irrelevant"} and retained)
    return dict(counters)


def load_graph_dois() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    claims_path = PROCESSED / "kg" / "claims.parquet"
    if claims_path.exists():
        try:
            import pandas as pd

            claims = pd.read_parquet(claims_path, columns=["dataset", "study_doi"])
            for row in claims.itertuples(index=False):
                key = dataset_key(row.dataset, row.study_doi)
                if key[0] and key[1]:
                    out.add(key)
        except Exception:
            pass

    payloads = {
        "mechanistic": PROCESSED / "graph_payload_mechanistic_primary_with_secondary.json",
        "disorder": PROCESSED / "graph_payload_disorder_primary_with_secondary.json",
    }
    for dataset, path in payloads.items():
        payload = load_json_object(path)
        for contribution in payload.get("contributions", []):
            if not isinstance(contribution, dict):
                continue
            doi = normalize_doi(contribution.get("paper", {}).get("doi", ""))
            if doi:
                out.add((dataset, doi))
    return out


def audit_graph_dois(
    graph_dois: set[tuple[str, str]],
    all_paper_rows: dict[tuple[str, str], dict],
    decision_cache: dict[tuple[str, str], dict],
) -> tuple[dict, list[dict]]:
    global_by_doi: dict[str, dict] = {}
    for (_, doi), row in all_paper_rows.items():
        global_by_doi.setdefault(doi, row)

    counters: Counter[str] = Counter()
    failures: list[dict] = []
    for dataset, doi in sorted(graph_dois):
        row = all_paper_rows.get((dataset, doi)) or global_by_doi.get(doi)
        counters["graph_dataset_dois"] += 1
        if not row:
            counters["missing_from_paper_libraries"] += 1
            failures.append(
                {
                    "comparison": "graph_current_deterministic",
                    "dataset": dataset,
                    "study_doi": doi,
                    "issue": "missing_from_paper_libraries",
                }
            )
            continue
        counters["found_in_paper_libraries"] += 1
        counters["has_abstract"] += int(bool(normalize(row.get("abstract", ""))))
        decision = current_decision(dataset, row, decision_cache)
        action = norm_action(decision.get("action", ""))
        counters[f"new_{action}"] += 1
        if not action_is_retained(action):
            counters["graph_new_excluded"] += 1
            failures.append(
                {
                    "comparison": "graph_current_deterministic",
                    "dataset": dataset,
                    "study_doi": doi,
                    "study_title": normalize(row.get("study_title", "")),
                    "issue": "current_deterministic_excludes_graph_doi",
                    "has_abstract": bool(normalize(row.get("abstract", ""))),
                    "matched_terms": matched_terms_string(decision),
                    "new_reason": normalize(decision.get("reason", "")),
                }
            )
    return dict(counters), failures


def aggregate_unique_old_deterministic(
    rows: list[dict],
    all_paper_rows: dict[tuple[str, str], dict],
    decision_cache: dict[tuple[str, str], dict],
) -> tuple[dict, list[dict]]:
    by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = dataset_key(row.get("dataset", ""), row.get("study_doi", ""))
        if not key[0] or not key[1]:
            continue
        entry = by_key.setdefault(
            key,
            {
                "dataset": key[0],
                "study_doi": key[1],
                "old_reports": set(),
                "old_actions": set(),
            },
        )
        entry["old_reports"].add(row.get("report", ""))
        entry["old_actions"].add(row.get("old_action", ""))

    counters: Counter[str] = Counter()
    deltas: list[dict] = []
    for key, entry in by_key.items():
        dataset, doi = key
        row = all_paper_rows.get(key)
        if not row:
            continue
        decision = current_decision(dataset, row, decision_cache)
        action = norm_action(decision.get("action", ""))
        old_any_retained = any(action_is_retained(action) for action in entry["old_actions"])
        new_retained = action_is_retained(action)
        counters["unique_dataset_dois"] += 1
        counters["old_any_retained"] += int(old_any_retained)
        counters["old_all_excluded"] += int(not old_any_retained)
        counters["new_retained"] += int(new_retained)
        counters["new_excluded"] += int(not new_retained)
        counters["old_any_retained_new_excluded"] += int(old_any_retained and not new_retained)
        counters["old_all_excluded_new_retained"] += int((not old_any_retained) and new_retained)
        if old_any_retained != new_retained:
            deltas.append(
                {
                    "comparison": "unique_old_deterministic_vs_current",
                    "dataset": dataset,
                    "study_doi": doi,
                    "study_title": normalize(row.get("study_title", "")),
                    "old_any_retained": old_any_retained,
                    "old_actions": "|".join(sorted(entry["old_actions"])),
                    "new_action": action,
                    "has_abstract": bool(normalize(row.get("abstract", ""))),
                    "matched_terms": matched_terms_string(decision),
                    "new_reason": normalize(decision.get("reason", "")),
                }
            )
    return dict(counters), deltas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-json",
        type=Path,
        default=PROCESSED / "deterministic_prescreen_shadow_audit.json",
        help="Audit JSON output path.",
    )
    parser.add_argument(
        "--deltas-csv",
        type=Path,
        default=PROCESSED / "deterministic_prescreen_shadow_audit_deltas.csv",
        help="Decision-delta CSV output path.",
    )
    args = parser.parse_args()

    deterministic_paths = sorted(PROCESSED.glob("deterministic_prescreen_report*.json"))
    llm_paths = sorted(PROCESSED.glob("llm_abstract_screening_report*.json"))
    paper_paths = {
        ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        ROOT / "data" / "processed" / "paper_library_disorder.json",
    }
    for det_path in deterministic_paths:
        inputs = load_json_object(det_path).get("inputs", {})
        paper_path = Path(inputs.get("paper_db_json", ""))
        if paper_path.exists():
            paper_paths.add(paper_path)
    all_paper_rows = load_paper_rows(paper_paths)
    decision_cache: dict[tuple[str, str], dict] = {}

    deterministic_summaries: list[dict] = []
    all_deltas: list[dict] = []
    old_unique_rows: list[dict] = []
    for path in deterministic_paths:
        summary, deltas = audit_deterministic_report(path, decision_cache)
        deterministic_summaries.append(summary)
        all_deltas.extend(deltas)
        payload = load_json_object(path)
        dataset = normalize(payload.get("dataset", "")) or ("mechanistic" if "mechanistic" in path.name else "disorder")
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            old_unique_rows.append(
                {
                    "report": str(path.relative_to(ROOT)),
                    "dataset": dataset,
                    "study_doi": normalize_doi(row.get("study_doi", "")),
                    "old_action": norm_action(row.get("deterministic_prescreen_action", "")),
                }
            )
    unique_old_summary, unique_old_deltas = aggregate_unique_old_deterministic(
        old_unique_rows,
        all_paper_rows,
        decision_cache,
    )
    all_deltas.extend(unique_old_deltas)

    llm_summaries: list[dict] = []
    for path in llm_paths:
        summary, deltas = audit_llm_report(path, all_paper_rows, decision_cache)
        llm_summaries.append(summary)
        all_deltas.extend(deltas)
    unique_llm_summary = aggregate_unique_llm(llm_paths, all_paper_rows, decision_cache)

    graph_summary, graph_failures = audit_graph_dois(load_graph_dois(), all_paper_rows, decision_cache)
    all_deltas.extend(graph_failures)

    payload = {
        "deterministic_reports": deterministic_summaries,
        "unique_old_deterministic_dataset_dois": unique_old_summary,
        "llm_reports": llm_summaries,
        "unique_llm_dataset_dois": unique_llm_summary,
        "graph_dois": graph_summary,
        "current_decisions_cached": len(decision_cache),
        "delta_rows_written": len(all_deltas),
        "outputs": {
            "json": str(args.out_json),
            "deltas_csv": str(args.deltas_csv),
        },
    }
    write_json(args.out_json, payload)
    write_csv(args.deltas_csv, all_deltas)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
