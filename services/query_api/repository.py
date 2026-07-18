from __future__ import annotations

import base64
import contextlib
import datetime as dt
import decimal
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import duckdb

from .config import Settings
from .models import AggregateQuery, FindingFilters, FindingQuery, NeighborQuery
from .r2_store import R2_RELEASE_SIDECAR_NAME, ObjectStore, R2ObjectStore


PUBLIC_DB_NAME = "public_api.duckdb"
PUBLIC_MANIFEST_NAME = "manifest.json"
PUBLIC_SCHEMA_NAME = "schema.json"
PUBLIC_QUERY_MANIFEST_VERSION = "psychedelics_kg_public_query_manifest_v1"


SUMMARY_FINDING_FIELDS = (
    "finding_id",
    "evidence_id",
    "paper_id",
    "entity_id",
    "compound_id",
    "literature_source",
    "domain",
    "evidence_type",
    "relation_type",
    "compound",
    "entity_label",
    "entity_kind",
    "study_doi",
    "study_title",
    "study_year",
    "study_journal",
    "result_direction_normalized",
    "text_depth",
    "graph_admission_status",
    "evidence_level",
    "support",
    "effect_size",
    "sample_size_total",
    "population",
    "comparator_normalized",
    "follow_up_window_normalized",
    "evidence_locator",
)

AGGREGATE_GROUP_FIELDS = {
    "compound",
    "compound_id",
    "entity_label",
    "entity_id",
    "entity_kind",
    "domain",
    "evidence_type",
    "literature_source",
    "relation_type",
    "result_direction_normalized",
    "study_year",
    "text_depth",
}

JSON_VALUE_FIELDS = {
    "aliases_json",
    "ids_json",
    "entity_aliases",
    "graph_parent_aliases",
    "first_author",
    "last_author",
    "graph_overview_subjects_json",
    "graph_use_context_projections_json",
}


class QueryArtifactUnavailable(RuntimeError):
    pass


class QueryNotFound(LookupError):
    pass


class InvalidQuery(ValueError):
    pass


class ReleaseChanged(InvalidQuery):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    run_id: str
    release_id: str
    generated_at: str
    db_path: Path
    manifest_path: Path
    schema_path: Path
    artifact_dir: Path
    row_counts: dict[str, int]
    manifest: dict[str, Any]


@dataclass(frozen=True)
class DownloadTarget:
    info: ReleaseInfo
    entry: dict[str, Any]
    path: Path | None = None
    url: str = ""


