"""Out-of-core materialization helpers for large discovery runs."""

from __future__ import annotations

from pathlib import Path
import shutil

import duckdb
import pandas as pd

from .strategy import normalized_key


RECORD_COLUMNS = (
    "provider",
    "provider_record_id",
    "pmid",
    "pmcid",
    "doi",
    "openalex_id",
    "semantic_scholar_id",
    "title",
    "authors",
    "publication_year",
    "publication_date",
    "journal",
    "publication_type",
    "language",
    "abstract",
)

HIT_COLUMNS = (
    *RECORD_COLUMNS,
    "rank_in_partition",
    "run_id",
    "protocol_id",
    "execution_id",
    "search_id",
    "dataset",
    "layer",
    "search_type",
    "module_id",
    "compound",
    "entity",
    "entity_type",
    "date_basis",
    "search_surface",
    "partition_id",
    "partition_start_date",
    "partition_end_date",
    "page_index",
    "retrieved_at_utc",
)


def _quoted(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _connection(work_dir: Path) -> duckdb.DuckDBPyConnection:
    work_dir = Path(work_dir)
    temporary = work_dir / ".duckdb_tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute("SET preserve_insertion_order = false")
    connection.execute("SET threads = 1")
    connection.execute("SET memory_limit = '3GB'")
    connection.execute(f"SET temp_directory = {_quoted(temporary)}")
    return connection


def _copy_atomic(connection: duckdb.DuckDBPyConnection, query: str, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection.execute(
        f"COPY ({query}) TO {_quoted(temporary)} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    temporary.replace(output_path)


def materialize_hits_from_checkpoint(checkpoint_path: Path, hits_path: Path) -> None:
    """Deduplicate a newline-delimited checkpoint without loading it into pandas."""

    checkpoint_path = Path(checkpoint_path).resolve()
    hits_path = Path(hits_path).resolve()
    if not checkpoint_path.exists() or checkpoint_path.stat().st_size == 0:
        hits_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {column: pd.Series(dtype="string") for column in HIT_COLUMNS}
        ).to_parquet(hits_path, index=False)
        return
    connection = _connection(hits_path.parent)
    try:
        query = f"""
            SELECT * EXCLUDE (_row_number)
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY execution_id, partition_id, provider_record_id
                    ORDER BY retrieved_at_utc DESC, page_index DESC
                ) AS _row_number
                FROM read_json_auto(
                    {_quoted(checkpoint_path)},
                    format = 'newline_delimited',
                    records = true
                )
            )
            WHERE _row_number = 1
            ORDER BY provider, provider_record_id, execution_id, partition_id
        """
        _copy_atomic(connection, query, hits_path)
    finally:
        connection.close()


def _first_nonempty(column: str) -> str:
    quoted = f'"{column}"'
    text = f"trim(CAST({quoted} AS VARCHAR))"
    return (
        f"COALESCE(first({quoted} ORDER BY execution_id, partition_id) "
        f"FILTER (WHERE {quoted} IS NOT NULL AND {text} <> '' "
        f"AND lower({text}) NOT IN ('nan', 'none')), '') AS {quoted}"
    )


def _string_agg(column: str) -> str:
    quoted = f'"{column}"'
    text = f"trim(CAST({quoted} AS VARCHAR))"
    return (
        f"COALESCE(string_agg(DISTINCT {text}, ' | ' ORDER BY {text}) "
        f"FILTER (WHERE {quoted} IS NOT NULL AND {text} <> ''), '')"
    )


def materialize_records_from_hits(hits_path: Path, records_path: Path) -> dict[str, int]:
    """Aggregate provider hits into one row per provider record out of core."""

    hits_path = Path(hits_path).resolve()
    records_path = Path(records_path).resolve()
    connection = _connection(records_path.parent)
    parts_dir = records_path.parent / ".duckdb_record_parts"
    try:
        scalar_columns = ",\n".join(_first_nonempty(column) for column in RECORD_COLUMNS[2:])
        query_template = """
            SELECT
                provider,
                provider_record_id,
                %s,
                count(DISTINCT execution_id) AS discovery_execution_count,
                %s AS discovery_execution_ids,
                %s AS discovery_search_ids,
                %s AS discovery_datasets,
                %s AS discovery_layers,
                %s AS discovery_compounds,
                %s AS discovery_entities,
                min(retrieved_at_utc) AS first_retrieved_at_utc,
                max(retrieved_at_utc) AS last_retrieved_at_utc
            FROM read_parquet(%s)
            %s
            GROUP BY provider, provider_record_id
        """ % (
            scalar_columns,
            _string_agg("execution_id"),
            _string_agg("search_id"),
            _string_agg("dataset"),
            _string_agg("layer"),
            _string_agg("compound"),
            _string_agg("entity"),
            _quoted(hits_path),
            "%s",
        )
        # Large, highly overlapping searches can exceed memory even in DuckDB
        # because each provider record carries several distinct provenance
        # aggregates. Hash-bucket the grouping while still scanning Parquet
        # out of core, then concatenate the disjoint record parts.
        bucket_count = 32 if hits_path.stat().st_size > 100_000_000 else 1
        if bucket_count == 1:
            query = (query_template % "") + " ORDER BY provider, provider_record_id"
            _copy_atomic(connection, query, records_path)
        else:
            shutil.rmtree(parts_dir, ignore_errors=True)
            parts_dir.mkdir(parents=True, exist_ok=True)
            for bucket in range(bucket_count):
                where = f"WHERE hash(provider_record_id) % {bucket_count} = {bucket}"
                _copy_atomic(
                    connection,
                    query_template % where,
                    parts_dir / f"records_{bucket:02d}.parquet",
                )
            combined = (
                f"SELECT * FROM read_parquet({_quoted(parts_dir / '*.parquet')}) "
                "ORDER BY provider, provider_record_id"
            )
            _copy_atomic(connection, combined, records_path)
        provider_hits = int(
            connection.execute(
                f"SELECT count(*) FROM read_parquet({_quoted(hits_path)})"
            ).fetchone()[0]
        )
        provider_records, records_with_doi = connection.execute(
            f"""
            SELECT
                count(*),
                count(*) FILTER (WHERE trim(COALESCE(doi, '')) <> '')
            FROM read_parquet({_quoted(records_path)})
            """
        ).fetchone()
        return {
            "provider_hits": int(provider_hits),
            "provider_records": int(provider_records),
            "records_with_doi": int(records_with_doi),
            "records_without_doi": int(provider_records - records_with_doi),
        }
    finally:
        connection.close()
        shutil.rmtree(parts_dir, ignore_errors=True)


def query_group_metrics(hits_path: Path, executions: pd.DataFrame) -> pd.DataFrame:
    """Compute yield diagnostics with DuckDB while keeping execution metadata in pandas."""

    columns = [
        "provider",
        "layer",
        "search_type",
        "executions",
        "complete_executions",
        "zero_result_executions",
        "zero_result_rate",
        "expected_hits",
        "retrieved_hits",
        "count_requests",
        "result_pages",
        "unique_records",
        "unique_dois",
        "exclusive_records",
    ]
    if executions.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict] = []
    group_columns = ["provider", "layer", "search_type"]
    for group, frame in executions.groupby(group_columns, dropna=False, sort=True):
        complete = frame[frame["status"].astype(str).eq("complete")]
        zero = int((complete["expected_total"].fillna(0).astype(int) == 0).sum())
        rows.append(
            {
                "provider": str(group[0]),
                "layer": str(group[1]),
                "search_type": str(group[2]),
                "executions": int(len(frame)),
                "complete_executions": int(len(complete)),
                "zero_result_executions": zero,
                "zero_result_rate": round(zero / len(complete), 6) if len(complete) else None,
                "expected_hits": int(frame["expected_total"].fillna(0).astype(int).sum()),
                "retrieved_hits": int(frame["retrieved_total"].fillna(0).astype(int).sum()),
                "count_requests": int(frame["count_request_count"].fillna(0).astype(int).sum()),
                "result_pages": int(frame["page_count"].fillna(0).astype(int).sum()),
            }
        )
    metrics = pd.DataFrame(rows)

    hits_path = Path(hits_path).resolve()
    connection = _connection(hits_path.parent)
    try:
        hit_metrics = connection.execute(
            f"""
            WITH keyed AS (
                SELECT
                    provider,
                    layer,
                    search_type,
                    CASE
                        WHEN trim(COALESCE(doi, '')) <> ''
                            THEN 'doi:' || lower(trim(doi))
                        WHEN trim(COALESCE(pmid, '')) <> ''
                            THEN 'pmid:' || trim(pmid)
                        WHEN trim(COALESCE(openalex_id, '')) <> ''
                            THEN 'openalex:' || upper(trim(openalex_id))
                        ELSE 'provider:' || trim(provider_record_id)
                    END AS record_key,
                    lower(trim(COALESCE(doi, ''))) AS doi_key
                FROM read_parquet({_quoted(hits_path)})
            ),
            group_records AS (
                SELECT DISTINCT provider, layer, search_type, record_key, doi_key
                FROM keyed
                WHERE record_key <> ''
            ),
            key_group_counts AS (
                SELECT record_key, count(*) AS group_count
                FROM group_records
                GROUP BY record_key
            )
            SELECT
                records.provider,
                records.layer,
                records.search_type,
                count(*) AS unique_records,
                count(DISTINCT NULLIF(records.doi_key, '')) AS unique_dois,
                count(*) FILTER (WHERE counts.group_count = 1) AS exclusive_records
            FROM group_records AS records
            JOIN key_group_counts AS counts USING (record_key)
            GROUP BY records.provider, records.layer, records.search_type
            """
        ).fetchdf()
    finally:
        connection.close()
    metrics = metrics.merge(hit_metrics, on=group_columns, how="left")
    for column in ("unique_records", "unique_dois", "exclusive_records"):
        metrics[column] = metrics[column].fillna(0).astype(int)
    return metrics[columns]


def compose_hits(
    *,
    gap_hits_path: Path,
    gap_run_id: str,
    update_hits_path: Path,
    update_run_id: str,
    composite_run_id: str,
    output_path: Path,
) -> None:
    """Compose component hit tables without concatenating them in memory."""

    output_path = Path(output_path).resolve()
    connection = _connection(output_path.parent)
    try:
        query = f"""
            WITH combined AS (
                SELECT
                    * REPLACE ({_quoted(composite_run_id)} AS run_id),
                    {_quoted(gap_run_id)} AS component_run_id,
                    {_quoted(composite_run_id)} AS composite_run_id,
                    0 AS _component_order
                FROM read_parquet({_quoted(Path(gap_hits_path).resolve())})
                UNION ALL BY NAME
                SELECT
                    * REPLACE ({_quoted(composite_run_id)} AS run_id),
                    {_quoted(update_run_id)} AS component_run_id,
                    {_quoted(composite_run_id)} AS composite_run_id,
                    1 AS _component_order
                FROM read_parquet({_quoted(Path(update_hits_path).resolve())})
            ),
            ranked AS (
                SELECT *, row_number() OVER (
                    PARTITION BY execution_id, partition_id, provider_record_id
                    ORDER BY _component_order DESC, retrieved_at_utc DESC
                ) AS _row_number
                FROM combined
            )
            SELECT * EXCLUDE (_component_order, _row_number)
            FROM ranked
            WHERE _row_number = 1
            ORDER BY provider, provider_record_id, execution_id, partition_id
        """
        _copy_atomic(connection, query, output_path)
    finally:
        connection.close()


def contexts_from_hits_parquet(
    hits_path: Path,
    doi_by_provider_record: dict[str, str],
    run_artifact: str,
) -> list[dict]:
    """Aggregate candidate contexts without loading every query hit into pandas."""

    mapping = pd.DataFrame(
        sorted(doi_by_provider_record.items()), columns=["provider_record_id", "canonical_doi"]
    )
    hits_path = Path(hits_path).resolve()
    connection = _connection(hits_path.parent)
    try:
        connection.register("doi_mapping", mapping)
        contexts = connection.execute(
            f"""
            WITH enriched AS (
                SELECT
                    lower(trim(COALESCE(NULLIF(hits.doi, ''), mapping.canonical_doi, ''))) AS doi,
                    trim(COALESCE(hits.compound, '')) AS compound,
                    trim(COALESCE(hits.entity, '')) AS entity,
                    trim(COALESCE(hits.entity_type, '')) AS entity_type,
                    trim(COALESCE(hits.search_id, '')) AS search_id
                FROM read_parquet({_quoted(hits_path)}) AS hits
                LEFT JOIN doi_mapping AS mapping USING (provider_record_id)
                WHERE trim(COALESCE(hits.compound, '')) <> ''
                   OR trim(COALESCE(hits.entity, '')) <> ''
            )
            SELECT
                doi,
                compound,
                entity,
                entity_type,
                string_agg(DISTINCT search_id, ' | ' ORDER BY search_id)
                    FILTER (WHERE search_id <> '') AS search_ids
            FROM enriched
            WHERE doi <> ''
            GROUP BY doi, compound, entity, entity_type
            ORDER BY doi, compound, entity, entity_type
            """
        ).fetchdf()
    finally:
        connection.close()
    rows: list[dict] = []
    for row in contexts.to_dict("records"):
        identifier = "|".join(
            [
                row["doi"],
                normalized_key(row["compound"]),
                normalized_key(row["entity"]),
                normalized_key(row["entity_type"]),
            ]
        )
        rows.append(
            {
                "context_id": identifier,
                "doi": row["doi"],
                "compound": row["compound"],
                "entity": row["entity"],
                "entity_type": row["entity_type"],
                "search_ids": row.get("search_ids") or "",
                "source_artifacts": run_artifact,
            }
        )
    return rows


def cleanup_temporary_directory(run_dir: Path) -> None:
    shutil.rmtree(Path(run_dir) / ".duckdb_tmp", ignore_errors=True)
