#!/usr/bin/env python3
"""Build the compact, study-level index used by the browser Analyze workspace."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTIVE = ROOT / "data" / "processed" / "graph_payload_active.json"
ANALYSIS_INDEX_SCHEMA = "psychedelics_kg_analysis_index_v1"
SOURCE_KEYS = ("primary", "meta_analyses", "reviews")
SPECIFIC_COMPOUND_KINDS = {"atomic_compound", "compound_combination"}
HIDDEN_DOMAINS = {"pharmacokinetics_exposure"}
OPEN_ACCESS_LEVELS = {"article_text", "full_text", "full_text_seen"}
CONDITION_LABELS = {
    "attention-deficit/hyperactivity disorder": "ADHD",
    "distress associated with life-threatening disease": "Distress in life-threatening illness",
    "nicotine dependence": "Tobacco use disorder",
    "suicidality": "Suicidal ideation & behavior",
}
TARGET_LABELS = {
    "alpha7 nicotinic acetylcholine receptor (chrna7)": "α7 nAChR",
    "alpha3beta4 nicotinic acetylcholine receptor": "α3β4 nAChR",
    "alpha4beta2 nicotinic acetylcholine receptor": "α4β2 nAChR",
    "kappa opioid receptor (oprk1)": "κ-opioid receptor",
    "mu opioid receptor (oprm1)": "μ-opioid receptor",
    "delta opioid receptor (oprd1)": "δ-opioid receptor",
}


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def key(value: object) -> str:
    return clean(value).casefold()


def parse_json(value: object) -> object:
    if isinstance(value, (dict, list)):
        return value
    text = clean(value)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_columnar(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload.get("fields") or []
    values = payload.get("values") or []
    rows = []
    for encoded in payload.get("rows") or []:
        row = {}
        for index, field in enumerate(fields):
            value_index = int(encoded[index] or 0) if index < len(encoded) else 0
            value = values[value_index] if 0 <= value_index < len(values) else None
            if value not in (None, ""):
                row[field] = value
        rows.append(row)
    return rows


def study_key(row: dict) -> str:
    doi = key(row.get("study_doi"))
    if doi:
        return f"doi:{doi}"
    openalex = key(row.get("openalex_id"))
    if openalex:
        return f"openalex:{openalex}"
    title = key(row.get("study_title"))
    year = clean(row.get("study_year"))
    return f"title:{title}|{year}" if title or year else ""


def preferred_label(current: str, candidate: str) -> str:
    if not current:
        return candidate
    current_upper = sum(character.isupper() for character in current)
    candidate_upper = sum(character.isupper() for character in candidate)
    return candidate if (candidate_upper, len(candidate)) > (current_upper, len(current)) else current


def author_identity(value: object) -> tuple[str, str] | None:
    parsed = parse_json(value)
    if not isinstance(parsed, dict):
        return None
    label = clean(parsed.get("display_name") or parsed.get("name") or parsed.get("author_name"))
    stable = clean(parsed.get("id") or parsed.get("author_id") or parsed.get("orcid") or parsed.get("openalex_author_id"))
    if not label and not stable:
        return None
    return (stable or label, label or stable)


def fallback_authors(value: object) -> list[str]:
    text = clean(value)
    if not text:
        return []
    parts = [clean(part) for part in text.split(";")] if ";" in text else [text]
    return [part for part in parts if part]


def analysis_authors(row: dict) -> list[tuple[str, str]]:
    values = [author_identity(row.get("first_author")), author_identity(row.get("last_author"))]
    fallback = fallback_authors(row.get("authors"))
    if values[0] is None and fallback:
        values[0] = (fallback[0], fallback[0])
    if values[1] is None and fallback:
        values[1] = (fallback[-1], fallback[-1])
    seen = set()
    result = []
    for item in values:
        if item is None:
            continue
        normalized = key(item[0])
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


def analysis_compounds(row: dict) -> list[tuple[str, str]]:
    raw = parse_json(row.get("graph_overview_subjects_json"))
    subjects = raw if isinstance(raw, list) else []
    if not subjects:
        label = clean(row.get("graph_overview_subject_label") or row.get("compound"))
        kind_value = clean(row.get("graph_overview_subject_kind") or row.get("graph_subject_kind") or "atomic_compound")
        subjects = [{"label": label, "kind": kind_value}] if label else []
    seen = set()
    result = []
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        label = clean(subject.get("label"))
        kind_value = key(subject.get("kind") or "atomic_compound").replace("-", " ").replace(" ", "_")
        normalized = key(label)
        if kind_value not in SPECIFIC_COMPOUND_KINDS or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append((normalized, label))
    return result


def graph_contract() -> list[dict]:
    payload = json.loads((ROOT / "schema" / "graph_view_contract.json").read_text(encoding="utf-8"))
    return payload.get("views") or []


def row_matches_area(row: dict, area: dict) -> bool:
    kind_value = key(row.get("entity_kind"))
    domain = key(row.get("domain") or row.get("finding_type"))
    label = key(row.get("graph_entity_label") or row.get("entity_label"))
    kinds = {key(value) for value in area.get("object_kinds") or []}
    domains = {key(value) for value in area.get("domains") or []}
    labels = {key(value) for value in area.get("object_labels") or []}
    return (
        (not kinds or kind_value in kinds)
        and (not domains or domain in domains)
        and (not labels or label in labels)
    )


def concept_for_row(row: dict, area_key: str) -> str:
    right = clean(row.get("graph_entity_label") or row.get("entity_label"))
    if not right:
        return ""
    if area_key == "pathway_readout":
        return clean(row.get("graph_parent_label") or row.get("molecular_finding_subtopic") or right)
    if area_key in {"brain_system", "intervention_component"}:
        return clean(row.get("graph_parent_label") or right)
    if area_key == "condition_indication":
        return CONDITION_LABELS.get(key(right), right)
    if area_key == "target_system":
        return TARGET_LABELS.get(key(right), right)
    return right


def compact_memberships(memberships: dict[str, set[int]], labels: dict[str, str]) -> list[list[object]]:
    return [
        [entity_key, labels.get(entity_key, entity_key), sorted(studies)]
        for entity_key, studies in sorted(
            memberships.items(),
            key=lambda item: (-len(item[1]), labels.get(item[0], item[0]).casefold()),
        )
        if studies
    ]


def compact_entity_memberships(
    memberships: dict[str, set[int]],
    labels: dict[str, str],
    area_memberships: dict[str, dict[str, set[int]]],
    concept_memberships: dict[str, dict[str, dict[str, set[int]]]],
) -> list[list[object]]:
    entries = []
    for entity_key, studies in sorted(
        memberships.items(),
        key=lambda item: (-len(item[1]), labels.get(item[0], item[0]).casefold()),
    ):
        if not studies:
            continue
        areas = {
            area_key: sorted(ids)
            for area_key, ids in area_memberships.get(entity_key, {}).items()
            if ids
        }
        concepts = {
            area_key: {
                concept_key: sorted(ids)
                for concept_key, ids in area_concepts.items()
                if ids
            }
            for area_key, area_concepts in concept_memberships.get(entity_key, {}).items()
            if any(area_concepts.values())
        }
        entries.append(
            [entity_key, labels.get(entity_key, entity_key), sorted(studies), areas, concepts]
        )
    return entries


def build_index(rows_by_source: dict[str, list[dict]], generated_at: str = "") -> dict:
    areas = graph_contract()
    studies: list[dict] = []
    study_ids: dict[str, int] = {}
    area_memberships: dict[str, set[int]] = {area["id"]: set() for area in areas}
    concept_memberships: dict[str, dict[str, set[int]]] = {
        area["id"]: defaultdict(set) for area in areas
    }
    concept_labels: dict[str, dict[str, str]] = {area["id"]: {} for area in areas}
    entity_memberships: dict[str, dict[str, set[int]]] = {
        "compound": defaultdict(set),
        "author": defaultdict(set),
        "journal": defaultdict(set),
    }
    entity_labels: dict[str, dict[str, str]] = {lens: {} for lens in entity_memberships}
    entity_area_memberships = {
        lens: defaultdict(lambda: defaultdict(set)) for lens in entity_memberships
    }
    entity_concept_memberships = {
        lens: defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        for lens in entity_memberships
    }

    for source_key in SOURCE_KEYS:
        for row in rows_by_source.get(source_key, []):
            domain = key(row.get("domain") or row.get("finding_type"))
            admission = key(row.get("graph_admission_status"))
            if domain in HIDDEN_DOMAINS or (admission and admission != "main_graph"):
                continue
            stable_key = study_key(row)
            if not stable_key:
                continue
            study_id = study_ids.get(stable_key)
            if study_id is None:
                study_id = len(studies)
                study_ids[stable_key] = study_id
                try:
                    year = int(float(clean(row.get("study_year"))))
                except ValueError:
                    year = 0
                studies.append(
                    {
                        "key": stable_key,
                        "source": source_key,
                        "year": year if 1800 <= year <= 3000 else 0,
                        "open": key(
                            row.get("text_depth")
                            or row.get("source_access_level")
                            or row.get("access_level")
                        ) in OPEN_ACCESS_LEVELS,
                    }
                )
            elif key(
                row.get("text_depth")
                or row.get("source_access_level")
                or row.get("access_level")
            ) in OPEN_ACCESS_LEVELS:
                studies[study_id]["open"] = True

            row_dimensions: list[tuple[str, str]] = []
            for area in areas:
                area_key = area["id"]
                if not row_matches_area(row, area):
                    continue
                area_memberships[area_key].add(study_id)
                label = concept_for_row(row, area_key)
                concept_key = key(label)
                if concept_key:
                    concept_memberships[area_key][concept_key].add(study_id)
                    concept_labels[area_key][concept_key] = preferred_label(
                        concept_labels[area_key].get(concept_key, ""), label
                    )
                row_dimensions.append((area_key, concept_key))

            row_entities: dict[str, list[tuple[str, str]]] = {
                "compound": analysis_compounds(row),
                "author": [(key(author_key), label) for author_key, label in analysis_authors(row)],
                "journal": [],
            }
            journal = clean(row.get("study_journal"))
            journal_key = key(journal)
            if journal_key:
                row_entities["journal"].append((journal_key, journal))

            for lens, entities in row_entities.items():
                for entity_key, label in entities:
                    if not entity_key:
                        continue
                    entity_memberships[lens][entity_key].add(study_id)
                    entity_labels[lens][entity_key] = preferred_label(
                        entity_labels[lens].get(entity_key, ""), label
                    )
                    for area_key, concept_key in row_dimensions:
                        entity_area_memberships[lens][entity_key][area_key].add(study_id)
                        if concept_key:
                            entity_concept_memberships[lens][entity_key][area_key][concept_key].add(study_id)

    return {
        "schema_version": ANALYSIS_INDEX_SCHEMA,
        "generated_at": generated_at,
        "study_count": len(studies),
        "studies": [
            [study["key"], study["source"], study["year"], 1 if study["open"] else 0]
            for study in studies
        ],
        "areas": {
            area["id"]: [area.get("label") or area["id"], sorted(area_memberships[area["id"]])]
            for area in areas
        },
        "concepts": {
            area["id"]: compact_memberships(
                concept_memberships[area["id"]], concept_labels[area["id"]]
            )
            for area in areas
        },
        "entities": {
            lens: compact_entity_memberships(
                entity_memberships[lens],
                entity_labels[lens],
                entity_area_memberships[lens],
                entity_concept_memberships[lens],
            )
            for lens in entity_memberships
        },
    }


def active_detail_paths(active_path: Path) -> tuple[dict[str, Path], str]:
    active = json.loads(active_path.read_text(encoding="utf-8"))
    mapping = active.get("active_detail_bootstraps") or {}
    paths = {
        source: ROOT / clean(mapping[source])
        for source in SOURCE_KEYS
    }
    manifest_path = ROOT / clean(active.get("active_manifest"))
    generated_at = ""
    if manifest_path.is_file():
        generated_at = clean(json.loads(manifest_path.read_text(encoding="utf-8")).get("generated_at"))
    return paths, generated_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active", type=Path, default=DEFAULT_ACTIVE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths, generated_at = active_detail_paths(args.active.resolve())
    rows_by_source = {source: load_columnar(path) for source, path in paths.items()}
    payload = build_index(rows_by_source, generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"Built analysis index with {payload['study_count']} studies at {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