class ReleaseResolver:
    """Resolve every request through the graph's atomically promoted pointer."""

    def __init__(
        self,
        *,
        active_pointer: Path,
        query_runs_dir: Path,
    ) -> None:
        self.active_pointer = active_pointer.resolve()
        self.query_runs_dir = query_runs_dir.resolve()

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReleaseResolver":
        return cls(
            active_pointer=settings.active_pointer,
            query_runs_dir=settings.query_runs_dir,
        )

    def resolve(self) -> ReleaseInfo:
        try:
            pointer = json.loads(self.active_pointer.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise QueryArtifactUnavailable(
                f"Active graph pointer is missing: {self.active_pointer}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise QueryArtifactUnavailable(
                f"Active graph pointer is invalid JSON: {self.active_pointer}"
            ) from exc
        run_id = str(pointer.get("run_id") or "").strip()
        release_id = str(pointer.get("release_id") or "").strip()
        if not run_id or not release_id:
            raise QueryArtifactUnavailable(
                "Active graph pointer lacks run_id or release_id"
            )

        artifact_dir = self.query_runs_dir / run_id
        manifest_path = artifact_dir / PUBLIC_MANIFEST_NAME
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise QueryArtifactUnavailable(
                "The active release has no public query artifact. Rebuild the routed KG "
                f"or run export_query_api.py for {run_id}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise QueryArtifactUnavailable(
                f"Public query manifest is invalid JSON: {manifest_path}"
            ) from exc
        if manifest.get("schema_version") != PUBLIC_QUERY_MANIFEST_VERSION:
            raise QueryArtifactUnavailable(
                f"Unsupported public query manifest schema: {manifest.get('schema_version')}"
            )
        if manifest.get("run_id") != run_id:
            raise QueryArtifactUnavailable(
                f"Active release/query artifact mismatch: {run_id} vs {manifest.get('run_id')}"
            )
        db_path = artifact_dir / str(manifest.get("database") or PUBLIC_DB_NAME)
        schema_path = artifact_dir / str(manifest.get("schema") or PUBLIC_SCHEMA_NAME)
        if not db_path.is_file() or not schema_path.is_file():
            raise QueryArtifactUnavailable(
                f"Public query artifact is incomplete: {artifact_dir}"
            )
        return ReleaseInfo(
            run_id=run_id,
            release_id=release_id,
            generated_at=str(manifest.get("generated_at") or ""),
            db_path=db_path,
            manifest_path=manifest_path,
            schema_path=schema_path,
            artifact_dir=artifact_dir,
            row_counts={
                str(key): int(value)
                for key, value in (manifest.get("row_counts") or {}).items()
            },
            manifest=manifest,
        )


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def decode_row(columns: Sequence[str], values: Sequence[Any]) -> dict[str, Any]:
    row = {
        column: json_value(value) for column, value in zip(columns, values, strict=True)
    }
    for field in JSON_VALUE_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            row[field] = json.loads(value)
        except json.JSONDecodeError:
            pass
    return row


def fetch_rows(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [decode_row(columns, row) for row in cursor.fetchall()]


def encode_cursor(*, release_id: str, offset: int) -> str:
    payload = json.dumps(
        {"release_id": release_id, "offset": offset},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str | None, *, release_id: str) -> int:
    if not value:
        return 0
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        offset = int(payload["offset"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise InvalidQuery("Invalid pagination cursor") from exc
    if payload.get("release_id") != release_id:
        raise ReleaseChanged(
            "This cursor belongs to a different data release; restart pagination on the current release."
        )
    if offset < 0:
        raise InvalidQuery("Invalid pagination cursor offset")
    return offset


class QueryService:
    def __init__(
        self,
        resolver: ReleaseResolver,
        *,
        public_base_url: str = "",
        remote_store: ObjectStore | None = None,
    ) -> None:
        self.resolver = resolver
        self.public_base_url = public_base_url.rstrip("/")
        self.remote_store = remote_store

    @classmethod
    def from_settings(cls, settings: Settings) -> "QueryService":
        return cls(
            ReleaseResolver.from_settings(settings),
            public_base_url=settings.public_base_url,
            remote_store=R2ObjectStore(settings.r2)
            if settings.r2 is not None
            else None,
        )

    @contextlib.contextmanager
    def connection(self, info: ReleaseInfo) -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(info.db_path), read_only=True)
        try:
            yield con
        finally:
            con.close()

    @staticmethod
    def release_meta(info: ReleaseInfo) -> dict[str, Any]:
        return {
            "release_id": info.release_id,
            "run_id": info.run_id,
            "generated_at": info.generated_at,
        }

    def meta(self) -> dict[str, Any]:
        info = self.resolver.resolve()
        return {
            "api_version": "v1",
            **self.release_meta(info),
            "row_counts": info.row_counts,
            "default_scope": "main_graph",
            "available_scopes": ["main_graph", "all_normalized"],
            "literature_sources": ["primary", "meta_analyses", "reviews"],
            "id_stability": {
                "finding_id": "release_scoped",
                "paper_id": "stable_when_doi_or_openalex_id_is_stable",
                "entity_id": "stable_until_canonical_label_changes",
            },
            "counting_warning": (
                "Finding rows are not independent studies. Use study_count, which counts distinct paper_id."
            ),
            "links": {
                "openapi": f"{self.public_base_url}/openapi.json"
                if self.public_base_url
                else "/openapi.json",
                "docs": f"{self.public_base_url}/docs"
                if self.public_base_url
                else "/docs",
                "mcp": f"{self.public_base_url}/mcp"
                if self.public_base_url
                else "/mcp",
            },
        }

    def schema(self) -> dict[str, Any]:
        info = self.resolver.resolve()
        return json.loads(info.schema_path.read_text(encoding="utf-8"))

    def health(self) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            con.execute("SELECT 1").fetchone()
        return {"status": "ok", **self.release_meta(info)}

    def table_columns(self, con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
        return [
            row[0]
            for row in con.execute(f"DESCRIBE {quote_identifier(table)}").fetchall()
        ]

    @staticmethod
    def add_in_filter(
        clauses: list[str],
        params: list[Any],
        *,
        expression: str,
        values: Sequence[str],
        casefold: bool = False,
    ) -> None:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            return
        placeholders = ",".join("?" for _ in cleaned)
        if casefold:
            clauses.append(f"lower({expression}) IN ({placeholders})")
            params.extend(value.casefold() for value in cleaned)
        else:
            clauses.append(f"{expression} IN ({placeholders})")
            params.extend(cleaned)

    def finding_where(
        self, filters: FindingFilters, *, scope: str
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope == "main_graph":
            clauses.append("graph_admission_status = 'main_graph'")
        elif scope != "all_normalized":
            raise InvalidQuery(f"Unsupported query scope: {scope}")

        for expression, values, casefold in (
            ("compound_id", filters.compound_ids, False),
            ("compound", filters.compounds, True),
            ("entity_id", filters.entity_ids, False),
            ("entity_label", filters.entity_labels, True),
            ("entity_kind", filters.entity_kinds, True),
            ("domain", filters.domains, True),
            ("evidence_type", filters.evidence_types, True),
            ("literature_source", filters.literature_sources, False),
            ("relation_type", filters.relation_types, True),
            ("text_depth", filters.text_depth, True),
            ("paper_id", filters.paper_ids, False),
            ("study_doi", filters.study_dois, True),
        ):
            self.add_in_filter(
                clauses,
                params,
                expression=expression,
                values=values,
                casefold=casefold,
            )
        self.add_in_filter(
            clauses,
            params,
            expression="coalesce(nullif(result_direction_normalized, ''), direction_normalized)",
            values=filters.directions,
            casefold=True,
        )
        if filters.year_from is not None:
            clauses.append("try_cast(study_year AS INTEGER) >= ?")
            params.append(filters.year_from)
        if filters.year_to is not None:
            clauses.append("try_cast(study_year AS INTEGER) <= ?")
            params.append(filters.year_to)
        if filters.query:
            clauses.append(
                "lower(concat_ws(' ', compound, entity_label, study_title, study_doi, "
                "outcome_measure, population)) LIKE ?"
            )
            params.append(f"%{filters.query.casefold()}%")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def search_entities(
        self,
        query: str,
        *,
        entity_kinds: Sequence[str] = (),
        limit: int = 15,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise InvalidQuery("Entity search query must not be empty")
        limit = max(1, min(int(limit), 50))
        info = self.resolver.resolve()
        clauses = ["(lower(label) LIKE ? OR lower(coalesce(aliases_json, '')) LIKE ?)"]
        params: list[Any] = [f"%{query.casefold()}%", f"%{query.casefold()}%"]
        self.add_in_filter(
            clauses,
            params,
            expression="entity_kind",
            values=entity_kinds,
            casefold=True,
        )
        sql = f"""
            SELECT entity_id, entity_type, entity_kind, domain, label,
                   graph_parent_label, graph_parent_kind, graph_parent_entity_id,
                   registry_status, aliases_json, ids_json
            FROM entities
            WHERE {" AND ".join(clauses)}
            ORDER BY
              CASE
                WHEN lower(label) = ? THEN 0
                WHEN lower(label) LIKE ? THEN 1
                ELSE 2
              END,
              label
            LIMIT ?
        """
        params.extend([query.casefold(), f"{query.casefold()}%", limit])
        with self.connection(info) as con:
            results = fetch_rows(con.execute(sql, params))
        return {"meta": self.release_meta(info), "results": results}

    def get_entity(self, entity_id: str) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            rows = fetch_rows(
                con.execute("SELECT * FROM entities WHERE entity_id = ?", [entity_id])
            )
            if not rows:
                raise QueryNotFound(f"Unknown entity_id: {entity_id}")
            counts = fetch_rows(
                con.execute(
                    """
                    SELECT
                      count(DISTINCT CASE WHEN entity_id = ? THEN finding_id END) AS object_finding_count,
                      count(DISTINCT CASE WHEN compound_id = ? THEN finding_id END) AS subject_finding_count,
                      count(DISTINCT CASE WHEN entity_id = ? OR compound_id = ? THEN paper_id END) AS study_count
                    FROM evidence_edges
                    """,
                    [entity_id, entity_id, entity_id, entity_id],
                )
            )[0]
        return {"meta": self.release_meta(info), "data": {**rows[0], "counts": counts}}

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            rows = fetch_rows(
                con.execute("SELECT * FROM findings WHERE finding_id = ?", [finding_id])
            )
        if not rows:
            raise QueryNotFound(f"Unknown finding_id: {finding_id}")
        return {"meta": self.release_meta(info), "data": rows[0]}

    def get_paper(
        self,
        paper_id_or_doi: str,
        *,
        include_findings: bool = True,
        finding_limit: int = 50,
    ) -> dict[str, Any]:
        info = self.resolver.resolve()
        finding_limit = max(1, min(int(finding_limit), 100))
        normalized_doi = paper_id_or_doi.removeprefix("https://doi.org/").removeprefix(
            "doi:"
        )
        with self.connection(info) as con:
            papers = fetch_rows(
                con.execute(
                    """
                    SELECT * FROM papers
                    WHERE paper_id = ? OR lower(doi) = lower(?) OR lower(study_doi) = lower(?)
                    LIMIT 1
                    """,
                    [paper_id_or_doi, normalized_doi, normalized_doi],
                )
            )
            if not papers:
                raise QueryNotFound(f"Unknown paper identifier: {paper_id_or_doi}")
            paper = papers[0]
            findings: list[dict[str, Any]] = []
            if include_findings:
                fields = ", ".join(
                    quote_identifier(field) for field in SUMMARY_FINDING_FIELDS
                )
                findings = fetch_rows(
                    con.execute(
                        f"""
                        SELECT {fields} FROM findings
                        WHERE paper_id = ?
                        ORDER BY domain, entity_label, finding_id
                        LIMIT ?
                        """,
                        [paper["paper_id"], finding_limit],
                    )
                )
        return {
            "meta": self.release_meta(info),
            "data": paper,
            **({"findings": findings} if include_findings else {}),
        }

    def query_findings(self, request: FindingQuery) -> dict[str, Any]:
        info = self.resolver.resolve()
        offset = decode_cursor(request.cursor, release_id=info.release_id)
        where, params = self.finding_where(request.filters, scope=request.scope)
        with self.connection(info) as con:
            available = self.table_columns(con, "findings")
            if request.fields:
                unknown = set(request.fields) - set(available)
                if unknown:
                    raise InvalidQuery(
                        f"Unknown public finding fields: {sorted(unknown)}"
                    )
                selected = list(dict.fromkeys(["finding_id", *request.fields]))
            elif request.detail_level == "full":
                selected = available
            else:
                selected = [
                    field for field in SUMMARY_FINDING_FIELDS if field in available
                ]
            field_sql = ", ".join(quote_identifier(field) for field in selected)
            total = int(
                con.execute(f"SELECT count(*) FROM findings{where}", params).fetchone()[
                    0
                ]
            )
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT {field_sql}
                    FROM findings
                    {where}
                    ORDER BY try_cast(study_year AS INTEGER) DESC NULLS LAST, finding_id
                    LIMIT ? OFFSET ?
                    """,
                    [*params, request.limit, offset],
                )
            )
        next_offset = offset + len(results)
        return {
            "meta": {
                **self.release_meta(info),
                "scope": request.scope,
                "total": total,
                "returned": len(results),
                "next_cursor": (
                    encode_cursor(release_id=info.release_id, offset=next_offset)
                    if next_offset < total
                    else None
                ),
            },
            "results": results,
        }

    def aggregate(self, request: AggregateQuery) -> dict[str, Any]:
        unknown = set(request.group_by) - AGGREGATE_GROUP_FIELDS
        if unknown:
            raise InvalidQuery(f"Unsupported aggregate fields: {sorted(unknown)}")
        info = self.resolver.resolve()
        where, params = self.finding_where(request.filters, scope=request.scope)
        fields = list(dict.fromkeys(request.group_by))
        field_sql = ", ".join(quote_identifier(field) for field in fields)
        with self.connection(info) as con:
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT {field_sql},
                           count(*) AS finding_count,
                           count(DISTINCT paper_id) AS study_count,
                           count(DISTINCT nullif(proposition_group_id, '')) AS proposition_count
                    FROM findings
                    {where}
                    GROUP BY {field_sql}
                    ORDER BY study_count DESC, finding_count DESC, {field_sql}
                    LIMIT ?
                    """,
                    [*params, request.limit],
                )
            )
        return {
            "meta": {
                **self.release_meta(info),
                "scope": request.scope,
                "group_by": fields,
                "returned": len(results),
            },
            "results": results,
        }

    def neighbors(self, entity_id: str, request: NeighborQuery) -> dict[str, Any]:
        info = self.resolver.resolve()
        clauses = ["(compound_id = ? OR entity_id = ?)"]
        params: list[Any] = [entity_id, entity_id]
        if request.scope == "main_graph":
            clauses.append("graph_admission_status = 'main_graph'")
        elif request.scope != "all_normalized":
            raise InvalidQuery(f"Unsupported query scope: {request.scope}")
        self.add_in_filter(
            clauses,
            params,
            expression="literature_source",
            values=request.literature_sources,
        )
        self.add_in_filter(
            clauses,
            params,
            expression="relation_type",
            values=request.relation_types,
            casefold=True,
        )
        with self.connection(info) as con:
            entity_exists = con.execute(
                "SELECT 1 FROM entities WHERE entity_id = ?", [entity_id]
            ).fetchone()
            if entity_exists is None:
                raise QueryNotFound(f"Unknown entity_id: {entity_id}")
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT compound_id, compound, graph_subject_kind,
                           entity_id, entity_label, entity_kind,
                           relation_type, domain, literature_source,
                           count(DISTINCT paper_id) AS study_count,
                           count(DISTINCT finding_id) AS finding_count
                    FROM evidence_edges
                    WHERE {" AND ".join(clauses)}
                    GROUP BY compound_id, compound, graph_subject_kind,
                             entity_id, entity_label, entity_kind,
                             relation_type, domain, literature_source
                    ORDER BY study_count DESC, finding_count DESC, compound, entity_label
                    LIMIT ?
                    """,
                    [*params, request.limit],
                )
            )
        return {
            "meta": {
                **self.release_meta(info),
                "scope": request.scope,
                "entity_id": entity_id,
                "returned": len(results),
            },
            "results": results,
        }

    def download_target(self, logical_name: str) -> DownloadTarget:
        info = self.resolver.resolve()
        file_entry = (info.manifest.get("files") or {}).get(logical_name)
        if not isinstance(file_entry, dict) or not file_entry.get("path"):
            raise QueryNotFound(f"Unknown public download: {logical_name}")

        if self.remote_store is not None:
            sidecar_path = info.artifact_dir / R2_RELEASE_SIDECAR_NAME
            if sidecar_path.is_file():
                try:
                    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise QueryArtifactUnavailable(
                        f"R2 release sidecar is invalid: {sidecar_path}"
                    ) from exc
                remote_entry = (sidecar.get("files") or {}).get(logical_name)
                if not isinstance(remote_entry, dict) or not remote_entry.get("key"):
                    raise QueryArtifactUnavailable(
                        f"R2 release has no download object for {logical_name}"
                    )
                for field in ("path", "sha256", "bytes"):
                    if remote_entry.get(field) != file_entry.get(field):
                        raise QueryArtifactUnavailable(
                            f"R2 release metadata disagrees about {logical_name}"
                        )
                return DownloadTarget(
                    info=info,
                    entry=file_entry,
                    url=self.remote_store.download_url(str(remote_entry["key"])),
                )

        path = (info.artifact_dir / str(file_entry["path"])).resolve()
        if info.artifact_dir not in path.parents or not path.is_file():
            raise QueryArtifactUnavailable("Public download path is invalid or missing")
        return DownloadTarget(info=info, entry=file_entry, path=path)

    def download_path(self, logical_name: str) -> tuple[ReleaseInfo, Path]:
        """Backward-compatible local download helper used by older callers."""
        target = self.download_target(logical_name)
        if target.path is None:
            raise QueryArtifactUnavailable("Public download is stored remotely")
        return target.info, target.path
