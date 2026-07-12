#!/usr/bin/env python3
"""Compare isolated review relationships with the 50-paper manual gold set.

Lexical matching is only a reproducible triage aid. Final improvement judgments
remain manual because proposition fidelity and paper-level centrality cannot be
established safely from token overlap alone.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
import re
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = ROOT / "data" / "processed" / "evaluation" / "review_paper_complete_50_20260711"
DEFAULT_GOLD = EVAL_ROOT / "results" / "manual_gold_relationships.csv"
DEFAULT_BASELINE = EVAL_ROOT / "results" / "manual_paper_assessment.csv"
DEFAULT_BUNDLES = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "review_relationship_runs"
    / "review_relationships_v2_eval50"
    / "paper_relationship_bundles.jsonl"
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "including",
    "into", "is", "it", "may", "of", "on", "or", "reviewed", "that", "the", "their", "through", "to", "with",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def tokens(value: object) -> set[str]:
    text = normalize(value).casefold().replace("5-ht", "serotonin ")
    raw = re.findall(r"[a-z0-9]+", text)
    return {token for token in raw if token not in STOPWORDS and len(token) > 1}


def token_f1(left: object, right: object) -> float:
    a = tokens(left)
    b = tokens(right)
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    return 2.0 * overlap / (len(a) + len(b))


def gold_text(row: dict) -> str:
    return " ".join(normalize(row.get(field, "")) for field in ("subject", "relation", "object", "manual_summary"))


def predicted_text(item: dict) -> str:
    anchors = " ".join(normalize(anchor.get("label", "")) for anchor in item.get("anchors", []) if isinstance(anchor, dict))
    return " ".join([anchors, normalize(item.get("relation_phrase", "")), normalize(item.get("relationship_statement", ""))])


def predicted_by_doi(bundle_rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in bundle_rows:
        if normalize(row.get("status", "")) != "ok":
            continue
        doi = normalize(row.get("study_doi", "")).lower()
        result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
        relationships = [
            item
            for item in result.get("relationships", [])
            if isinstance(item, dict) and normalize(item.get("paper_prominence", "")) in {"paper_defining", "major_supporting"}
        ]
        out[doi] = relationships
    return out


def compare(
    gold_rows: list[dict],
    baseline_rows: list[dict],
    bundle_rows: list[dict],
    *,
    lexical_threshold: float,
) -> tuple[list[dict], list[dict], dict]:
    predicted = predicted_by_doi(bundle_rows)
    matches: list[dict] = []
    gold_by_doi: dict[str, list[dict]] = {}
    for row in gold_rows:
        gold_by_doi.setdefault(normalize(row.get("doi", "")).lower(), []).append(row)

    matched_gold = 0
    for doi, gold_items in gold_by_doi.items():
        candidates = predicted.get(doi, [])
        for gold in gold_items:
            scored = sorted(
                ((token_f1(gold_text(gold), predicted_text(item)), item) for item in candidates),
                key=lambda pair: pair[0],
                reverse=True,
            )
            score, best = scored[0] if scored else (0.0, {})
            is_candidate_match = score >= lexical_threshold
            matched_gold += int(is_candidate_match)
            matches.append(
                {
                    "doi": doi,
                    "gold_relationship_id": normalize(gold.get("relationship_id", "")),
                    "gold_prominence": normalize(gold.get("prominence", "")),
                    "gold_text": gold_text(gold),
                    "gold_graph_form": normalize(gold.get("graph_form", "")),
                    "best_predicted_id": normalize(best.get("item_id", "")),
                    "best_predicted_text": predicted_text(best),
                    "best_predicted_prominence": normalize(best.get("paper_prominence", "")),
                    "best_predicted_graph_form": normalize(best.get("graph_form", "")),
                    "lexical_score": round(score, 4),
                    "lexical_candidate_match": is_candidate_match,
                    "manual_match": "",
                    "manual_notes": "",
                }
            )

    baseline_by_doi = {normalize(row.get("doi", "")).lower(): row for row in baseline_rows}
    paper_rows: list[dict] = []
    for doi in sorted(gold_by_doi):
        items = predicted.get(doi, [])
        doi_matches = [row for row in matches if row["doi"] == doi]
        paper_rows.append(
            {
                "doi": doi,
                "source_depth": normalize(baseline_by_doi.get(doi, {}).get("source_depth", "")),
                "baseline_graph_capture": normalize(baseline_by_doi.get(doi, {}).get("graph_capture", "")),
                "gold_relationship_count": len(gold_by_doi[doi]),
                "new_central_relationship_count": len(items),
                "lexical_candidate_recall": round(
                    sum(bool(row["lexical_candidate_match"]) for row in doi_matches) / len(doi_matches), 4
                ) if doi_matches else 0.0,
                "new_manual_capture": "",
                "new_manual_precision": "",
                "normalization_fidelity": "",
                "manual_notes": "",
            }
        )

    predicted_central = [item for items in predicted.values() for item in items]
    gold_forms = Counter(normalize(row.get("graph_form", "")) for row in gold_rows)
    predicted_forms = Counter(normalize(item.get("graph_form", "")) for item in predicted_central)
    report = {
        "schema_version": "review_relationship_gold_comparison_v2",
        "generated_at_utc": now_utc(),
        "lexical_screen_is_not_final_evaluation": True,
        "lexical_threshold": lexical_threshold,
        "counts": {
            "gold_relationships": len(gold_rows),
            "predicted_central_relationships": len(predicted_central),
            "gold_lexical_candidate_matches": matched_gold,
            "papers_in_gold": len(gold_by_doi),
            "papers_with_new_central_relationships": sum(bool(predicted.get(doi)) for doi in gold_by_doi),
        },
        "baseline_graph_capture": dict(Counter(normalize(row.get("graph_capture", "")) for row in baseline_rows)),
        "gold_by_graph_form": dict(gold_forms),
        "predicted_by_graph_form": dict(predicted_forms),
    }
    return matches, paper_rows, report


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-csv", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--baseline-csv", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--bundles-jsonl", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--lexical-threshold", type=float, default=0.3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gold_rows = pd.read_csv(args.gold_csv).fillna("").to_dict("records")
    baseline_rows = pd.read_csv(args.baseline_csv).fillna("").to_dict("records")
    bundle_rows = read_jsonl(args.bundles_jsonl)
    matches, papers, report = compare(
        gold_rows,
        baseline_rows,
        bundle_rows,
        lexical_threshold=args.lexical_threshold,
    )
    out_dir = args.out_dir or args.bundles_jsonl.parent / "evaluation"
    matches_path = out_dir / "gold_match_candidates.csv"
    papers_path = out_dir / "manual_comparison.csv"
    report_path = out_dir / "comparison_report.json"
    write_csv(matches_path, matches)
    write_csv(papers_path, papers)
    report["outputs"] = {
        "gold_match_candidates_csv": str(matches_path.resolve()),
        "manual_comparison_csv": str(papers_path.resolve()),
        "report_json": str(report_path.resolve()),
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
