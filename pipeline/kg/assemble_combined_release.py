#!/usr/bin/env python3
"""Assemble an append/update evidence release from a canonical base and overlays.

Each overlay replaces the complete evidence contribution for every DOI it
contains. Current candidate eligibility is applied after DOI-alias resolution,
so stale downstream evidence for newly excluded papers cannot re-enter a build.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.extract.route_extraction_profiles import is_legacy_v1_secondary_profile
from pipeline.ingest.metadata_utils import normalize_doi


CANONICAL_PAPER_METADATA_FIELDS = (
    "pmid",
    "pmcid",
    "openalex_id",
    "study_title",
    "study_year",
    "authors",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "language",
    "mesh_terms",
    "keywords",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_list(path: Path) -> list[dict]:
    payload = read_json(path)
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError(f"Expected a JSON list of objects: {path}")
    return payload


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            rows.append(row)
    return rows


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_aliases(path: Path) -> dict[str, str]:
    payload = read_json(path)
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        raise ValueError("DOI alias registry must contain a records list")
    return {
        normalize_doi(row.get("alias_doi", "")).lower(): normalize_doi(
            row.get("canonical_doi", "")
        ).lower()
        for row in records
        if isinstance(row, dict)
        and normalize_doi(row.get("alias_doi", ""))
        and normalize_doi(row.get("canonical_doi", ""))
    }


def resolve_doi(value: object, aliases: dict[str, str]) -> str:
    doi = normalize_doi(value).lower()
    seen: set[str] = set()
    while doi in aliases and doi not in seen:
        seen.add(doi)
        doi = aliases[doi]
    if doi in seen:
        raise ValueError(f"Cyclic DOI alias registry entry involving {doi}")
    return doi


def evidence_doi(row: dict) -> str:
    return normalize_doi(row.get("study_doi") or row.get("doi") or "").lower()


def output_doi(row: dict) -> str:
    result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
    return normalize_doi(row.get("study_doi") or row.get("doi") or result.get("study_doi") or "").lower()


def canonicalize_evidence_row(row: dict, aliases: dict[str, str]) -> tuple[dict, bool]:
    original = evidence_doi(row)
    if not original:
        raise ValueError("Evidence row has no DOI")
    canonical = resolve_doi(original, aliases)
    out = dict(row)
    out["study_doi"] = canonical
    if canonical != original:
        out["study_doi_alias"] = original
    return out, canonical != original


def canonicalize_output_row(row: dict, aliases: dict[str, str]) -> tuple[dict, bool]:
    original = output_doi(row)
    if not original:
        raise ValueError("Extraction output row has no DOI")
    canonical = resolve_doi(original, aliases)
    out = dict(row)
    if "study_doi" in out:
        out["study_doi"] = canonical
    result = out.get("result")
    if isinstance(result, dict):
        result = dict(result)
        result["study_doi"] = canonical
        out["result"] = result
    if canonical != original:
        out["study_doi_alias"] = original
    return out, canonical != original


def eligible_dois(candidate_table: Path, field: str, aliases: dict[str, str]) -> set[str]:
    frame = pd.read_parquet(candidate_table, columns=["doi", field])
    selected = frame[field].fillna(False).astype(bool)
    return {
        resolve_doi(value, aliases)
        for value in frame.loc[selected, "doi"]
        if normalize_doi(value)
    }


def candidate_metadata(candidate_table: Path, aliases: dict[str, str]) -> dict[str, dict]:
    """Load one authoritative metadata record per canonical candidate DOI."""

    frame = pd.read_parquet(candidate_table)
    available = [field for field in CANONICAL_PAPER_METADATA_FIELDS if field in frame.columns]
    by_doi: dict[str, tuple[bool, dict]] = {}
    for record in frame[["doi", *available]].to_dict(orient="records"):
        original = normalize_doi(record.pop("doi", "")).lower()
        if not original:
            continue
        canonical = resolve_doi(original, aliases)
        is_canonical_record = original == canonical
        current = by_doi.get(canonical)
        if current is not None and (current[0] or not is_canonical_record):
            continue
        cleaned: dict[str, object] = {}
        for field, value in record.items():
            if isinstance(value, float) and pd.isna(value):
                continue
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            cleaned[field] = value
        by_doi[canonical] = (is_canonical_record, cleaned)
    return {doi: metadata for doi, (_canonical, metadata) in by_doi.items()}


def apply_candidate_metadata(
    rows: list[dict],
    metadata_by_doi: dict[str, dict],
) -> tuple[list[dict], dict]:
    """Replace stale extraction metadata with the canonical candidate record."""

    out: list[dict] = []
    papers_updated: set[str] = set()
    fields_updated = 0
    blank_fields_filled = 0
    for row in rows:
        updated = dict(row)
        doi = evidence_doi(updated)
        metadata = metadata_by_doi.get(doi, {})
        for field, value in metadata.items():
            previous = updated.get(field)
            if previous == value:
                continue
            if not clean(previous):
                blank_fields_filled += 1
            updated[field] = value
            fields_updated += 1
            papers_updated.add(doi)
        out.append(updated)
    return out, {
        "papers_updated_from_candidate_metadata": len(papers_updated),
        "row_fields_updated_from_candidate_metadata": fields_updated,
        "blank_row_fields_filled_from_candidate_metadata": blank_fields_filled,
    }


def exact_deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        digest = hashlib.sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        out.append(row)
    return out, len(rows) - len(out)


def remove_legacy_v1_secondary_outputs(rows: list[dict]) -> tuple[list[dict], dict]:
    """Remove obsolete V1 review/meta audit outputs from a combined release.

    These rows are not current evidence contracts. Review evidence is supplied
    by the paper-centered relationship pipeline, while meta-analysis evidence
    is supplied by the V2 meta-analysis pipeline. Keeping the obsolete output
    records makes an otherwise current release appear to depend on disabled
    extraction contracts and can accidentally revive those contracts later.
    """

    kept: list[dict] = []
    removed: Counter = Counter()
    removed_papers: set[str] = set()
    for row in rows:
        contract = (
            row.get("extraction_contract", {})
            if isinstance(row.get("extraction_contract"), dict)
            else {}
        )
        prompt_profile = clean(row.get("prompt_profile") or contract.get("prompt_profile"))
        schema_profile = clean(row.get("schema_profile") or contract.get("schema_profile"))
        if is_legacy_v1_secondary_profile(prompt_profile, schema_profile):
            removed[f"{prompt_profile}/{schema_profile}"] += 1
            doi = output_doi(row)
            if doi:
                removed_papers.add(doi)
            continue
        kept.append(row)
    return kept, {
        "legacy_v1_secondary_rows_removed": sum(removed.values()),
        "legacy_v1_secondary_papers_removed": len(removed_papers),
        "legacy_v1_secondary_contract_counts": dict(sorted(removed.items())),
    }


def reject_non_v2_meta_analysis_evidence(rows: list[dict]) -> None:
    """Fail closed if any meta-analysis evidence is not from the V2 converter."""

    incompatible = [
        row
        for row in rows
        if clean(row.get("source_type")) == "meta_analysis"
        and clean(row.get("route_output_schema_version"))
        != "meta_analysis_v2_evidence_rows_v1"
    ]
    if not incompatible:
        return
    papers = sorted({evidence_doi(row) for row in incompatible if evidence_doi(row)})
    sample = ", ".join(papers[:10])
    raise ValueError(
        "Combined release contains non-V2 meta-analysis evidence: "
        f"{len(incompatible)} row(s) across {len(papers)} paper(s)"
        + (f" ({sample})" if sample else "")
        + ". Replace each paper's complete contribution with "
        "meta_analysis_v2_evidence_rows_v1 before release."
    )


def canonicalize_layer_rows(
    rows: list[dict],
    *,
    aliases: dict[str, str],
    canonicalizer,
    doi_getter,
    layer_label: str,
) -> tuple[list[dict], int, int, int]:
    """Canonicalize a layer and prefer the registered DOI over its aliases.

    A single extraction layer can contain both an old publisher DOI and its
    registered canonical DOI.  Concatenating both after alias resolution would
    duplicate one paper's evidence.  When the canonical DOI is present, retain
    only its rows.  Multiple aliases without the canonical record are
    ambiguous and therefore fail closed instead of silently choosing one.
    """

    staged: list[tuple[dict, str, str, bool]] = []
    originals_by_canonical: dict[str, set[str]] = {}
    for row in rows:
        original = doi_getter(row)
        normalized, changed = canonicalizer(row, aliases)
        canonical = doi_getter(normalized)
        staged.append((normalized, original, canonical, changed))
        originals_by_canonical.setdefault(canonical, set()).add(original)

    preferred_origin: dict[str, str] = {}
    collision_papers = 0
    for canonical, originals in originals_by_canonical.items():
        if len(originals) == 1:
            preferred_origin[canonical] = next(iter(originals))
            continue
        collision_papers += 1
        if canonical not in originals:
            raise ValueError(
                f"{layer_label} contains multiple DOI aliases for {canonical} "
                f"without a canonical DOI record: {sorted(originals)}"
            )
        preferred_origin[canonical] = canonical

    kept = [
        normalized
        for normalized, original, canonical, _changed in staged
        if original == preferred_origin[canonical]
    ]
    alias_count = sum(int(item[3]) for item in staged)
    return kept, alias_count, len(staged) - len(kept), collision_papers


def assemble_layers(
    base_rows: list[dict],
    overlays: list[tuple[str, list[dict]]],
    *,
    aliases: dict[str, str],
    eligible: set[str],
    row_kind: str = "evidence",
    replacement_dois_by_overlay: dict[str, set[str]] | None = None,
) -> tuple[list[dict], dict]:
    canonicalizer = canonicalize_evidence_row if row_kind == "evidence" else canonicalize_output_row
    doi_getter = evidence_doi if row_kind == "evidence" else output_doi

    canonical_base, base_aliases, base_collision_rows, base_collision_papers = (
        canonicalize_layer_rows(
            base_rows,
            aliases=aliases,
            canonicalizer=canonicalizer,
            doi_getter=doi_getter,
            layer_label="base layer",
        )
    )

    normalized_overlays: list[
        tuple[str, list[dict], set[str], int, int, int]
    ] = []
    owner: dict[str, str] = {}
    declared_replacements = replacement_dois_by_overlay or {}
    unknown_labels = set(declared_replacements) - {label for label, _rows in overlays}
    if unknown_labels:
        raise ValueError(
            "Replacement cohort supplied for unknown overlay label(s): "
            + ", ".join(sorted(unknown_labels))
        )
    for label, rows in overlays:
        normalized_rows, alias_count, collision_rows, collision_papers = canonicalize_layer_rows(
            rows,
            aliases=aliases,
            canonicalizer=canonicalizer,
            doi_getter=doi_getter,
            layer_label=f"overlay {label}",
        )
        dois: set[str] = set()
        for normalized in normalized_rows:
            doi = doi_getter(normalized)
            dois.add(doi)
        replacement_dois = declared_replacements.get(label, dois)
        undeclared_row_dois = dois - replacement_dois
        if undeclared_row_dois:
            raise ValueError(
                f"Overlay {label} contains DOI(s) absent from its replacement cohort: "
                + ", ".join(sorted(undeclared_row_dois)[:10])
            )
        for doi in replacement_dois:
            previous = owner.get(doi)
            if previous and previous != label:
                raise ValueError(f"Overlay DOI {doi} appears in both {previous} and {label}")
            owner[doi] = label
        normalized_overlays.append(
            (
                label,
                normalized_rows,
                dois,
                replacement_dois,
                alias_count,
                collision_rows,
                collision_papers,
            )
        )

    replacement_dois = set(owner)
    kept_base = [
        row for row in canonical_base
        if doi_getter(row) not in replacement_dois and doi_getter(row) in eligible
    ]
    dropped_base_replaced = sum(doi_getter(row) in replacement_dois for row in canonical_base)
    dropped_base_ineligible = sum(
        doi_getter(row) not in replacement_dois and doi_getter(row) not in eligible
        for row in canonical_base
    )

    combined = list(kept_base)
    overlay_report: dict[str, dict] = {}
    for (
        label,
        rows,
        dois,
        replacement_dois,
        alias_count,
        collision_rows,
        collision_papers,
    ) in normalized_overlays:
        kept = [row for row in rows if doi_getter(row) in eligible]
        combined.extend(kept)
        overlay_report[label] = {
            "input_rows": len(rows),
            "input_papers": len(dois),
            "replacement_papers_declared": len(replacement_dois),
            "replacement_papers_without_rows": len(replacement_dois - dois),
            "eligible_rows_added": len(kept),
            "eligible_papers_added": len({doi_getter(row) for row in kept}),
            "ineligible_rows_removed": len(rows) - len(kept),
            "doi_alias_rows_canonicalized": alias_count,
            "doi_alias_collision_rows_removed": collision_rows,
            "doi_alias_collision_papers": collision_papers,
        }

    combined, exact_duplicates = exact_deduplicate(combined)
    report = {
        "base_input_rows": len(base_rows),
        "base_input_papers": len({doi_getter(row) for row in canonical_base}),
        "base_rows_kept": len(kept_base),
        "base_rows_replaced": dropped_base_replaced,
        "base_rows_removed_by_current_eligibility": dropped_base_ineligible,
        "base_doi_alias_rows_canonicalized": base_aliases,
        "base_doi_alias_collision_rows_removed": base_collision_rows,
        "base_doi_alias_collision_papers": base_collision_papers,
        "overlays": overlay_report,
        "exact_duplicate_rows_removed": exact_duplicates,
        "combined_rows": len(combined),
        "combined_papers": len({doi_getter(row) for row in combined}),
    }
    return combined, report


def parse_layer(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or not clean(label) or not clean(raw_path):
        raise argparse.ArgumentTypeError("Layer must be LABEL=PATH")
    return clean(label), Path(raw_path).resolve()


def replacement_cohorts(
    layers: list[tuple[str, Path]], aliases: dict[str, str]
) -> dict[str, set[str]]:
    cohorts: dict[str, set[str]] = {}
    for label, path in layers:
        if label in cohorts:
            raise ValueError(f"Duplicate replacement cohort label: {label}")
        rows = read_jsonl(path) if path.suffix.lower() == ".jsonl" else read_json_list(path)
        dois = {
            resolve_doi(
                row.get("study_doi")
                or row.get("doi")
                or (
                    row.get("result", {}).get("study_doi")
                    if isinstance(row.get("result"), dict)
                    else ""
                ),
                aliases,
            )
            for row in rows
            if normalize_doi(
                row.get("study_doi")
                or row.get("doi")
                or (
                    row.get("result", {}).get("study_doi")
                    if isinstance(row.get("result"), dict)
                    else ""
                )
            )
        }
        if not dois:
            raise ValueError(f"Replacement cohort {label} contains no DOI records: {path}")
        cohorts[label] = dois
    return cohorts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-evidence", type=Path, required=True)
    parser.add_argument("--evidence-overlay", action="append", type=parse_layer, default=[])
    parser.add_argument(
        "--evidence-replacement-cohort",
        action="append",
        type=parse_layer,
        default=[],
        help=(
            "Optional LABEL=JSON_OR_JSONL declaring every paper replaced by an "
            "evidence overlay, including papers with valid zero-row outcomes."
        ),
    )
    parser.add_argument("--base-outputs", type=Path, required=True)
    parser.add_argument("--output-overlay", action="append", type=parse_layer, default=[])
    parser.add_argument("--candidate-table", type=Path, required=True)
    parser.add_argument("--eligibility-field", default="retained_for_extraction_candidate")
    parser.add_argument("--doi-alias-registry", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    aliases = read_aliases(args.doi_alias_registry)
    evidence_replacement_cohorts = replacement_cohorts(
        args.evidence_replacement_cohort, aliases
    )
    eligible = eligible_dois(args.candidate_table, args.eligibility_field, aliases)
    metadata_by_doi = candidate_metadata(args.candidate_table, aliases)
    evidence, evidence_report = assemble_layers(
        read_json_list(args.base_evidence),
        [(label, read_json_list(path)) for label, path in args.evidence_overlay],
        aliases=aliases,
        eligible=eligible,
        row_kind="evidence",
        replacement_dois_by_overlay=evidence_replacement_cohorts,
    )
    evidence, metadata_report = apply_candidate_metadata(evidence, metadata_by_doi)
    evidence_report.update(metadata_report)
    reject_non_v2_meta_analysis_evidence(evidence)
    outputs, output_report = assemble_layers(
        read_jsonl(args.base_outputs),
        [(label, read_jsonl(path)) for label, path in args.output_overlay],
        aliases=aliases,
        eligible=eligible,
        row_kind="output",
    )
    outputs, legacy_output_report = remove_legacy_v1_secondary_outputs(outputs)
    output_report.update(legacy_output_report)
    output_report["combined_rows_before_legacy_v1_removal"] = output_report["combined_rows"]
    output_report["combined_papers_before_legacy_v1_removal"] = output_report[
        "combined_papers"
    ]
    output_report["combined_rows"] = len(outputs)
    output_report["combined_papers"] = len({output_doi(row) for row in outputs})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.out_dir / "routed_evidence_rows.json"
    outputs_path = args.out_dir / "route_extraction_outputs.jsonl"
    report_path = args.out_dir / "combined_release_assembly_report.json"
    write_json(evidence_path, evidence)
    write_jsonl(outputs_path, outputs)
    report = {
        "schema_version": "combined_routed_release_assembly_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "run_id": args.run_id,
        "eligibility": {
            "candidate_table": str(args.candidate_table.resolve()),
            "field": args.eligibility_field,
            "eligible_canonical_dois": len(eligible),
        },
        "doi_alias_registry": str(args.doi_alias_registry.resolve()),
        "evidence": evidence_report,
        "outputs": output_report,
        "inputs": {
            "base_evidence": str(args.base_evidence.resolve()),
            "evidence_overlays": {label: str(path) for label, path in args.evidence_overlay},
            "evidence_replacement_cohorts": {
                label: str(path) for label, path in args.evidence_replacement_cohort
            },
            "base_outputs": str(args.base_outputs.resolve()),
            "output_overlays": {label: str(path) for label, path in args.output_overlay},
        },
        "artifacts": {
            "evidence": str(evidence_path.resolve()),
            "outputs": str(outputs_path.resolve()),
        },
        "source_type_counts": dict(
            sorted(Counter(clean(row.get("source_type", "")) for row in evidence).items())
        ),
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
