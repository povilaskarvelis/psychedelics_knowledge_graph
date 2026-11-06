"""Gather source-identity decisions from the older per-incident files.

The pipeline still reads those files. This command copies their decisions into
the one decision file, so that later steps can switch readers without losing
any. Migrated entries are regenerated from their sources on every run; entries
recorded directly in the decision file are kept byte for byte. ``--check``
reports whether the decision file still matches its sources.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from pipeline.ingest.candidate_status import clean, normalize_doi
from pipeline.identity.register import (
    DEFAULT_DECISIONS_PATH,
    decision_id,
    normalize_decision,
    read_decision_lines,
    serialize_decision,
    validate_decisions,
    write_decision_lines,
)
from pipeline.identity.works import DEFAULT_WORK_REGISTRY, load_work_relations


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SOURCES = {
    "identity_registry": ROOT / "pipeline" / "fulltext" / "source_identity_registry.json",
    "pdf_hash_registry": ROOT / "pipeline" / "fulltext" / "source_identity_pdf_hash_registry.json",
    "route_holds": ROOT / "pipeline" / "extract" / "manual_extraction_route_overrides.json",
    "metadata_overrides": ROOT / "data" / "curated" / "paper_metadata_overrides.json",
    "graph_dispositions": ROOT / "data" / "curated" / "graph_inclusion_disposition_overrides.json",
    "pdf_url_corrections": ROOT / "data" / "curated" / "pdf_source_url_corrections.json",
}
NOT_MIGRATED = {
    "pipeline/fulltext/manual_fulltext_access_overrides.json": "access decisions: whether and how to retrieve text",
    "pipeline/validate/doi_alias_registry.json": "the work registry of relations between DOIs, read through pipeline.identity.works",
}
# Identity-registry actions that accept the text as the requested paper because
# the DOI parsed from the document is wrong, versus a related document.
REGISTRY_PARSE_ERROR_ACTIONS = {"ignore_incorrect_extracted_document_doi", "no_override_required"}
REGISTRY_RELATED_ACTIONS = {"accept_related_document_doi", "accept_correction_original_doi"}
REGISTRY_RELATIONS = {
    "preprint_repository_version": "preprint_or_repository_copy",
    "publisher_doi_alias": "same_publication",
    "article_version": "version_doi",
    "publisher_language_alias": "translation",
    "correction_record_to_original_doi": "correction_pair",
}
REGISTRY_CONDITION = (
    "Applies only when the artifact shows this document DOI and the requested title "
    "matches its front matter (registry acceptance policy)."
)


def relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())


def load_json(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must hold a JSON object")
    return payload


def migrated(source: str, path: Path, key: str, decision: dict) -> dict:
    origin = {"source": source, "file": relative(path), "key": key}
    return normalize_decision(
        {
            "decision_id": decision_id(source, key, decision["verdict"]),
            **decision,
            "origin": origin,
        }
    )


def from_identity_registry(path: Path) -> tuple[list[dict], list[dict]]:
    payload = load_json(path)
    reviewed_at = clean(payload.get("reviewed_at", ""))
    decisions, skipped = [], []
    for record in payload.get("records", []):
        requested = normalize_doi(record.get("requested_doi", ""))
        observed = normalize_doi(record.get("observed_document_doi", ""))
        action = clean(record.get("identity_action", ""))
        relationship = clean(record.get("relationship_type", ""))
        if action == "no_override_required":
            verdict, relation = "verified", ""
            meaning = "the document DOI is the requested DOI; the entry was not needed"
        elif action in REGISTRY_PARSE_ERROR_ACTIONS:
            verdict, relation = "verified", ""
            meaning = "the DOI read from the document is wrong; the text is the requested paper"
        elif action in REGISTRY_RELATED_ACTIONS and relationship in REGISTRY_RELATIONS:
            verdict, relation = "version_of", REGISTRY_RELATIONS[relationship]
            meaning = f"the text is the related document {observed}"
        else:
            skipped.append({"source": "identity_registry", "doi": requested, "reason": f"unmapped action {action!r} / {relationship!r}"})
            continue
        decision = {
            "doi": requested,
            "target": {"kind": "fulltext", "document_doi": observed},
            "verdict": verdict,
            "basis": clean(record.get("review_basis", "")) or f"Curated registry: {meaning}. {REGISTRY_CONDITION}",
            "evidence": [value for value in [clean(record.get("source_artifact", ""))] if value],
            "reviewer": f"legacy: {relative(path)}",
            "legacy": {key: record[key] for key in ("relationship_type", "identity_action", "record_group") if key in record},
        }
        if relation:
            decision.update(relation=relation, related_doi=observed)
        if reviewed_at:
            decision["decided_at"] = reviewed_at
        decisions.append(migrated("identity_registry", path, f"{requested}|{observed}", decision))
    return decisions, skipped


def from_pdf_hash_registry(path: Path) -> tuple[list[dict], list[dict]]:
    decisions = []
    for record in load_json(path).get("records", []):
        doi = normalize_doi(record.get("requested_doi", ""))
        sha = clean(record.get("pdf_sha256", "")).casefold()
        decisions.append(
            migrated(
                "pdf_hash_registry",
                path,
                f"{doi}|{sha}",
                {
                    "doi": doi,
                    "target": {"kind": "fulltext", "pdf_sha256": sha},
                    "verdict": "verified",
                    "basis": clean(record.get("review_basis", "")),
                    "evidence": [
                        value
                        for value in (clean(record.get("source_url", "")), clean(record.get("source_artifact", "")))
                        if value
                    ],
                    "reviewer": f"legacy: {relative(path)}",
                    "decided_at": clean(record.get("reviewed_at", "")),
                    "legacy": {
                        key: record[key]
                        for key in ("document_kind", "expected_title", "source_quality_note")
                        if key in record
                    },
                },
            )
        )
    return decisions, []


def from_route_holds(path: Path) -> tuple[list[dict], list[dict]]:
    decisions, skipped = [], []
    for record in load_json(path).get("records", []):
        doi = normalize_doi(record.get("doi", ""))
        if clean(record.get("manual_action", "")) != "hold_source_review":
            skipped.append({"source": "route_holds", "doi": doi, "reason": "route override, not an identity decision"})
            continue
        decisions.append(
            migrated(
                "route_holds",
                path,
                doi,
                {
                    "doi": doi,
                    "target": {"kind": "record"},
                    "verdict": "hold",
                    "basis": clean(record.get("manual_reason", "")),
                    "evidence": [value for value in [clean(record.get("evidence_artifact", ""))] if value],
                    "reviewer": clean(record.get("reviewed_by", "")) or f"legacy: {relative(path)}",
                    "legacy": {
                        key: record[key]
                        for key in ("manual_action", "routing_repair_plan")
                        if key in record
                    },
                },
            )
        )
    return decisions, skipped


def from_metadata_overrides(path: Path) -> tuple[list[dict], list[dict]]:
    decisions, skipped = [], []
    seen: Counter[str] = Counter()
    for record in load_json(path).get("records", []):
        # A record that `apply` wrote from a decision is already in the decision file.
        if record.get("source_decision"):
            continue
        doi = normalize_doi(record.get("doi", ""))
        fields = {key: value for key, value in (record.get("fields") or {}).items() if clean(value)}
        clear_fields = [clean(field) for field in record.get("clear_fields") or [] if clean(field)]
        if not fields and not clear_fields:
            skipped.append({"source": "metadata_overrides", "doi": doi, "reason": "no field set or cleared"})
            continue
        seen[doi] += 1
        key = doi if seen[doi] == 1 else f"{doi}#{seen[doi]}"
        decisions.append(
            migrated(
                "metadata_overrides",
                path,
                key,
                {
                    "doi": doi,
                    "target": {"kind": "record"},
                    "verdict": "record_corrected",
                    "fields": fields,
                    "clear_fields": clear_fields,
                    "basis": clean(record.get("evidence_basis", "")),
                    "reviewer": f"legacy: {relative(path)}",
                    "legacy": {
                        key: record[key]
                        for key in ("source_repair_evidence_20261022", "source_repair_followups", "prior_evidence_basis")
                        if key in record
                    },
                },
            )
        )
    return decisions, skipped


def from_graph_dispositions(path: Path) -> tuple[list[dict], list[dict]]:
    decisions, skipped = [], []
    for group in load_json(path).get("overrides", []):
        disposition = clean(group.get("disposition", ""))
        for raw_doi in group.get("dois", []):
            doi = normalize_doi(raw_doi)
            if disposition != "source_not_verified":
                skipped.append({"source": "graph_dispositions", "doi": doi, "reason": f"disposition {disposition!r} is not an identity decision"})
                continue
            decisions.append(
                migrated(
                    "graph_dispositions",
                    path,
                    f"{doi}|{disposition}",
                    {
                        "doi": doi,
                        "target": {"kind": "record"},
                        "verdict": "hold",
                        "basis": clean(group.get("reason", "")),
                        "reviewer": f"legacy: {relative(path)}",
                        "legacy": {"disposition": disposition, "next_action": clean(group.get("next_action", ""))},
                    },
                )
            )
    return decisions, skipped


def from_pdf_url_corrections(path: Path) -> tuple[list[dict], list[dict]]:
    decisions = []
    for record in load_json(path).get("records", []):
        doi = normalize_doi(record.get("doi", ""))
        rejected_url = clean(record.get("rejected_url", ""))
        decisions.append(
            migrated(
                "pdf_url_corrections",
                path,
                f"{doi}|{rejected_url}",
                {
                    "doi": doi,
                    "target": {"kind": "fulltext", "source_url": rejected_url},
                    "verdict": "not_this_work",
                    "basis": clean(record.get("evidence", "")),
                    "reviewer": f"legacy: {relative(path)}",
                    "legacy": {
                        key: record[key]
                        for key in ("replacement_pdf_url", "replacement_landing_url")
                        if key in record
                    },
                },
            )
        )
    return decisions, []


CONVERTERS = {
    "identity_registry": from_identity_registry,
    "pdf_hash_registry": from_pdf_hash_registry,
    "route_holds": from_route_holds,
    "metadata_overrides": from_metadata_overrides,
    "graph_dispositions": from_graph_dispositions,
    "pdf_url_corrections": from_pdf_url_corrections,
}


def migrated_decisions(sources: dict[str, Path] = LEGACY_SOURCES) -> tuple[list[dict], list[dict]]:
    decisions: list[dict] = []
    skipped: list[dict] = []
    for source, path in sources.items():
        if not Path(path).exists():
            skipped.append({"source": source, "doi": "", "reason": f"source file missing: {relative(path)}"})
            continue
        found, passed_over = CONVERTERS[source](Path(path))
        decisions.extend(found)
        skipped.extend(passed_over)
    return decisions, skipped


def run_migration(
    *,
    decisions_path: Path = DEFAULT_DECISIONS_PATH,
    sources: dict[str, Path] = LEGACY_SOURCES,
    work_registry: Path = DEFAULT_WORK_REGISTRY,
    check: bool = False,
) -> dict:
    """Regenerate migrated entries; keep entries recorded directly in the file."""
    existing = read_decision_lines(decisions_path)
    native = [
        (line, decision)
        for line, decision in existing
        if not isinstance(decision.get("origin"), dict) or decision["origin"].get("source") not in sources
    ]
    regenerated, skipped = migrated_decisions(sources)
    validate_decisions(regenerated + [decision for _line, decision in native])
    lines = [serialize_decision(decision) for decision in regenerated] + [line for line, _decision in native]
    in_sync = [line for line, _decision in existing] == lines
    if not check and not in_sync:
        write_decision_lines(decisions_path, lines)
    relations = load_work_relations(work_registry) if Path(work_registry).exists() else []
    return {
        "decisions_path": relative(decisions_path),
        "mode": "check" if check else "write",
        "in_sync_before": in_sync,
        "written": not check and not in_sync,
        "migrated": len(regenerated),
        "native_kept": len(native),
        "by_source": dict(Counter(decision["origin"]["source"] for decision in regenerated)),
        "by_verdict": dict(Counter(decision["verdict"] for decision in regenerated)),
        "papers": len({decision["doi"] for decision in regenerated}),
        "skipped": dict(Counter(f"{row['source']}: {row['reason']}" for row in skipped)),
        "not_migrated": NOT_MIGRATED,
        "work_registry_relations": dict(Counter(row["relation"] for row in relations)),
        "work_registry_without_relation_name": sum(1 for row in relations if not row["legacy_relationship_type"]),
    }
