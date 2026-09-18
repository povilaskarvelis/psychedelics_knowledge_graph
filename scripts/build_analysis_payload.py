"""Build compact Analyze records and immutable, on-demand finding chunks.

Keep finding-level filter semantics and row identity; never aggregate away findings.
The detail payload remains the source of truth. Charts do not need its quotations,
locators, estimates, doses, funding metadata, or proposition identifiers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_analysis_index import build_index, load_columnar

SCHEMA = "psychedelics_kg_analysis_bootstrap_v1"
CHUNK_SIZE = 512
# These fields are used only by evidence cards / Explore, not Analyze charts or
# coverage axes. New chart dependencies must be covered by the parity tests.
DETAIL_ONLY_FIELDS = frozenset("""
    support effect_size p_value dose dosing_schedule session_context
    administration_route route route_of_administration
    affinity_value evidence_location evidence_locator proposition_group_id
    funders grant_ids funding_metadata_status funding_providers
    funding_assertion_count funding_funder_count funding_award_count
    registered_trial_urls open_data_resource_ids open_data_urls open_data_repositories
    shared_code_resource_ids shared_code_urls shared_code_repositories
    preregistration_urls preregistration_repositories
    risk_of_bias_summary heterogeneity_i_squared heterogeneity_tau_squared
    heterogeneity_interpretation meta_analysis_subgroup_or_moderator
""".split())
AUTHOR_FIELDS = frozenset("""
    name display_name displayName author label id author_id authorId
    openalex_author_id openalexAuthorId orcid
""".split())


def compact_row(row: dict) -> dict:
    result = {k: v for k, v in row.items() if k not in DETAIL_ONLY_FIELDS}
    for field in ("first_author", "last_author"):
        author = result.get(field)
        if isinstance(author, dict):
            result[field] = {k: v for k, v in author.items() if k in AUTHOR_FIELDS}
    return result


def columnar(rows: list[dict], *, run_length: bool = False, **metadata) -> dict:
    fields = sorted({field for row in rows for field in row})
    values: list = [None]
    ids = {"null": 0}
    def value_id(value):
        if value is None or value == "":
            return 0
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key not in ids:
            ids[key] = len(values)
            values.append(value)
        return ids[key]
    encoded = [[value_id(row.get(field)) for field in fields] for row in rows]
    if not run_length:
        return {**metadata, "fields": fields, "values": values, "rows": encoded}
    columns = []
    for index in range(len(fields)):
        runs = []
        for row in encoded:
            value = row[index]
            if runs and runs[-1][0] == value:
                runs[-1][1] += 1
            else:
                runs.append([value, 1])
        columns.append(runs)
    return {**metadata, "fields": fields, "values": values,
            "row_count": len(rows), "columns": columns}


def write_immutable(directory: Path, stem: str, payload: dict) -> Path:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()[:20]
    path = directory / f"{stem}_{digest}.json"
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    elif path.read_bytes() != content:
        raise ValueError(f"Immutable analysis payload mismatch: {path}")
    return path


def build_analysis_release(detail_paths: dict[str, Path], output_dir: Path, generated_at: str = "") -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    all_rows = {}
    files = {}
    for source, path in sorted(detail_paths.items()):
        rows = load_columnar(path)
        all_rows[source] = rows
        chunks = []
        for offset in range(0, len(rows), CHUNK_SIZE):
            chunk = columnar([
                {**row, "__analysis_row": offset + index}
                for index, row in enumerate(rows[offset:offset + CHUNK_SIZE])
            ], schema_version="psychedelics_kg_analysis_findings_v1", source=source)
            chunk_path = write_immutable(output_dir, f"findings_{source}_{offset // CHUNK_SIZE}", chunk)
            chunks.append(chunk_path.name)
            files[f"analysis_detail:{source}:{offset // CHUNK_SIZE}"] = chunk_path
        payload = columnar([
            compact_row(row) for row in rows
        ], run_length=True, schema_version=SCHEMA, source=source, chunk_size=CHUNK_SIZE, detail_chunks=chunks)
        compact_path = write_immutable(output_dir, f"analysis_{source}", payload)
        files[f"analysis:{source}"] = compact_path
        sources[source] = compact_path
    index_path = write_immutable(output_dir, "analysis_index", build_index(all_rows, generated_at))
    files["analysis:index"] = index_path
    return {"sources": sources, "index": index_path, "files": files}
