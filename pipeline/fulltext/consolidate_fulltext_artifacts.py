#!/usr/bin/env python3
"""Consolidate full-text artifacts into the canonical article-level store."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

try:
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi, now_utc
    from pipeline.fulltext.source_identity import identity_is_verified
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi, now_utc
    from pipeline.fulltext.source_identity import identity_is_verified


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_TARGET_DIR = DEFAULT_FULLTEXT_DIR / "articles"
DEFAULT_REPORT = DEFAULT_FULLTEXT_DIR / "fulltext_artifact_consolidation_report.json"
DEFAULT_SOURCE_DIRS = ("disorder", "mechanistic", "pmc_xml", "europepmc_xml")


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def artifact_doi(path: Path, artifact: dict) -> str:
    doi = normalize_doi(artifact.get("study_doi", ""))
    if doi:
        return doi
    return normalize_doi(path.stem.replace("_", "/"))


def artifact_char_count(artifact: dict) -> int:
    try:
        return int(artifact.get("best_char_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def artifact_section_count(artifact: dict) -> int:
    try:
        return int(artifact.get("best_section_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def artifact_is_ready(artifact: dict) -> bool:
    return bool(clean(artifact.get("best_backend", ""))) and artifact_char_count(artifact) > 0


def artifact_identity_rank(artifact: dict) -> int:
    identity = artifact.get("source_identity")
    if isinstance(identity, dict) and clean(identity.get("status", "")):
        return 2 if identity_is_verified(identity) else 0
    # Missing identity evidence is not a weaker success.  Legacy artifacts must
    # be audited/migrated explicitly; they cannot silently repopulate the
    # canonical store on a future consolidation run.
    return 0


def source_priority(source_dir: str) -> int:
    # Prefer parsed article XML when comparable, then legacy PDF-derived artifacts.
    return {
        "pmc_xml": 0,
        "europepmc_xml": 0,
        "disorder": 1,
        "mechanistic": 1,
    }.get(source_dir, 5)


def artifact_rank(candidate: dict) -> tuple[int, int, int, int, int]:
    artifact = candidate["artifact"]
    return (
        artifact_identity_rank(artifact),
        1 if artifact_is_ready(artifact) else 0,
        artifact_char_count(artifact),
        artifact_section_count(artifact),
        -source_priority(candidate["source_dir"]),
    )


def canonicalize_artifact(artifact: dict, source_path: Path, source_dir: str, generated_at: str) -> dict:
    out = dict(artifact)
    legacy_dataset = clean(out.get("dataset", ""))
    out["dataset"] = "articles"
    out["fulltext_artifact_layout"] = "canonical_articles_v1"
    out["canonicalized_at_utc"] = generated_at
    out["source_artifact_path"] = str(source_path)
    out["source_artifact_dataset"] = legacy_dataset or source_dir
    return out


def iter_source_artifacts(fulltext_dir: Path, source_dirs: list[str]) -> list[dict]:
    candidates: list[dict] = []
    for source_dir in source_dirs:
        root = fulltext_dir / source_dir
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            artifact = load_json(path)
            doi = artifact_doi(path, artifact)
            if not doi:
                continue
            candidates.append(
                {
                    "doi": doi,
                    "source_dir": source_dir,
                    "source_path": path,
                    "artifact": artifact,
                    "ready": artifact_is_ready(artifact),
                    "best_backend": clean(artifact.get("best_backend", "")),
                    "best_char_count": artifact_char_count(artifact),
                    "best_section_count": artifact_section_count(artifact),
                }
            )
    return candidates


def consolidate_fulltext_artifacts(
    *,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    target_dir: Path = DEFAULT_TARGET_DIR,
    source_dirs: list[str] | None = None,
    report_path: Path = DEFAULT_REPORT,
    overwrite: bool = False,
    limit: int = 0,
) -> dict:
    generated_at = now_utc()
    source_dirs = source_dirs or list(DEFAULT_SOURCE_DIRS)
    candidates = iter_source_artifacts(fulltext_dir, source_dirs)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["doi"]].append(candidate)

    records: list[dict] = []
    counts: Counter[str] = Counter()
    selected_dois = sorted(grouped)
    if limit > 0:
        selected_dois = selected_dois[:limit]

    target_dir.mkdir(parents=True, exist_ok=True)
    for doi in selected_dois:
        doi_candidates = grouped[doi]
        best = max(doi_candidates, key=artifact_rank)
        target_path = target_dir / f"{doi_to_slug(doi)}.json"
        action = "skipped_existing"
        existing_target = load_json(target_path) if target_path.exists() else {}
        existing_doi = artifact_doi(target_path, existing_target) if existing_target else ""
        if existing_doi and existing_doi != doi:
            # Slug-only filenames can collide for punctuation variants. Never
            # overwrite one DOI's artifact with another record.
            action = "skipped_target_doi_collision"
        elif artifact_identity_rank(best["artifact"]) == 0:
            action = "skipped_identity_unverified"
        elif overwrite or not target_path.exists():
            artifact = canonicalize_artifact(
                best["artifact"],
                source_path=best["source_path"],
                source_dir=best["source_dir"],
                generated_at=generated_at,
            )
            write_json(target_path, artifact)
            action = "written" if not target_path.exists() else "overwritten" if overwrite else "written"
        counts[action] += 1
        if len(doi_candidates) > 1:
            counts["doi_with_duplicate_sources"] += 1
        if best["ready"]:
            counts["selected_ready"] += 1
        else:
            counts["selected_not_ready"] += 1
        records.append(
            {
                "doi": doi,
                "target_path": str(target_path),
                "action": action,
                "selected_source_dir": best["source_dir"],
                "selected_source_path": str(best["source_path"]),
                "selected_best_backend": best["best_backend"],
                "selected_best_char_count": best["best_char_count"],
                "selected_best_section_count": best["best_section_count"],
                "source_count": len(doi_candidates),
                "source_dirs": "|".join(sorted({candidate["source_dir"] for candidate in doi_candidates})),
            }
        )

    report = {
        "generated_at_utc": generated_at,
        "fulltext_dir": str(fulltext_dir.resolve()),
        "target_dir": str(target_dir.resolve()),
        "source_dirs": source_dirs,
        "overwrite": overwrite,
        "limit": limit,
        "counts": {
            "source_artifacts": len(candidates),
            "unique_dois": len(grouped),
            "selected_dois": len(selected_dois),
            **dict(counts),
        },
        "records": records,
    }
    write_json(report_path, report)
    print(
        "FULLTEXT_CONSOLIDATION: "
        f"selected={len(selected_dois):,} "
        f"written={counts.get('written', 0) + counts.get('overwritten', 0):,} "
        f"skipped_existing={counts.get('skipped_existing', 0):,} "
        f"target={target_dir}",
        flush=True,
    )
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--target-dir", default=str(DEFAULT_TARGET_DIR))
    parser.add_argument("--source-dirs", default=",".join(DEFAULT_SOURCE_DIRS))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    source_dirs = [part.strip() for part in args.source_dirs.split(",") if part.strip()]
    consolidate_fulltext_artifacts(
        fulltext_dir=Path(args.fulltext_dir).resolve(),
        target_dir=Path(args.target_dir).resolve(),
        source_dirs=source_dirs,
        report_path=Path(args.report).resolve(),
        overwrite=bool(args.overwrite),
        limit=max(0, args.limit),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
