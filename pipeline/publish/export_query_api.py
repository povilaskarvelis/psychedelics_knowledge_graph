#!/usr/bin/env python3
"""Build sanitized, versioned query artifacts for REST, MCP, and bulk access.

The normalized KG tables contain internal columns that must not be exposed as a
public database.  This exporter reuses the browser payload's public finding
projection, adds stable join identifiers, and writes a compact DuckDB database
plus Parquet tables.  Outputs are versioned by routed run and are built before
that run can be promoted.
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
        DETAIL_BOOTSTRAP_FIELDS,
        load_findings,
        ui_source_key_for_finding,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    import sys

    ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT_FOR_IMPORT))
    from pipeline.publish.export_evidence_payload import (
        DETAIL_BOOTSTRAP_FIELDS,
        load_findings,
        ui_source_key_for_finding,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KG_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_OUT_ROOT = ROOT / "data" / "processed" / "query_api_runs"

PUBLIC_QUERY_SCHEMA_VERSION = "psychedelics_kg_public_query_v1"
PUBLIC_QUERY_MANIFEST_VERSION = "psychedelics_kg_public_query_manifest_v1"
PUBLIC_DB_NAME = "public_api.duckdb"
PUBLIC_SCHEMA_NAME = "schema.json"
PUBLIC_MANIFEST_NAME = "manifest.json"
PUBLIC_TABLE_DIR = "tables"

PUBLIC_FINDING_FIELDS = tuple(
    dict.fromkeys(
        (
            "finding_id",
            "evidence_id",
            "paper_id",
            "entity_id",
            "compound_id",
            "projection_type",
            "literature_source",
            "direction_normalized",
            *DETAIL_BOOTSTRAP_FIELDS,
        )
    )
)

PUBLIC_EDGE_FIELDS = (
    "evidence_id",
    "finding_id",
    "projection_type",
    "source_name",
    "domain",
    "dataset",
    "entity_kind",
    "evidence_type",
    "relation_type",
    "compound_id",
    "compound",
    "graph_subject_kind",
    "graph_overview_subject_label",
    "graph_overview_subject_kind",
    "graph_overview_subject_reason",
    "graph_overview_subjects_json",
    "graph_use_context_projections_json",
    "entity_id",
    "entity_label",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
    "paper_id",
    "study_doi",
    "study_year",
    "direction",
    "direction_normalized",
    "evidence_design",
    "graph_admission_status",
    "graph_admission_reason",
    "proposition_group_id",
    "proposition_conflict_group_id",
    "support",
    "confidence",
    "evidence_level",
    "source_type",
    "source_family",
    "paper_type",
    "access_level",
    "sample_size_total",
    "outcome_measure",
    "outcome_measure_normalized",
    "effect_size",
    "p_value",
    "confidence_interval",
    "evidence_location",
    "evidence_locator",
    "supporting_quote",
    "proposition_duplicate_count",
    "direction_consistency",
    "literature_source",
)

PUBLIC_ENTITY_FIELDS = (
    "entity_id",
    "entity_type",
    "domain",
    "entity_kind",
    "label",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
    "registry_status",
    "aliases_json",
    "ids_json",
)

PUBLIC_PAPER_FIELDS = (
    "paper_id",
    "doi",
    "openalex_id",
    "title",
    "authors",
    "year",
    "journal",
    "study_doi",
    "study_title",
    "study_year",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "trial_registry_ids",
    "study_design",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "source_access_level",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)

PUBLIC_AUTHOR_FIELDS = (
    "author_id",
    "display_name",
    "canonical_name",
    "openalex_author_id",
    "orcid",
    "source",
    "identity_confidence",
    "display_names_json",
    "paper_count",
    "authorship_count",
    "first_author_paper_count",
    "last_author_paper_count",
)

PUBLIC_PAPER_AUTHOR_FIELDS = (
    "paper_id",
    "doi",
    "paper_openalex_id",
    "author_id",
    "display_name",
    "canonical_name",
    "openalex_author_id",
    "orcid",
    "author_position",
    "author_position_label",
    "is_first_author",
    "is_last_author",
    "source",
    "identity_confidence",
)

FORBIDDEN_PUBLIC_COLUMNS = {
    "raw_row_json",
    "normalization_notes",
    "extraction_warnings",
    "needs_human_review",
}

NUMERIC_FINDING_FIELDS = {
    "study_year",
    "meta_analysis_study_count",
    "meta_analysis_effect_or_experiment_count",
    "meta_analysis_dataset_or_comparison_count",
    "meta_analysis_overall_study_count",
    "meta_analysis_overall_effect_or_experiment_count",
    "meta_analysis_overall_dataset_or_comparison_count",
    "proposition_duplicate_count",
}

FIELD_DESCRIPTIONS = {
    "finding_id": "Release-scoped identifier for one normalized finding.",
    "evidence_id": "Identifier for the graph evidence projection associated with a finding.",
    "paper_id": "Canonical report identifier, normally DOI-based when a DOI is available.",
    "entity_id": "Canonical identifier for the finding object entity.",
    "compound_id": "Canonical identifier for the graph subject compound or exposure.",
    "literature_source": "One of primary, meta_analyses, or reviews; these layers should not be conflated.",
    "graph_admission_status": "Whether the finding is admitted to the overview graph or retained as paper detail.",
    "graph_admission_reason": "Reason for the overview/detail admission decision.",
    "result_direction_normalized": "Normalized positive, negative, null, mixed, or uncertain result direction when available.",
    "text_depth": "Whether extraction used article text or abstract-only evidence.",
    "supporting_quote": "Short third-party source excerpt retained for provenance; not relicensed as CC0.",
    "evidence_locator": "Location of the supporting evidence in the source report.",
    "proposition_group_id": "Identifier grouping duplicate expressions of the same normalized proposition.",
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


def normalize_finding_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.columns:
        if column in NUMERIC_FINDING_FIELDS:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
            continue
        if column in {"open_access_is_oa", "unpaywall_is_oa"}:
            df[column] = df[column].astype("boolean")
            continue
        df[column] = df[column].map(json_safe_scalar)
        if df[column].dtype == object:
            df[column] = df[column].map(lambda value: None if value is None else str(value))
    return df


def outcome_edge_lookup(edges: pd.DataFrame) -> dict[str, dict]:
    base = edges.copy()
    if "projection_type" in base.columns:
        base = base[base["projection_type"].fillna("outcome") != "use_context"]
    keep = [
        column
        for column in (
            "finding_id",
            "evidence_id",
            "entity_id",
            "compound_id",
            "projection_type",
            "direction_normalized",
        )
        if column in base.columns
    ]
    if "finding_id" not in keep:
        return {}
    base = base[keep].drop_duplicates("finding_id", keep="first")
    return {
        normalize(record.get("finding_id")): record
        for record in base.to_dict(orient="records")
        if normalize(record.get("finding_id"))
    }


def build_public_findings(kg_dir: Path, edges: pd.DataFrame) -> pd.DataFrame:
    edge_by_finding = outcome_edge_lookup(edges)
    records: list[dict] = []
    for finding in load_findings(kg_dir):
        finding_id = normalize(finding.get("finding_id"))
        edge = edge_by_finding.get(finding_id, {})
        record = {field: finding.get(field) for field in PUBLIC_FINDING_FIELDS}
        record.update(
            {
                "finding_id": finding_id,
                "evidence_id": normalize(finding.get("evidence_id") or edge.get("evidence_id")),
                "paper_id": normalize(finding.get("paper_id")),
                "entity_id": normalize(edge.get("entity_id")),
                "compound_id": normalize(edge.get("compound_id")),
                "projection_type": normalize(edge.get("projection_type")) or "outcome",
                "literature_source": ui_source_key_for_finding(finding),
                "direction_normalized": normalize(edge.get("direction_normalized")),
            }
        )
        records.append(record)
    return normalize_finding_dataframe_types(
        pd.DataFrame.from_records(records, columns=PUBLIC_FINDING_FIELDS)
    )


def selected_columns(df: pd.DataFrame, fields: Iterable[str], *, table_name: str) -> pd.DataFrame:
    fields = tuple(fields)
    columns = [field for field in fields if field in df.columns]
    missing_required = {
        "entities": {"entity_id", "label"},
        "papers": {"paper_id"},
        "evidence_edges": {"evidence_id", "finding_id", "paper_id"},
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
    forbidden = FORBIDDEN_PUBLIC_COLUMNS & set(selected.columns)
    if forbidden:
        raise ValueError(f"Refusing to publish forbidden {table_name} columns: {sorted(forbidden)}")
    return selected


def build_public_tables(kg_dir: Path) -> dict[str, pd.DataFrame]:
    required = {
        "entities": kg_dir / "entities.parquet",
        "papers": kg_dir / "papers.parquet",
        "evidence_edges": kg_dir / "evidence_edges.parquet",
        "findings": kg_dir / "findings.parquet",
    }
    for name, path in required.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name} table: {path}")

    raw_edges = pd.read_parquet(required["evidence_edges"])
    findings = build_public_findings(kg_dir, raw_edges)
    source_by_finding = dict(
        zip(findings["finding_id"], findings["literature_source"], strict=False)
    )

    edges = selected_columns(raw_edges, PUBLIC_EDGE_FIELDS, table_name="evidence_edges")
    edges["literature_source"] = edges["finding_id"].map(source_by_finding).fillna("primary")
    ordered_edge_fields = [field for field in PUBLIC_EDGE_FIELDS if field in edges.columns]
    edges = edges[ordered_edge_fields]

    tables = {
        "findings": findings,
        "evidence_edges": edges,
        "entities": selected_columns(
            pd.read_parquet(required["entities"]),
            PUBLIC_ENTITY_FIELDS,
            table_name="entities",
        ),
        "papers": selected_columns(
            pd.read_parquet(required["papers"]),
            PUBLIC_PAPER_FIELDS,
            table_name="papers",
        ),
    }

    optional = {
        "authors": (kg_dir / "authors.parquet", PUBLIC_AUTHOR_FIELDS),
        "paper_authors": (kg_dir / "paper_authors.parquet", PUBLIC_PAPER_AUTHOR_FIELDS),
    }
    for table_name, (path, fields) in optional.items():
        if path.is_file():
            tables[table_name] = selected_columns(
                pd.read_parquet(path), fields, table_name=table_name
            )
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
        raise ValueError("A non-empty run_id is required for public query artifacts")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(prefix=f".{out_dir.name}.query-build.", dir=out_dir.parent)
    )
    try:
        table_dir = stage_dir / PUBLIC_TABLE_DIR
        table_dir.mkdir(parents=True)
        tables = build_public_tables(kg_dir)
        table_paths: dict[str, Path] = {}
        for table_name, frame in tables.items():
            path = table_dir / f"{table_name}.parquet"
            frame.to_parquet(path, index=False)
            table_paths[table_name] = path

        db_path = stage_dir / PUBLIC_DB_NAME
        con = duckdb.connect(str(db_path))
        try:
            for table_name, path in table_paths.items():
                con.execute(
                    f"CREATE TABLE {quote_identifier(table_name)} AS SELECT * FROM read_parquet(?)",
                    [path.as_posix()],
                )
            con.execute("CHECKPOINT")
            schemas = {
                table_name: {
                    "row_count": int(
                        con.execute(
                            f"SELECT count(*) FROM {quote_identifier(table_name)}"
                        ).fetchone()[0]
                    ),
                    "fields": table_schema(con, table_name),
                }
                for table_name in table_paths
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
                "literature_source": ["primary", "meta_analyses", "reviews"],
                "default_query_scope": "main_graph",
                "alternative_query_scope": "all_normalized",
                "counting_warning": "Finding rows are not independent studies; use distinct paper_id for study counts.",
                "finding_id_stability": "finding_id is release-scoped; paper and canonical entity IDs are more stable across releases.",
            },
        }
        schema_path = stage_dir / PUBLIC_SCHEMA_NAME
        write_json(schema_path, schema_payload)

        files: dict[str, dict] = {}
        for logical_name, path in {
            "database": db_path,
            "schema": schema_path,
            **{f"table:{name}": path for name, path in table_paths.items()},
        }.items():
            files[logical_name] = {
                "path": path.relative_to(stage_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }

        source_finding_count = int(
            ((kg_manifest.get("tables") or {}).get("findings") or {}).get(
                "rows", len(tables["findings"])
            )
        )
        if len(tables["findings"]) != source_finding_count:
            raise ValueError(
                "Public finding count does not match the normalized KG: "
                f"public={len(tables['findings'])}, kg={source_finding_count}"
            )

        manifest = {
            "schema_version": PUBLIC_QUERY_MANIFEST_VERSION,
            "public_schema_version": PUBLIC_QUERY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "run_id": run_id,
            "kg_dir": root_relative_or_absolute(kg_dir),
            "source_kg_table_version": normalize(kg_manifest.get("kg_table_version")),
            "database": PUBLIC_DB_NAME,
            "schema": PUBLIC_SCHEMA_NAME,
            "row_counts": {name: int(len(frame)) for name, frame in tables.items()},
            "files": files,
            "license": {
                "structured_data": "CC0-1.0",
                "source_material_boundary": (
                    "Third-party reports, bibliographic provider data, and supporting excerpts "
                    "retain their original rights and terms."
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
        raise FileNotFoundError(f"Missing public query manifest: {manifest_path}")
    manifest = read_json_object(manifest_path)
    if normalize(manifest.get("schema_version")) != PUBLIC_QUERY_MANIFEST_VERSION:
        raise ValueError(f"Unexpected public query manifest schema: {manifest_path}")
    if normalize(manifest.get("run_id")) != normalize(run_id):
        raise ValueError(f"Public query artifact run_id does not match {run_id}: {manifest_path}")
    if Path(normalize(manifest.get("kg_dir"))).name != kg_dir.name:
        raise ValueError(f"Public query artifact points at a different KG: {manifest_path}")
    db_path = out_dir / normalize(manifest.get("database"))
    schema_path = out_dir / normalize(manifest.get("schema"))
    if not db_path.is_file() or not schema_path.is_file():
        raise FileNotFoundError(f"Public query artifact is incomplete: {out_dir}")
    kg_manifest = read_json_object(kg_dir / "manifest.json")
    kg_rows = int(((kg_manifest.get("tables") or {}).get("findings") or {}).get("rows", -1))
    public_rows = int((manifest.get("row_counts") or {}).get("findings", -2))
    if kg_rows < 0 or public_rows != kg_rows:
        raise ValueError(
            f"Public query/KG row-count mismatch for {run_id}: public={public_rows}, kg={kg_rows}"
        )
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
    print(f"Built public query artifacts: {out_dir}")
    print(f"Public findings: {manifest['row_counts']['findings']}")
    print(f"Public database: {out_dir / PUBLIC_DB_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
