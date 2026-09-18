"""Generate author-identity review candidates; name similarity never merges IDs.

When a reviewed baseline is supplied, the audit also isolates identity issues
introduced by the candidate build. Structural regressions can fail the build,
while name/coauthor similarity remains a review queue rather than an automatic
merge rule.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IDENTITY_OVERRIDES = ROOT / "pipeline" / "kg" / "author_identity_overrides.json"


def name_parts(value: str) -> list[str]:
    value = "".join("-" if unicodedata.category(c) == "Pd" else c for c in value)
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", value)


def canonical_name(value: str) -> str:
    return " ".join(name_parts(value))


def _load_tables(kg_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    authors = pd.read_parquet(kg_dir / "authors.parquet").fillna("")
    links = pd.read_parquet(kg_dir / "paper_authors.parquet").fillna("")
    papers = pd.read_parquet(kg_dir / "papers.parquet").fillna("")
    return authors, links, papers


def _collaborator_lookup(links: pd.DataFrame):
    papers_by_author = links.groupby("author_id")["paper_id"].agg(set).to_dict()
    authors_by_paper = links.groupby("paper_id")["author_id"].agg(set).to_dict()
    cache: dict[str, set[str]] = {}

    def collaborators(author_id: str) -> set[str]:
        if author_id not in cache:
            paper_sets = [authors_by_paper[p] for p in papers_by_author.get(author_id, set())]
            cache[author_id] = (set().union(*paper_sets) if paper_sets else set()) - {author_id}
        return cache[author_id]

    return collaborators, papers_by_author


def _same_paper_name_collisions(
    authors: pd.DataFrame, links: pd.DataFrame, papers: pd.DataFrame
) -> list[dict[str, Any]]:
    names_by_id = authors.set_index("author_id")["display_name"].to_dict()
    work = links.copy()
    work["audit_canonical_name"] = work["author_id"].map(
        lambda author_id: canonical_name(names_by_id.get(author_id, ""))
    )
    titles = papers.set_index("paper_id")["title"].to_dict() if "title" in papers else {}
    rows: list[dict[str, Any]] = []
    for (paper_id, name), group in work.groupby(["paper_id", "audit_canonical_name"]):
        author_ids = sorted(set(group["author_id"]))
        if not name or len(author_ids) < 2:
            continue
        rows.append(
            {
                "paper_id": paper_id,
                "doi": next((str(value) for value in group.get("doi", []) if str(value)), ""),
                "title": titles.get(paper_id, ""),
                "canonical_name": name,
                "author_ids": author_ids,
                "author_positions": sorted(int(value) for value in group["author_position"]),
                "display_names": sorted(set(group["display_name"])),
            }
        )
    return sorted(rows, key=lambda row: (row["paper_id"], row["canonical_name"]))


def _new_exact_name_candidates(
    authors: pd.DataFrame,
    links: pd.DataFrame,
    baseline_authors: pd.DataFrame,
    baseline_links: pd.DataFrame,
    same_paper_collisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_ids = set(baseline_authors["author_id"])
    new_paper_ids = set(links["paper_id"]) - set(baseline_links["paper_id"])
    ids_on_new_papers = set(links.loc[links["paper_id"].isin(new_paper_ids), "author_id"])
    new_ids = (set(authors["author_id"]) - baseline_ids) & ids_on_new_papers
    collaborators, papers_by_author = _collaborator_lookup(links)
    same_paper_names = {row["canonical_name"] for row in same_paper_collisions}
    rows: list[dict[str, Any]] = []
    grouped = defaultdict(list)
    for row in authors.to_dict("records"):
        name = canonical_name(row.get("display_name", ""))
        if name:
            grouped[name].append(row)

    for name, members in grouped.items():
        ids = {row["author_id"] for row in members}
        introduced = ids & new_ids
        if len(ids) < 2 or not introduced:
            continue
        shared = 0
        shared_pairs: list[dict[str, Any]] = []
        for left_id in sorted(introduced):
            for right_id in sorted(ids - {left_id}):
                overlap = len((collaborators(left_id) & collaborators(right_id)) - ids)
                if overlap:
                    shared_pairs.append(
                        {
                            "left_author_id": left_id,
                            "right_author_id": right_id,
                            "shared_coauthors": overlap,
                        }
                    )
                    shared = max(shared, overlap)
        priority_reasons = []
        if name in same_paper_names:
            priority_reasons.append("same_name_on_same_paper")
        if shared >= 2:
            priority_reasons.append("at_least_two_shared_coauthors")
        rows.append(
            {
                "canonical_name": name,
                "names": sorted({str(row["display_name"]) for row in members}),
                "author_ids": sorted(ids),
                "new_author_ids": sorted(introduced),
                "orcids": sorted({str(row["orcid"]) for row in members if row.get("orcid")}),
                "paper_count": len(
                    set().union(*(papers_by_author.get(author_id, set()) for author_id in ids))
                ),
                "max_shared_coauthors": shared,
                "shared_coauthor_pairs": shared_pairs,
                "priority": bool(priority_reasons),
                "priority_reasons": priority_reasons,
                "status": "needs_identity_review",
                "identities": [
                    {
                        key: row.get(key, "")
                        for key in (
                            "author_id",
                            "display_name",
                            "orcid",
                            "paper_count",
                            "identity_confidence",
                        )
                    }
                    for row in members
                ],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["priority"]),
            -row["max_shared_coauthors"],
            row["canonical_name"],
        ),
    )


def _frame_issue_keys(frame: pd.DataFrame, columns: list[str]) -> set[tuple[str, ...]]:
    if frame.empty:
        return set()
    return {
        tuple(str(value) for value in row)
        for row in frame[columns].itertuples(index=False, name=None)
    }


def audit(
    kg_dir: Path,
    out_dir: Path,
    baseline_dir: Path | None = None,
    fail_on_new_integrity_errors: bool = False,
    identity_overrides: Path | None = DEFAULT_IDENTITY_OVERRIDES,
) -> dict:
    authors, links, papers = _load_tables(kg_dir)
    groups = defaultdict(list)
    for row in authors.to_dict("records"):
        parts = name_parts(row["display_name"])
        if len(parts) >= 2 and len(parts[0]) > 2:
            groups[(parts[0], parts[-1])].append(row)
    collaborators, papers_by_author = _collaborator_lookup(links)
    rows = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        ids = {member["author_id"] for member in members}
        orcids = sorted({member["orcid"] for member in members if member["orcid"]})
        shared = 0
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                shared = max(
                    shared,
                    len(
                        (collaborators(left["author_id"]) & collaborators(right["author_id"]))
                        - ids
                    ),
                )
        rows.append(
            {
                "name_key": " ".join(key),
                "identity_count": len(ids),
                "paper_count": len(
                    set().union(*(papers_by_author.get(author_id, set()) for author_id in ids))
                ),
                "names": sorted({member["display_name"] for member in members}),
                "author_ids": sorted(ids),
                "orcids": orcids,
                "max_shared_coauthors": shared,
                "status": (
                    "identifier_conflict_review" if len(orcids) > 1 else "name_similarity_review"
                ),
                "identities": [
                    {
                        field: member[field]
                        for field in (
                            "author_id",
                            "display_name",
                            "orcid",
                            "paper_count",
                            "identity_confidence",
                        )
                    }
                    for member in members
                ],
            }
        )
    rows.sort(key=lambda row: (-row["paper_count"], row["name_key"]))

    duplicate_positions = links[links.duplicated(["paper_id", "author_position"], keep=False)]
    duplicate_identities = links[links.duplicated(["paper_id", "author_id"], keep=False)]
    name_counts = duplicate_identities.groupby(["paper_id", "author_id"])["display_name"].transform(
        "nunique"
    )
    differing_names = duplicate_identities[name_counts.gt(1)]
    conflicts = links[links.identity_confidence.eq("openalex_author_id_orcid_conflict")]
    orphan_links = links[
        ~links.paper_id.isin(papers.paper_id) | ~links.author_id.isin(authors.author_id)
    ]
    same_paper_collisions = _same_paper_name_collisions(authors, links, papers)

    new_candidates: list[dict[str, Any]] = []
    new_same_paper_collisions: list[dict[str, Any]] = []
    new_duplicate_position_rows = 0
    new_repeated_identity_groups = 0
    new_repeated_identity_groups_with_different_names = 0
    new_orphan_rows = 0
    new_paper_count = 0
    new_authorship_rows = 0
    if baseline_dir is not None:
        baseline_authors, baseline_links, baseline_papers = _load_tables(baseline_dir)
        new_paper_ids = set(links["paper_id"]) - set(baseline_links["paper_id"])
        new_paper_count = len(new_paper_ids)
        new_authorship_rows = int(links["paper_id"].isin(new_paper_ids).sum())
        baseline_same_paper = _same_paper_name_collisions(
            baseline_authors, baseline_links, baseline_papers
        )
        baseline_same_keys = {
            (row["paper_id"], row["canonical_name"], tuple(row["author_ids"]))
            for row in baseline_same_paper
        }
        new_same_paper_collisions = [
            row
            for row in same_paper_collisions
            if (row["paper_id"], row["canonical_name"], tuple(row["author_ids"]))
            not in baseline_same_keys
        ]
        new_candidates = _new_exact_name_candidates(
            authors, links, baseline_authors, baseline_links, new_same_paper_collisions
        )

        baseline_duplicate_positions = baseline_links[
            baseline_links.duplicated(["paper_id", "author_position"], keep=False)
        ]
        baseline_duplicate_identities = baseline_links[
            baseline_links.duplicated(["paper_id", "author_id"], keep=False)
        ]
        baseline_name_counts = baseline_duplicate_identities.groupby(
            ["paper_id", "author_id"]
        )["display_name"].transform("nunique")
        baseline_differing_names = baseline_duplicate_identities[
            baseline_name_counts.gt(1)
        ]
        baseline_orphans = baseline_links[
            ~baseline_links.paper_id.isin(baseline_papers.paper_id)
            | ~baseline_links.author_id.isin(baseline_authors.author_id)
        ]
        new_duplicate_position_rows = len(
            _frame_issue_keys(duplicate_positions, ["paper_id", "author_position", "author_id"])
            - _frame_issue_keys(
                baseline_duplicate_positions, ["paper_id", "author_position", "author_id"]
            )
        )
        # Compare repeated-author groups, rather than individual positions. A
        # baseline group can gain or lose a source position when a provider
        # refreshes its byline without becoming a newly introduced problem.
        new_repeated_identity_groups = len(
            _frame_issue_keys(duplicate_identities, ["paper_id", "author_id"])
            - _frame_issue_keys(baseline_duplicate_identities, ["paper_id", "author_id"])
        )
        new_repeated_identity_groups_with_different_names = len(
            _frame_issue_keys(differing_names, ["paper_id", "author_id"])
            - _frame_issue_keys(baseline_differing_names, ["paper_id", "author_id"])
        )
        new_orphan_rows = len(
            _frame_issue_keys(orphan_links, ["paper_id", "author_id"])
            - _frame_issue_keys(baseline_orphans, ["paper_id", "author_id"])
        )

    reviewed_distinct: list[dict[str, Any]] = []
    reviewed_keys: set[tuple[str, tuple[str, ...]]] = set()
    if identity_overrides and identity_overrides.is_file():
        payload = json.loads(identity_overrides.read_text())
        records = payload.get("distinct_identity_reviews", [])
        if not isinstance(records, list):
            raise ValueError("distinct_identity_reviews must be an array")
        seen_review_ids: set[str] = set()
        for index, record in enumerate(records, start=1):
            required = {
                "review_id", "canonical_name", "identity_ids", "decision",
                "reason", "sources", "reviewed_at", "reviewed_by",
            }
            if not isinstance(record, dict) or not required.issubset(record):
                raise ValueError(f"Distinct identity review {index} lacks review provenance")
            review_id = str(record["review_id"]).strip()
            identity_ids = record["identity_ids"]
            if (
                not review_id
                or review_id in seen_review_ids
                or record["decision"] != "different_people"
                or not isinstance(identity_ids, list)
                or len(set(identity_ids)) < 2
                or not record["reason"]
                or not isinstance(record["sources"], list)
                or not record["sources"]
            ):
                raise ValueError(f"Invalid distinct identity review {index}")
            seen_review_ids.add(review_id)
            reviewed_keys.add(
                (canonical_name(str(record["canonical_name"])), tuple(sorted(set(identity_ids))))
            )

    unresolved_candidates: list[dict[str, Any]] = []
    for row in new_candidates:
        key = (row["canonical_name"], tuple(sorted(row["author_ids"])))
        if key in reviewed_keys:
            reviewed_distinct.append({**row, "status": "reviewed_different_people"})
        else:
            unresolved_candidates.append(row)
    new_candidates = unresolved_candidates
    priority_candidates = [row for row in new_candidates if row["priority"]]
    report = {
        "schema_version": "author_identity_audit_v2",
        "kg_dir": str(kg_dir.resolve()),
        "baseline_dir": str(baseline_dir.resolve()) if baseline_dir else "",
        "author_identities": len(authors),
        "authorship_rows": len(links),
        "candidate_name_groups": len(rows),
        "candidate_identities": sum(row["identity_count"] for row in rows),
        "groups_with_multiple_orcids": sum(len(row["orcids"]) > 1 for row in rows),
        "orcid_conflict_profiles": int(conflicts.openalex_author_id.nunique()),
        "orcid_conflict_authorship_rows": len(conflicts),
        "repeated_author_on_same_paper_rows": len(duplicate_identities),
        "papers_with_repeated_authors": int(duplicate_identities.paper_id.nunique()),
        "repeated_identity_groups_with_different_names": int(
            len(differing_names[["paper_id", "author_id"]].drop_duplicates())
        ),
        "same_paper_same_name_identity_groups": len(same_paper_collisions),
        "duplicate_position_rows": len(duplicate_positions),
        "orphan_authorship_rows": len(orphan_links),
        "new_exact_name_collision_groups": len(new_candidates),
        "new_priority_identity_review_groups": len(priority_candidates),
        "reviewed_distinct_name_groups": len(reviewed_distinct),
        "new_papers_compared_with_baseline": new_paper_count,
        "authorship_rows_on_new_papers": new_authorship_rows,
        "new_same_paper_same_name_identity_groups": len(new_same_paper_collisions),
        "new_duplicate_position_rows": new_duplicate_position_rows,
        "new_repeated_identity_groups": new_repeated_identity_groups,
        "new_repeated_identity_groups_with_different_names": (
            new_repeated_identity_groups_with_different_names
        ),
        "new_orphan_authorship_rows": new_orphan_rows,
        "limitations": (
            "Candidate groups are not verified duplicates. Common names, different middle "
            "names, and multiple ORCIDs require source review. Shared coauthors only "
            "prioritize review. Initial-only names and reordered surnames are not "
            "exhaustively matched."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (out_dir / "name_candidates.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "new_name_candidates.json").write_text(
        json.dumps(new_candidates, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "new_priority_name_candidates.json").write_text(
        json.dumps(priority_candidates, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "reviewed_distinct_name_groups.json").write_text(
        json.dumps(reviewed_distinct, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "same_paper_name_collisions.json").write_text(
        json.dumps(same_paper_collisions, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "new_same_paper_name_collisions.json").write_text(
        json.dumps(new_same_paper_collisions, indent=2, ensure_ascii=False) + "\n"
    )
    for name, frame in [
        ("repeated_authors", duplicate_identities),
        ("possible_false_merges", differing_names),
        ("duplicate_positions", duplicate_positions),
        ("orcid_conflicts", conflicts),
    ]:
        frame.to_csv(out_dir / f"{name}.csv", index=False)

    # A publication can intentionally repeat a person in its supplied byline
    # (for example, once per panel role). Keep those groups in the review
    # artifacts, but only fail when one identity is attached to different names,
    # a position is duplicated, or an authorship is orphaned.
    integrity_errors = (
        new_duplicate_position_rows
        + new_repeated_identity_groups_with_different_names
        + new_orphan_rows
    )
    if fail_on_new_integrity_errors and integrity_errors:
        raise ValueError(
            "Author identity audit found new structural errors: "
            f"duplicate_positions={new_duplicate_position_rows}, "
            "repeated_identities_with_different_names="
            f"{new_repeated_identity_groups_with_different_names}, "
            f"orphans={new_orphan_rows}. Review {out_dir}."
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--fail-on-new-integrity-errors", action="store_true")
    parser.add_argument("--identity-overrides", type=Path, default=DEFAULT_IDENTITY_OVERRIDES)
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                args.kg_dir,
                args.out_dir,
                baseline_dir=args.baseline_dir,
                fail_on_new_integrity_errors=args.fail_on_new_integrity_errors,
                identity_overrides=args.identity_overrides,
            ),
            indent=2,
        )
    )
