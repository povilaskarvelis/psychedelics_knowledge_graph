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
from .models import PaperFilters, PaperQuery, RelationshipFilters, RelationshipQuery
from .r2_store import R2_RELEASE_SIDECAR_NAME, ObjectStore, R2ObjectStore


PUBLIC_DB_NAME = "public_api.duckdb"
PUBLIC_MANIFEST_NAME = "manifest.json"
PUBLIC_SCHEMA_NAME = "schema.json"
PUBLIC_QUERY_MANIFEST_VERSION = "psychedelics_kg_public_catalogue_manifest_v2"

JSON_VALUE_FIELDS = {
    "aliases_json",
    "external_ids_json",
    "name_variants_json",
    "openalex_profile_ids_json",
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
    """Resolve every request through the current graph release pointer."""

    def __init__(self, *, active_pointer: Path, query_runs_dir: Path) -> None:
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
                f"The current release has no public catalogue artifact: {run_id}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise QueryArtifactUnavailable(
                f"Public catalogue manifest is invalid JSON: {manifest_path}"
            ) from exc
        if manifest.get("schema_version") != PUBLIC_QUERY_MANIFEST_VERSION:
            raise QueryArtifactUnavailable(
                f"Unsupported public catalogue schema: {manifest.get('schema_version')}"
            )
        if manifest.get("run_id") != run_id:
            raise QueryArtifactUnavailable(
                f"Current release/catalogue mismatch: {run_id} vs {manifest.get('run_id')}"
            )

        db_path = artifact_dir / str(manifest.get("database") or PUBLIC_DB_NAME)
        schema_path = artifact_dir / str(manifest.get("schema") or PUBLIC_SCHEMA_NAME)
        if not db_path.is_file() or not schema_path.is_file():
            raise QueryArtifactUnavailable(
                f"Public catalogue artifact is incomplete: {artifact_dir}"
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
        column: json_value(value)
        for column, value in zip(columns, values, strict=True)
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
            "This cursor belongs to a different data release; restart pagination."
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
            "public_data": [
                "papers",
                "concepts",
                "OpenAlex/ORCID-backed authors",
                "paper-level relationships",
            ],
            "excluded_data": [
                "granular findings",
                "statistics",
                "quotes",
                "result direction",
                "internal curation fields",
            ],
            "author_identity_note": (
                "ORCID is canonical when available, including across OpenAlex profiles "
                "carrying the same ORCID. Otherwise the OpenAlex profile remains the "
                "identifier. Unresolved name-only rows and profiles with conflicting "
                "ORCID evidence are excluded."
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

    @staticmethod
    def add_year_filter(
        clauses: list[str], params: list[Any], year_from: int | None, year_to: int | None
    ) -> None:
        if year_from is not None:
            clauses.append("p.year >= ?")
            params.append(year_from)
        if year_to is not None:
            clauses.append("p.year <= ?")
            params.append(year_to)

    def paper_where(self, filters: PaperFilters) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for expression, values, casefold in (
            ("p.paper_id", filters.paper_ids, False),
            ("p.doi", filters.dois, True),
            ("p.paper_type", filters.paper_types, True),
            ("p.paper_subtype", filters.paper_subtypes, True),
        ):
            self.add_in_filter(
                clauses, params, expression=expression, values=values, casefold=casefold
            )
        if filters.author_ids:
            placeholders = ",".join("?" for _ in filters.author_ids)
            clauses.append(
                "EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.paper_id "
                f"AND pa.author_id IN ({placeholders}))"
            )
            params.extend(filters.author_ids)
        if filters.author_names:
            cleaned = [value.strip().casefold() for value in filters.author_names if value.strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                clauses.append(
                    "EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.paper_id "
                    f"AND lower(pa.normalized_name) IN ({placeholders}))"
                )
                params.extend(cleaned)
        relationship_filters = (
            filters.concept_ids or filters.domains or filters.relation_types
        )
        if relationship_filters:
            rel_clauses = ["r.paper_id = p.paper_id"]
            if filters.concept_ids:
                placeholders = ",".join("?" for _ in filters.concept_ids)
                rel_clauses.append(
                    f"(r.subject_id IN ({placeholders}) OR r.object_id IN ({placeholders}))"
                )
                params.extend(filters.concept_ids)
                params.extend(filters.concept_ids)
            self.add_in_filter(
                rel_clauses,
                params,
                expression="r.domain",
                values=filters.domains,
                casefold=True,
            )
            self.add_in_filter(
                rel_clauses,
                params,
                expression="r.relation_type",
                values=filters.relation_types,
                casefold=True,
            )
            clauses.append(
                f"EXISTS (SELECT 1 FROM relationships r WHERE {' AND '.join(rel_clauses)})"
            )
        self.add_year_filter(clauses, params, filters.year_from, filters.year_to)
        if filters.query:
            value = f"%{filters.query.casefold()}%"
            clauses.append(
                "(lower(concat_ws(' ', p.title, p.doi, p.journal)) LIKE ? OR "
                "EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.paper_id "
                "AND lower(pa.author_name) LIKE ?))"
            )
            params.extend([value, value])
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def relationship_where(
        self, filters: RelationshipFilters
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for expression, values, casefold in (
            ("r.paper_id", filters.paper_ids, False),
            ("p.doi", filters.dois, True),
            ("r.paper_type", filters.paper_types, True),
            ("r.paper_subtype", filters.paper_subtypes, True),
            ("r.subject_id", filters.subject_ids, False),
            ("r.object_id", filters.object_ids, False),
            ("r.domain", filters.domains, True),
            ("r.relation_type", filters.relation_types, True),
        ):
            self.add_in_filter(
                clauses, params, expression=expression, values=values, casefold=casefold
            )
        if filters.concept_ids:
            placeholders = ",".join("?" for _ in filters.concept_ids)
            clauses.append(
                f"(r.subject_id IN ({placeholders}) OR r.object_id IN ({placeholders}))"
            )
            params.extend(filters.concept_ids)
            params.extend(filters.concept_ids)
        if filters.author_ids:
            placeholders = ",".join("?" for _ in filters.author_ids)
            clauses.append(
                "EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.paper_id "
                f"AND pa.author_id IN ({placeholders}))"
            )
            params.extend(filters.author_ids)
        if filters.author_names:
            cleaned = [value.strip().casefold() for value in filters.author_names if value.strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                clauses.append(
                    "EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.paper_id "
                    f"AND lower(pa.normalized_name) IN ({placeholders}))"
                )
                params.extend(cleaned)
        self.add_year_filter(clauses, params, filters.year_from, filters.year_to)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def attach_authors(
        self,
        con: duckdb.DuckDBPyConnection,
        papers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not papers:
            return papers
        paper_ids = [paper["paper_id"] for paper in papers]
        placeholders = ",".join("?" for _ in paper_ids)
        authors = fetch_rows(
            con.execute(
                f"""
                SELECT paper_id, author_id, author_name, author_position,
                       is_first_author, is_last_author
                FROM paper_authors
                WHERE paper_id IN ({placeholders})
                ORDER BY paper_id, author_position, author_name
                """,
                paper_ids,
            )
        )
        by_paper: dict[str, list[dict[str, Any]]] = {}
        for author in authors:
            by_paper.setdefault(author.pop("paper_id"), []).append(author)
        for paper in papers:
            paper["authors"] = by_paper.get(paper["paper_id"], [])
        return papers

    def paged_meta(
        self,
        info: ReleaseInfo,
        *,
        total: int,
        returned: int,
        offset: int,
    ) -> dict[str, Any]:
        next_offset = offset + returned
        return {
            **self.release_meta(info),
            "total": total,
            "returned": returned,
            "next_cursor": (
                encode_cursor(release_id=info.release_id, offset=next_offset)
                if next_offset < total
                else None
            ),
        }

    def facets(self) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            def values(sql: str) -> list[dict[str, Any]]:
                return fetch_rows(con.execute(sql))

            facets = {
                "paper_types": values(
                    "SELECT paper_type AS value, count(*) AS paper_count FROM papers "
                    "WHERE paper_type IS NOT NULL GROUP BY 1 ORDER BY 1"
                ),
                "paper_subtypes": values(
                    "SELECT paper_subtype AS value, count(*) AS paper_count FROM papers "
                    "WHERE paper_subtype IS NOT NULL GROUP BY 1 ORDER BY 1"
                ),
                "domains": values(
                    "SELECT domain AS value, count(DISTINCT paper_id) AS paper_count "
                    "FROM relationships GROUP BY 1 ORDER BY 1"
                ),
                "relation_types": values(
                    "SELECT relation_type AS value, count(DISTINCT paper_id) AS paper_count "
                    "FROM relationships GROUP BY 1 ORDER BY 1"
                ),
                "concept_kinds": values(
                    "SELECT concept_kind AS value, count(*) AS concept_count "
                    "FROM concepts GROUP BY 1 ORDER BY 1"
                ),
            }
            year_range = fetch_rows(
                con.execute("SELECT min(year) AS minimum, max(year) AS maximum FROM papers")
            )[0]
            unclassified_paper_count = int(
                con.execute(
                    "SELECT count(*) FROM papers WHERE paper_type IS NULL"
                ).fetchone()[0]
            )
        return {
            "meta": self.release_meta(info),
            "paper_years": year_range,
            "unclassified_paper_count": unclassified_paper_count,
            **facets,
        }

    def search_concepts(
        self,
        query: str,
        *,
        concept_kinds: Sequence[str] = (),
        domains: Sequence[str] = (),
        limit: int = 15,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise InvalidQuery("Concept search query must not be empty")
        limit = max(1, min(int(limit), 50))
        info = self.resolver.resolve()
        clauses = ["(lower(c.label) LIKE ? OR lower(coalesce(c.aliases_json, '')) LIKE ?)"]
        params: list[Any] = [f"%{query.casefold()}%", f"%{query.casefold()}%"]
        self.add_in_filter(
            clauses,
            params,
            expression="c.concept_kind",
            values=concept_kinds,
            casefold=True,
        )
        self.add_in_filter(
            clauses, params, expression="c.domain", values=domains, casefold=True
        )
        params.extend([query.casefold(), f"{query.casefold()}%", limit])
        with self.connection(info) as con:
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT c.*,
                           (SELECT count(DISTINCT r.paper_id)
                            FROM relationships r
                            WHERE c.concept_id = r.subject_id OR c.concept_id = r.object_id)
                            AS paper_count,
                           (SELECT count(DISTINCT r.relationship_id)
                            FROM relationships r
                            WHERE c.concept_id = r.subject_id OR c.concept_id = r.object_id)
                            AS relationship_count
                    FROM concepts c
                    WHERE {' AND '.join(clauses)}
                    ORDER BY CASE
                        WHEN lower(c.label) = ? THEN 0
                        WHEN lower(c.label) LIKE ? THEN 1
                        ELSE 2
                    END, c.label
                    LIMIT ?
                    """,
                    params,
                )
            )
        return {"meta": self.release_meta(info), "results": results}

    def get_concept(self, concept_id: str) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            rows = fetch_rows(
                con.execute("SELECT * FROM concepts WHERE concept_id = ?", [concept_id])
            )
            if not rows:
                raise QueryNotFound(f"Unknown concept_id: {concept_id}")
            counts = fetch_rows(
                con.execute(
                    """
                    SELECT count(DISTINCT paper_id) AS paper_count,
                           count(DISTINCT relationship_id) AS relationship_count
                    FROM relationships
                    WHERE subject_id = ? OR object_id = ?
                    """,
                    [concept_id, concept_id],
                )
            )[0]
        return {"meta": self.release_meta(info), "data": {**rows[0], **counts}}

    def search_authors(self, query: str, *, limit: int = 15) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise InvalidQuery("Author search query must not be empty")
        limit = max(1, min(int(limit), 50))
        info = self.resolver.resolve()
        value = query.casefold()
        with self.connection(info) as con:
            results = fetch_rows(
                con.execute(
                    """
                    SELECT * FROM authors
                    WHERE lower(author_name) LIKE ? OR lower(normalized_name) LIKE ?
                       OR lower(coalesce(name_variants_json, '')) LIKE ?
                    ORDER BY CASE
                        WHEN lower(author_name) = ? OR lower(normalized_name) = ? THEN 0
                        WHEN lower(author_name) LIKE ? THEN 1
                        ELSE 2
                    END, paper_count DESC, author_name
                    LIMIT ?
                    """,
                    [
                        f"%{value}%",
                        f"%{value}%",
                        f"%{value}%",
                        value,
                        value,
                        f"{value}%",
                        limit,
                    ],
                )
            )
        return {
            "meta": {
                **self.release_meta(info),
                "identity_note": "ORCID is canonical when available; otherwise records use an OpenAlex profile ID.",
            },
            "results": results,
        }

    def get_author(self, author_id: str) -> dict[str, Any]:
        info = self.resolver.resolve()
        with self.connection(info) as con:
            rows = fetch_rows(
                con.execute("SELECT * FROM authors WHERE author_id = ?", [author_id])
            )
        if not rows:
            raise QueryNotFound(f"Unknown author_id: {author_id}")
        return {
            "meta": {
                **self.release_meta(info),
                "identity_note": "This record uses an ORCID when available; otherwise it uses an OpenAlex profile ID.",
            },
            "data": rows[0],
        }

    def query_papers(self, request: PaperQuery) -> dict[str, Any]:
        info = self.resolver.resolve()
        offset = decode_cursor(request.cursor, release_id=info.release_id)
        where, params = self.paper_where(request.filters)
        with self.connection(info) as con:
            total = int(
                con.execute(f"SELECT count(*) FROM papers p{where}", params).fetchone()[0]
            )
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT p.* FROM papers p
                    {where}
                    ORDER BY p.year DESC NULLS LAST, p.title, p.paper_id
                    LIMIT ? OFFSET ?
                    """,
                    [*params, request.limit, offset],
                )
            )
            self.attach_authors(con, results)
        return {
            "meta": self.paged_meta(
                info, total=total, returned=len(results), offset=offset
            ),
            "results": results,
        }

    def get_author_papers(
        self, author_id: str, *, limit: int = 25, cursor: str | None = None
    ) -> dict[str, Any]:
        self.get_author(author_id)
        return self.query_papers(
            PaperQuery(
                filters=PaperFilters(author_ids=[author_id]),
                limit=limit,
                cursor=cursor,
            )
        )

    def get_paper(
        self,
        paper_id_or_doi: str,
        *,
        include_relationships: bool = True,
        relationship_limit: int = 50,
    ) -> dict[str, Any]:
        info = self.resolver.resolve()
        relationship_limit = max(1, min(int(relationship_limit), 100))
        normalized_doi = paper_id_or_doi.removeprefix("https://doi.org/").removeprefix(
            "doi:"
        )
        with self.connection(info) as con:
            papers = fetch_rows(
                con.execute(
                    """
                    SELECT * FROM papers
                    WHERE paper_id = ? OR lower(doi) = lower(?)
                    LIMIT 1
                    """,
                    [paper_id_or_doi, normalized_doi],
                )
            )
            if not papers:
                raise QueryNotFound(f"Unknown paper identifier: {paper_id_or_doi}")
            paper = self.attach_authors(con, papers)[0]
            relationship_count = int(
                con.execute(
                    "SELECT count(*) FROM relationships WHERE paper_id = ?",
                    [paper["paper_id"]],
                ).fetchone()[0]
            )
            relationships: list[dict[str, Any]] = []
            if include_relationships:
                relationships = fetch_rows(
                    con.execute(
                        """
                        SELECT * FROM relationships
                        WHERE paper_id = ?
                        ORDER BY domain, subject_label, object_label, relation_type
                        LIMIT ?
                        """,
                        [paper["paper_id"], relationship_limit],
                    )
                )
        return {
            "meta": self.release_meta(info),
            "data": paper,
            "relationship_count": relationship_count,
            "relationships_truncated": relationship_count > len(relationships)
            if include_relationships
            else None,
            **({"relationships": relationships} if include_relationships else {}),
        }

    def query_relationships(self, request: RelationshipQuery) -> dict[str, Any]:
        info = self.resolver.resolve()
        offset = decode_cursor(request.cursor, release_id=info.release_id)
        where, params = self.relationship_where(request.filters)
        with self.connection(info) as con:
            total = int(
                con.execute(
                    f"SELECT count(*) FROM relationships r JOIN papers p USING (paper_id){where}",
                    params,
                ).fetchone()[0]
            )
            results = fetch_rows(
                con.execute(
                    f"""
                    SELECT r.*, p.doi, p.title, p.year, p.journal
                    FROM relationships r
                    JOIN papers p USING (paper_id)
                    {where}
                    ORDER BY p.year DESC NULLS LAST, r.paper_id, r.relationship_id
                    LIMIT ? OFFSET ?
                    """,
                    [*params, request.limit, offset],
                )
            )
        return {
            "meta": self.paged_meta(
                info, total=total, returned=len(results), offset=offset
            ),
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
