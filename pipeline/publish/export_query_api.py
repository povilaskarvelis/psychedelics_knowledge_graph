#!/usr/bin/env python3
"""Build the narrow, versioned query catalogue for REST and MCP.

The internal knowledge graph contains extraction detail that is useful to the
website but is not a stable public data contract. This exporter publishes only
papers, concepts, OpenAlex/ORCID-backed authors, and deduplicated paper-level
relationships. Granular findings and unfinished curation fields remain private.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

try:
    from pipeline.publish.export_evidence_payload import (
        load_findings,
        ui_source_key_for_finding,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    import sys

    ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT_FOR_IMPORT))
    from pipeline.publish.export_evidence_payload import (
        load_findings,
        ui_source_key_for_finding,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KG_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_OUT_ROOT = ROOT / "data" / "processed" / "query_api_runs"

PUBLIC_QUERY_SCHEMA_VERSION = "psychedelics_kg_public_catalogue_v2"
PUBLIC_QUERY_MANIFEST_VERSION = "psychedelics_kg_public_catalogue_manifest_v2"
PUBLIC_DB_NAME = "public_api.duckdb"
PUBLIC_SCHEMA_NAME = "schema.json"
PUBLIC_MANIFEST_NAME = "manifest.json"

PUBLIC_RELATIONSHIP_SOURCE_FIELDS = (
    "domain",
    "entity_kind",
    "relation_type",
    "compound_id",
    "compound",
    "graph_subject_kind",
    "entity_id",
    "entity_label",
    "paper_id",
    "graph_admission_status",
)

PUBLIC_CONCEPT_SOURCE_FIELDS = (
    "entity_id",
    "entity_type",
    "domain",
    "entity_kind",
    "label",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
    "aliases_json",
    "ids_json",
)

PUBLIC_PAPER_SOURCE_FIELDS = (
    "paper_id",
    "doi",
    "openalex_id",
    "title",
    "authors",
    "year",
    "journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "funders",
    "grant_ids",
    "funding_metadata_status",
    "funding_providers",
    "funding_assertion_count",
    "funding_funder_count",
    "funding_award_count",
)

PUBLIC_AUTHOR_FIELDS = (
    "author_id",
    "display_name",
    "canonical_name",
    "openalex_author_id",
    "openalex_author_ids_json",
    "orcid",
    "identity_confidence",
    "display_names_json",
    "paper_count",
)

PUBLIC_PAPER_AUTHOR_FIELDS = (
    "paper_id",
    "author_id",
    "display_name",
    "canonical_name",
    "identity_confidence",
    "author_position",
    "is_first_author",
    "is_last_author",
)

FIELD_DESCRIPTIONS = {
    "paper_id": "Stable paper identifier, normally DOI-based when a DOI is available.",
    "doi": "Digital Object Identifier without a URL prefix.",
    "openalex_id": "OpenAlex work identifier when available.",
    "title": "Paper or report title.",
    "year": "Publication year.",
    "journal": "Journal or publication venue.",
    "publication_type": "Publication type supplied by the bibliographic source.",
    "publication_date": "Publication date when available.",
    "publisher": "Publisher when available.",
    "journal_issn": "Print ISSN when available.",
    "journal_eissn": "Electronic ISSN when available.",
    "language": "Publication language when available.",
    "open_access_is_oa": "Whether an open-access copy is known to be available.",
    "open_access_status": "Open-access category when available.",
    "open_access_url": "URL of a known open-access copy when available.",
    "funders": "Provider-backed funder names associated with the paper, joined as a pipe-delimited list.",
    "grant_ids": "Provider-backed grant or award identifiers associated with the paper, joined as a pipe-delimited list.",
    "funding_metadata_status": "Funding-enrichment result for the paper, distinguishing reported funding from no funding reported by queried providers.",
    "funding_providers": "Providers that supplied at least one normalized funding assertion for the paper.",
    "funding_assertion_count": "Number of normalized provider funding assertions retained for the paper.",
    "funding_funder_count": "Number of distinct normalized funders retained for the paper.",
    "funding_award_count": "Number of distinct grant or award identifiers retained for the paper.",
    "paper_type": "Broad controlled type: primary_study, meta_analysis, or review.",
    "paper_subtype": "More specific controlled paper classification when available.",
    "concept_id": "Stable identifier for a standardized concept.",
    "concept_type": "Broad concept family used by the knowledge graph.",
    "concept_kind": "Controlled concept category.",
    "domain": "Research domain associated with a concept or relationship.",
    "label": "Preferred human-readable concept label.",
    "parent_label": "Preferred label of the broader parent concept when available.",
    "parent_kind": "Category of the broader parent concept when available.",
    "parent_concept_id": "Identifier of the broader parent concept when available.",
    "aliases_json": "JSON array of alternative labels.",
    "external_ids_json": "JSON object of external identifiers when available.",
    "author_id": "Canonical ORCID identifier when available; otherwise an OpenAlex author-profile identifier.",
    "author_name": "Preferred author name from structured authorship metadata.",
    "normalized_name": "Normalized preferred author name used for matching.",
    "openalex_author_id": "OpenAlex author identifier when available.",
    "openalex_author_ids_json": "JSON array of OpenAlex author profiles linked to this identity.",
    "orcid": "ORCID identifier when available.",
    "identity_source": "External identifier used for the public author identity.",
    "name_variants_json": "JSON array of credited name variants linked to this identity.",
    "openalex_profile_ids_json": "JSON array of OpenAlex author profiles linked to this identity.",
    "paper_count": "Number of catalogue papers linked to this ORCID/OpenAlex author identity.",
    "author_position": "Position in the paper's credited author list.",
    "is_first_author": "Whether this is the first credited author.",
    "is_last_author": "Whether this is the last credited author.",
    "relationship_id": "Stable identifier for one deduplicated paper-level relationship.",
    "subject_id": "Concept identifier at the subject end of the relationship.",
    "subject_label": "Preferred label at the subject end of the relationship.",
    "subject_kind": "Concept category at the subject end of the relationship.",
    "object_id": "Concept identifier at the object end of the relationship.",
    "object_label": "Preferred label at the object end of the relationship.",
    "object_kind": "Concept category at the object end of the relationship.",
    "relation_type": "Controlled type describing the paper-level relationship.",
}

TABLE_METADATA = {
    "papers": {
        "description": "One row per paper or report in the public catalogue.",
        "grain": "paper",
        "primary_key": ["paper_id"],
        "foreign_keys": [],
    },
    "concepts": {
        "description": "One row per standardized concept used in public relationships.",
        "grain": "concept",
        "primary_key": ["concept_id"],
        "foreign_keys": [{"fields": ["parent_concept_id"], "references": "concepts.concept_id"}],
    },
    "authors": {
        "description": "One row per OpenAlex- or ORCID-backed author identity.",
        "grain": "ORCID/OpenAlex author identity",
        "primary_key": ["author_id"],
        "foreign_keys": [],
    },
    "paper_authors": {
        "description": "One row per OpenAlex/ORCID-backed authorship on a paper.",
        "grain": "paper-author credit",
        "primary_key": ["paper_id", "author_id", "author_position"],
        "foreign_keys": [
            {"fields": ["paper_id"], "references": "papers.paper_id"},
            {"fields": ["author_id"], "references": "authors.author_id"},
        ],
    },
    "relationships": {
        "description": "One deduplicated relationship between two concepts reported by one paper.",
        "grain": "paper-subject-object-relation",
        "primary_key": ["relationship_id"],
        "foreign_keys": [
            {"fields": ["paper_id"], "references": "papers.paper_id"},
            {"fields": ["subject_id"], "references": "concepts.concept_id"},
            {"fields": ["object_id"], "references": "concepts.concept_id"},
        ],
    },
}

PUBLIC_PAPER_TYPES = {"primary_study", "meta_analysis", "review"}
MIN_STRUCTURED_AUTHORSHIP_RATE = 0.95
PUBLIC_PAPER_SUBTYPES = {
    "primary_study",
    "meta_analysis",
    "network_meta_analysis",
    "review",
    "systematic_review",
    "narrative_review",
    "scoping_review",
    "literature_review",
    "umbrella_review",
    "guideline",
    "consensus_statement",
}

REQUIRED_NONEMPTY_FIELDS = {
    "papers": ["paper_id", "title"],
    "concepts": ["concept_id", "concept_type", "concept_kind", "domain", "label"],
    "authors": ["author_id", "author_name", "normalized_name", "identity_source"],
    "paper_authors": ["paper_id", "author_id", "author_name", "normalized_name"],
    "relationships": [
        "relationship_id",
        "paper_id",
        "subject_id",
        "subject_label",
        "subject_kind",
        "object_id",
        "object_label",
        "object_kind",
        "domain",
        "relation_type",
        "paper_type",
        "paper_subtype",
    ],
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def read_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def root_relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def json_safe_scalar(value: object) -> object:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def selected_columns(df: pd.DataFrame, fields: Iterable[str], *, table_name: str) -> pd.DataFrame:
    fields = tuple(fields)
    columns = [field for field in fields if field in df.columns]
    missing_required = {
        "entities": {"entity_id", "label"},
        "papers": {"paper_id"},
        "evidence_edges": {"paper_id", "compound_id", "entity_id", "relation_type"},
        "authors": {"author_id", "display_name"},
        "paper_authors": {"paper_id", "author_id", "display_name"},
    }.get(table_name, set()) - set(columns)
    if missing_required:
        raise ValueError(f"{table_name} is missing required public columns: {sorted(missing_required)}")
    selected = df[columns].copy()
    # Keep the public schema stable when an optional source column is absent in
    # a small or older release. This lets clients rely on fields across updates.
    for field in fields:
        if field not in selected.columns:
            selected[field] = None
    selected = selected[list(fields)]
    return selected


def paper_classifications(kg_dir: Path) -> dict[str, tuple[str, str]]:
    broad_by_source = {
        "primary": "primary_study",
        "meta_analyses": "meta_analysis",
        "reviews": "review",
    }
    values: dict[str, set[tuple[str, str]]] = {}
    for finding in load_findings(kg_dir):
        paper_id = normalize(finding.get("paper_id"))
        source = ui_source_key_for_finding(finding)
        if not paper_id or source not in broad_by_source:
            continue
        broad = broad_by_source[source]
        subtype = normalize(finding.get("paper_type")) or broad
        values.setdefault(paper_id, set()).add((broad, subtype))

    conflicting = {paper_id: sorted(items) for paper_id, items in values.items() if len(items) > 1}
    if conflicting:
        samples = dict(list(conflicting.items())[:5])
        raise ValueError(f"Conflicting public paper classifications: {samples}")
    return {paper_id: next(iter(items)) for paper_id, items in values.items()}


def normalize_public_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if column in {
            "year",
            "author_position",
            "paper_count",
            "funding_assertion_count",
            "funding_funder_count",
            "funding_award_count",
        }:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
        elif column in {"open_access_is_oa", "is_first_author", "is_last_author"}:
            out[column] = out[column].map(
                lambda value: (
                    True
                    if normalize(value).casefold() in {"true", "1", "yes"}
                    else False
                    if normalize(value).casefold() in {"false", "0", "no"}
                    else pd.NA
                )
            ).astype("boolean")
        else:
            out[column] = out[column].map(json_safe_scalar)
            if out[column].dtype == object:
                out[column] = out[column].map(
                    lambda value: None if value is None else str(value)
                )
    return out


def relationship_id(record: dict[str, object]) -> str:
    key = "|".join(
        normalize(record.get(field))
        for field in ("paper_id", "subject_id", "object_id", "relation_type", "domain")
    )
    return f"relationship:{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"


def validate_public_tables(tables: dict[str, pd.DataFrame]) -> None:
    keys = {
        "papers": ["paper_id"],
        "concepts": ["concept_id"],
        "authors": ["author_id"],
        "paper_authors": ["paper_id", "author_id", "author_position"],
        "relationships": ["relationship_id"],
    }
    for table_name, key_fields in keys.items():
        frame = tables[table_name]
        if frame[key_fields].isna().any().any():
            raise ValueError(f"Public {table_name} contains a null key")
        if frame.duplicated(key_fields).any():
            raise ValueError(f"Public {table_name} contains duplicate keys")
        undocumented = set(frame.columns) - set(FIELD_DESCRIPTIONS)
        if undocumented:
            raise ValueError(
                f"Public {table_name} has undocumented fields: {sorted(undocumented)}"
            )
        for field in REQUIRED_NONEMPTY_FIELDS[table_name]:
            missing = frame[field].isna() | frame[field].astype(str).str.strip().eq("")
            if missing.any():
                raise ValueError(
                    f"Public {table_name}.{field} contains {int(missing.sum())} empty values"
                )

    paper_ids = set(tables["papers"]["paper_id"])
    concept_ids = set(tables["concepts"]["concept_id"])
    author_ids = set(tables["authors"]["author_id"])
    if set(tables["paper_authors"]["paper_id"]) - paper_ids:
        raise ValueError("Public paper_authors contains unknown paper IDs")
    if set(tables["paper_authors"]["author_id"]) - author_ids:
        raise ValueError("Public paper_authors contains unknown author IDs")
    if set(tables["relationships"]["paper_id"]) - paper_ids:
        raise ValueError("Public relationships contains unknown paper IDs")
    related_concepts = set(tables["relationships"]["subject_id"]) | set(
        tables["relationships"]["object_id"]
    )
    if related_concepts - concept_ids:
        raise ValueError("Public relationships contains unknown concept IDs")
    parent_ids = set(tables["concepts"]["parent_concept_id"].dropna()) - {""}
    if parent_ids - concept_ids:
        raise ValueError("Public concepts contains unknown parent concept IDs")

    classified_papers = tables["papers"].dropna(subset=["paper_type"])
    if set(classified_papers["paper_type"]) - PUBLIC_PAPER_TYPES:
        raise ValueError("Public papers contains unsupported paper types")
    if set(classified_papers["paper_subtype"]) - PUBLIC_PAPER_SUBTYPES:
        raise ValueError("Public papers contains unsupported paper subtypes")


def build_public_tables(kg_dir: Path) -> dict[str, pd.DataFrame]:
    required = {
        "entities": kg_dir / "entities.parquet",
        "papers": kg_dir / "papers.parquet",
        "evidence_edges": kg_dir / "evidence_edges.parquet",
        "findings": kg_dir / "findings.parquet",
        "authors": kg_dir / "authors.parquet",
        "paper_authors": kg_dir / "paper_authors.parquet",
    }
    for name, path in required.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name} table: {path}")

    classifications = paper_classifications(kg_dir)

    papers = selected_columns(
        pd.read_parquet(required["papers"]),
        PUBLIC_PAPER_SOURCE_FIELDS,
        table_name="papers",
    )
    papers["paper_type"] = papers["paper_id"].map(
        lambda value: classifications.get(normalize(value), (None, None))[0]
    )
    papers["paper_subtype"] = papers["paper_id"].map(
        lambda value: classifications.get(normalize(value), (None, None))[1]
    )
    papers = papers.drop(columns=["authors"])

    raw_edges = selected_columns(
        pd.read_parquet(required["evidence_edges"]),
        PUBLIC_RELATIONSHIP_SOURCE_FIELDS,
        table_name="evidence_edges",
    )
    raw_edges = raw_edges[raw_edges["graph_admission_status"] == "main_graph"].copy()
    relationships = raw_edges.rename(
        columns={
            "compound_id": "subject_id",
            "compound": "subject_label",
            "graph_subject_kind": "subject_kind",
            "entity_id": "object_id",
            "entity_label": "object_label",
            "entity_kind": "object_kind",
        }
    )
    relationship_fields = [
        "paper_id",
        "subject_id",
        "subject_label",
        "subject_kind",
        "object_id",
        "object_label",
        "object_kind",
        "domain",
        "relation_type",
    ]
    relationships = relationships[relationship_fields].drop_duplicates(
        ["paper_id", "subject_id", "object_id", "relation_type", "domain"]
    )
    relationships.insert(
        0,
        "relationship_id",
        [relationship_id(record) for record in relationships.to_dict(orient="records")],
    )
    relationships["paper_type"] = relationships["paper_id"].map(
        lambda value: classifications.get(normalize(value), (None, None))[0]
    )
    relationships["paper_subtype"] = relationships["paper_id"].map(
        lambda value: classifications.get(normalize(value), (None, None))[1]
    )

    entities = selected_columns(
        pd.read_parquet(required["entities"]),
        PUBLIC_CONCEPT_SOURCE_FIELDS,
        table_name="entities",
    ).rename(
        columns={
            "entity_id": "concept_id",
            "entity_type": "concept_type",
            "entity_kind": "concept_kind",
            "graph_parent_label": "parent_label",
            "graph_parent_kind": "parent_kind",
            "graph_parent_entity_id": "parent_concept_id",
            "ids_json": "external_ids_json",
        }
    )
    used_concepts = set(relationships["subject_id"]) | set(relationships["object_id"])
    parent_ids = set(
        entities.loc[entities["concept_id"].isin(used_concepts), "parent_concept_id"]
        .dropna()
        .astype(str)
    ) - {""}
    concepts = entities[entities["concept_id"].isin(used_concepts | parent_ids)].copy()

    source_paper_authors = selected_columns(
        pd.read_parquet(required["paper_authors"]),
        PUBLIC_PAPER_AUTHOR_FIELDS,
        table_name="paper_authors",
    )
    structured_authorship = source_paper_authors["author_id"].fillna("").astype(str).str.startswith(
        ("openalex:", "orcid:")
    )
    structured_authorship &= source_paper_authors["identity_confidence"].ne(
        "openalex_author_id_orcid_conflict"
    )
    structured_rate = (
        float(structured_authorship.mean()) if len(source_paper_authors) else 0.0
    )
    if structured_rate < MIN_STRUCTURED_AUTHORSHIP_RATE:
        raise ValueError(
            "Structured author identity coverage is "
            f"{structured_rate:.1%}; at least {MIN_STRUCTURED_AUTHORSHIP_RATE:.0%} is required. "
            "Refusing to publish unresolved or conflicting author identities. Seed or "
            "refresh the OpenAlex author cache, review identity conflicts, and rebuild "
            "author tables."
        )

    paper_authors = source_paper_authors[structured_authorship].copy().rename(
        columns={"display_name": "author_name", "canonical_name": "normalized_name"}
    )
    paper_authors = paper_authors.drop(columns=["identity_confidence"])
    paper_authors = paper_authors[paper_authors["paper_id"].isin(set(papers["paper_id"]))]
    paper_authors = paper_authors.drop_duplicates(
        ["paper_id", "author_id", "author_position"]
    )

    source_authors = selected_columns(
        pd.read_parquet(required["authors"]),
        PUBLIC_AUTHOR_FIELDS,
        table_name="authors",
    ).rename(
        columns={
            "display_name": "author_name",
            "canonical_name": "normalized_name",
            "identity_confidence": "identity_source",
            "display_names_json": "name_variants_json",
            "openalex_author_ids_json": "openalex_profile_ids_json",
        }
    )
    source_authors = source_authors[
        source_authors["author_id"].fillna("").astype(str).str.startswith(
            ("openalex:", "orcid:")
        )
    ].copy()
    author_counts = paper_authors.groupby("author_id")["paper_id"].nunique()
    source_authors["paper_count"] = source_authors["author_id"].map(author_counts).fillna(0)
    authors = source_authors[source_authors["paper_count"] > 0].copy()

    tables = {
        "papers": normalize_public_frame(papers),
        "concepts": normalize_public_frame(concepts),
        "authors": normalize_public_frame(authors),
        "paper_authors": normalize_public_frame(paper_authors),
        "relationships": normalize_public_frame(relationships),
    }
    tables["paper_authors"].attrs["source_authorship_rows"] = int(
        len(source_paper_authors)
    )
    tables["paper_authors"].attrs["structured_authorship_rate"] = structured_rate
    validate_public_tables(tables)
    return tables


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def table_schema(con: duckdb.DuckDBPyConnection, table_name: str) -> list[dict]:
    rows = con.execute(f"DESCRIBE {quote_identifier(table_name)}").fetchall()
    return [
        {
            "name": row[0],
            "type": row[1],
            "nullable": str(row[2]).upper() != "NO",
            **({"description": FIELD_DESCRIPTIONS[row[0]]} if row[0] in FIELD_DESCRIPTIONS else {}),
        }
        for row in rows
    ]


def materialize_query_artifacts(
    *,
    kg_dir: Path,
    out_dir: Path,
    run_id: str | None = None,
    generated_at: str | None = None,
) -> dict:
    kg_dir = kg_dir.resolve()
    out_dir = out_dir.resolve()
    kg_manifest_path = kg_dir / "manifest.json"
    kg_manifest = read_json_object(kg_manifest_path) if kg_manifest_path.is_file() else {}
    run_id = normalize(run_id or kg_manifest.get("run_id") or kg_dir.name)
    if not run_id:
        raise ValueError("A non-empty run_id is required for query runtime artifacts")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(prefix=f".{out_dir.name}.query-build.", dir=out_dir.parent)
    )
    try:
        tables = build_public_tables(kg_dir)

        db_path = stage_dir / PUBLIC_DB_NAME
        con = duckdb.connect(str(db_path))
        try:
            for table_name, frame in tables.items():
                source_name = f"_source_{table_name}"
                con.register(source_name, frame)
                try:
                    con.execute(
                        f"CREATE TABLE {quote_identifier(table_name)} AS "
                        f"SELECT * FROM {quote_identifier(source_name)}"
                    )
                finally:
                    con.unregister(source_name)
            con.execute("CHECKPOINT")
            schemas = {
                table_name: {
                    **TABLE_METADATA[table_name],
                    "row_count": int(
                        con.execute(
                            f"SELECT count(*) FROM {quote_identifier(table_name)}"
                        ).fetchone()[0]
                    ),
                    "fields": table_schema(con, table_name),
                }
                for table_name in tables
            }
        finally:
            con.close()

        generated_at = generated_at or now_utc()
        schema_payload = {
            "schema_version": PUBLIC_QUERY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "run_id": run_id,
            "tables": schemas,
            "semantics": {
                "paper_type": ["primary_study", "meta_analysis", "review"],
                "relationship_scope": (
                    "Relationships are deduplicated at paper-subject-object-relation-domain "
                    "grain and include only relationships admitted to the public graph."
                ),
                "author_identity": (
                    "Public author records require an OpenAlex or ORCID identity. ORCID is "
                    "canonical when available, including across OpenAlex profiles carrying "
                    "the same ORCID. OpenAlex profiles without ORCID remain separate unless "
                    "a reviewed correction links them. Name-only authorship rows and profiles "
                    "with conflicting ORCID evidence are excluded."
                ),
                "excluded_data": [
                    "granular findings",
                    "effect estimates and statistical fields",
                    "supporting quotes",
                    "result direction and confidence",
                    "internal curation and review fields",
                    "unresolved name-only author records",
                    "author profiles with conflicting ORCID evidence",
                ],
            },
        }
        schema_path = stage_dir / PUBLIC_SCHEMA_NAME
        write_json(schema_path, schema_payload)

        files: dict[str, dict] = {}
        for logical_name, path in {"database": db_path, "schema": schema_path}.items():
            files[logical_name] = {
                "path": path.relative_to(stage_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }

        manifest = {
            "schema_version": PUBLIC_QUERY_MANIFEST_VERSION,
            "public_schema_version": PUBLIC_QUERY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "run_id": run_id,
            "release_id": "",
            "evidence_release_id": "",
            "kg_dir": root_relative_or_absolute(kg_dir),
            "source_kg_table_version": normalize(kg_manifest.get("kg_table_version")),
            "database": PUBLIC_DB_NAME,
            "schema": PUBLIC_SCHEMA_NAME,
            "row_counts": {name: int(len(frame)) for name, frame in tables.items()},
            "files": files,
            "quality": {
                "contract": "narrow_public_catalogue",
                "query_only": True,
                "bulk_artifacts_excluded": True,
                "all_fields_documented": True,
                "relationships_deduplicated": True,
                "granular_findings_excluded": True,
                "name_only_authors_excluded": True,
                "conflicting_orcid_profiles_excluded": True,
                "minimum_structured_authorship_rate": MIN_STRUCTURED_AUTHORSHIP_RATE,
                "structured_authorship_rate": tables["paper_authors"].attrs[
                    "structured_authorship_rate"
                ],
                "source_authorship_rows": tables["paper_authors"].attrs[
                    "source_authorship_rows"
                ],
                "published_authorship_rows": len(tables["paper_authors"]),
                "validated_tables": list(tables),
            },
            "license": {
                "project_created_structured_data": "CC0-1.0",
                "source_material_boundary": (
                    "Third-party reports and bibliographic provider data retain their "
                    "original rights and terms. The public catalogue contains no source quotes."
                ),
                "project_license_file": "DATA_LICENSE.md",
            },
        }
        write_json(stage_dir / PUBLIC_MANIFEST_NAME, manifest)

        backup_dir = out_dir.with_name(f".{out_dir.name}.previous")
        shutil.rmtree(backup_dir, ignore_errors=True)
        if out_dir.exists():
            out_dir.rename(backup_dir)
        try:
            os.replace(stage_dir, out_dir)
        except BaseException:
            if backup_dir.exists() and not out_dir.exists():
                backup_dir.rename(out_dir)
            raise
        shutil.rmtree(backup_dir, ignore_errors=True)
        return manifest
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def validate_query_artifact(*, kg_dir: Path, out_dir: Path, run_id: str) -> dict:
    manifest_path = out_dir / PUBLIC_MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query runtime manifest: {manifest_path}")
    manifest = read_json_object(manifest_path)
    if normalize(manifest.get("schema_version")) != PUBLIC_QUERY_MANIFEST_VERSION:
        raise ValueError(f"Unexpected query runtime manifest schema: {manifest_path}")
    if normalize(manifest.get("run_id")) != normalize(run_id):
        raise ValueError(f"Public query artifact run_id does not match {run_id}: {manifest_path}")
    if Path(normalize(manifest.get("kg_dir"))).name != kg_dir.name:
        raise ValueError(f"Public query artifact points at a different KG: {manifest_path}")
    db_path = out_dir / normalize(manifest.get("database"))
    schema_path = out_dir / normalize(manifest.get("schema"))
    if not db_path.is_file() or not schema_path.is_file():
        raise FileNotFoundError(f"Public query artifact is incomplete: {out_dir}")
    files = manifest.get("files") or {}
    if set(files) != {"database", "schema"}:
        raise ValueError(
            f"Query artifacts must not contain bulk release files: {sorted(files)}"
        )
    if (out_dir / "tables").exists():
        raise ValueError(f"Query artifact contains a bulk tables directory: {out_dir}")
    expected_tables = set(TABLE_METADATA)
    public_counts = manifest.get("row_counts") or {}
    if set(public_counts) != expected_tables:
        raise ValueError(
            f"Unexpected public tables for {run_id}: {sorted(public_counts)}"
        )
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        actual_tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if actual_tables != expected_tables:
            raise ValueError(
                f"Public database table mismatch for {run_id}: {sorted(actual_tables)}"
            )
        for table_name, expected_count in public_counts.items():
            actual_count = int(
                con.execute(
                    f"SELECT count(*) FROM {quote_identifier(table_name)}"
                ).fetchone()[0]
            )
            if actual_count != int(expected_count):
                raise ValueError(
                    f"Public {table_name} row-count mismatch for {run_id}: "
                    f"manifest={expected_count}, database={actual_count}"
                )
    finally:
        con.close()
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    kg_dir = args.kg_dir.resolve()
    run_id = normalize(args.run_id or kg_dir.name)
    out_dir = (
        args.out_dir.resolve()
        if args.out_dir is not None
        else (DEFAULT_OUT_ROOT / run_id).resolve()
    )
    if args.check:
        manifest = validate_query_artifact(kg_dir=kg_dir, out_dir=out_dir, run_id=run_id)
        print(f"Public query artifact is complete: {manifest['run_id']}")
        return 0
    manifest = materialize_query_artifacts(
        kg_dir=kg_dir,
        out_dir=out_dir,
        run_id=run_id,
    )
    print(f"Built query runtime artifacts: {out_dir}")
    print(f"Public papers: {manifest['row_counts']['papers']}")
    print(f"Public relationships: {manifest['row_counts']['relationships']}")
    print(f"Public database: {out_dir / PUBLIC_DB_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
