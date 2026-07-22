#!/usr/bin/env python3
"""Provider-only normalization helpers for paper funding metadata.

This module deliberately does not accept the legacy ``funders`` or
``grant_ids`` strings from candidate, extraction, or KG records.  Its inputs
are provider response fragments, and every output row retains the provider
that asserted the funder/award relationship.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Iterable

from pipeline.ingest.metadata_utils import normalize, normalize_doi


FUNDING_ASSERTION_SCHEMA_VERSION = "paper_funding_v1"
FUNDING_ATTEMPT_SCHEMA_VERSION = "paper_funding_provider_attempt_v1"

ASSERTION_COLUMNS = (
    "schema_version",
    "assertion_key",
    "doi",
    "provider",
    "provider_record_id",
    "source_field",
    "funder_name",
    "funder_acronym",
    "funder_country",
    "funder_openalex_id",
    "funder_ror_id",
    "funder_crossref_id",
    "award_id",
    "award_name",
    "award_openalex_id",
    "award_doi",
    "provider_asserted_by",
    "retrieval_run_id",
    "retrieved_at_utc",
    "source_payload_sha256",
)

ATTEMPT_COLUMNS = (
    "schema_version",
    "doi",
    "provider",
    "provider_record_id",
    "lookup_identifier",
    "result_status",
    "funding_assertion_count",
    "retrieval_run_id",
    "retrieved_at_utc",
    "source_payload_sha256",
    "source_payload_json",
    "error_type",
    "error_message",
)

TERMINAL_ATTEMPT_STATUSES = {
    "funding_found",
    "no_funding_metadata",
    "provider_record_not_found",
}

FUNDING_VALUE_FIELDS = (
    "funder_name",
    "funder_acronym",
    "funder_openalex_id",
    "funder_ror_id",
    "funder_crossref_id",
    "award_id",
    "award_name",
    "award_openalex_id",
    "award_doi",
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def clean_identifier(value: object) -> str:
    return normalize(value).rstrip("/")


def openalex_short_id(value: object, prefix: str) -> str:
    text = clean_identifier(value)
    short = text.rsplit("/", 1)[-1]
    return short if short.upper().startswith(prefix.upper()) else text


def first_value(value: object) -> str:
    values = value if isinstance(value, list) else [value]
    for item in values:
        text = normalize(item)
        if text:
            return text
    return ""


def blank_assertion() -> dict[str, str]:
    return {column: "" for column in ASSERTION_COLUMNS}


def assertion_identity(row: dict) -> str:
    identity_fields = (
        "doi",
        "provider",
        "source_field",
        "funder_name",
        "funder_acronym",
        "funder_openalex_id",
        "funder_ror_id",
        "funder_crossref_id",
        "award_id",
        "award_name",
        "award_openalex_id",
        "award_doi",
    )
    identity = "\x1f".join(normalize(row.get(field, "")).casefold() for field in identity_fields)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def finalize_assertions(
    rows: Iterable[dict],
    *,
    doi: str,
    provider: str,
    provider_record_id: str,
    retrieval_run_id: str,
    retrieved_at_utc: str,
    source_payload_sha256: str,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in rows:
        row = blank_assertion()
        row.update({column: normalize(source.get(column, "")) for column in ASSERTION_COLUMNS})
        row.update(
            {
                "schema_version": FUNDING_ASSERTION_SCHEMA_VERSION,
                "doi": normalize_doi(doi).lower(),
                "provider": normalize(provider).lower(),
                "provider_record_id": normalize(provider_record_id),
                "retrieval_run_id": normalize(retrieval_run_id),
                "retrieved_at_utc": normalize(retrieved_at_utc),
                "source_payload_sha256": normalize(source_payload_sha256),
            }
        )
        if not any(row[field] for field in FUNDING_VALUE_FIELDS):
            continue
        row["assertion_key"] = assertion_identity(row)
        if row["assertion_key"] in seen:
            continue
        seen.add(row["assertion_key"])
        out.append(row)
    return out


def openalex_funding_fragment(work: dict) -> dict:
    return {
        "funders": work.get("funders", []) if isinstance(work, dict) else [],
        "awards": work.get("awards", []) if isinstance(work, dict) else [],
    }


def funding_rows_from_openalex(work: dict) -> list[dict[str, str]]:
    """Normalize current OpenAlex ``funders`` and ``awards`` fields.

    The deprecated Work ``grants`` field is intentionally not consumed here.
    """

    raw_funders = work.get("funders", []) if isinstance(work, dict) else []
    raw_awards = work.get("awards", []) if isinstance(work, dict) else []
    funders = [item for item in raw_funders if isinstance(item, dict)] if isinstance(raw_funders, list) else []
    awards = [item for item in raw_awards if isinstance(item, dict)] if isinstance(raw_awards, list) else []

    funder_by_id: dict[str, dict] = {}
    for funder in funders:
        funder_id = clean_identifier(funder.get("id", ""))
        if funder_id:
            funder_by_id[funder_id.casefold()] = funder
            funder_by_id[openalex_short_id(funder_id, "F").casefold()] = funder

    represented_ids: set[str] = set()
    represented_names: set[str] = set()
    rows: list[dict[str, str]] = []
    for award in awards:
        funder_id = clean_identifier(award.get("funder_id", ""))
        funder = funder_by_id.get(funder_id.casefold(), {}) if funder_id else {}
        if funder_id:
            represented_ids.add(openalex_short_id(funder_id, "F").casefold())
        funder_name = normalize(award.get("funder_display_name", "")) or normalize(
            funder.get("display_name", "")
        )
        if funder_name:
            represented_names.add(funder_name.casefold())
        rows.append(
            {
                "source_field": "awards",
                "funder_name": funder_name,
                "funder_openalex_id": openalex_short_id(
                    funder_id or funder.get("id", ""), "F"
                ),
                "funder_ror_id": clean_identifier(funder.get("ror", "")),
                "award_id": normalize(award.get("funder_award_id", "")),
                "award_name": normalize(award.get("display_name", "")),
                "award_openalex_id": openalex_short_id(award.get("id", ""), "A"),
                "award_doi": normalize_doi(award.get("doi", "")),
            }
        )

    for funder in funders:
        funder_id = openalex_short_id(funder.get("id", ""), "F")
        funder_name = normalize(funder.get("display_name", ""))
        if (
            (funder_id and funder_id.casefold() in represented_ids)
            or (funder_name and funder_name.casefold() in represented_names)
        ):
            continue
        rows.append(
            {
                "source_field": "funders",
                "funder_name": funder_name,
                "funder_openalex_id": funder_id,
                "funder_ror_id": clean_identifier(funder.get("ror", "")),
            }
        )
    return rows


def pubmed_funding_fragment(article: ET.Element) -> dict:
    grants: list[dict[str, str]] = []
    for grant in article.findall(".//GrantList/Grant"):
        grants.append(
            {
                "grant_id": normalize(grant.findtext("GrantID")),
                "acronym": normalize(grant.findtext("Acronym")),
                "agency": normalize(grant.findtext("Agency")),
                "country": normalize(grant.findtext("Country")),
            }
        )
    return {"grants": grants}


def funding_rows_from_pubmed(article: ET.Element) -> list[dict[str, str]]:
    return [
        {
            "source_field": "GrantList/Grant",
            "funder_name": grant["agency"] or grant["acronym"],
            "funder_acronym": grant["acronym"],
            "funder_country": grant["country"],
            "award_id": grant["grant_id"],
        }
        for grant in pubmed_funding_fragment(article)["grants"]
    ]


def crossref_funding_fragment(item: dict) -> dict:
    return {"funder": item.get("funder", []) if isinstance(item, dict) else []}


def funding_rows_from_crossref(item: dict) -> list[dict[str, str]]:
    raw_funders = item.get("funder", []) if isinstance(item, dict) else []
    funders = raw_funders if isinstance(raw_funders, list) else []
    rows: list[dict[str, str]] = []
    for funder in funders:
        if not isinstance(funder, dict):
            continue
        awards = funder.get("award", [])
        awards = awards if isinstance(awards, list) else [awards]
        award_values = [normalize(value) for value in awards if normalize(value)] or [""]
        crossref_id = first_value(funder.get("DOI", "") or funder.get("doi", ""))
        ror_id = first_value(funder.get("ROR", "") or funder.get("ror", ""))
        for award_id in award_values:
            rows.append(
                {
                    "source_field": "funder",
                    "funder_name": normalize(funder.get("name", "")),
                    "funder_ror_id": clean_identifier(ror_id),
                    "funder_crossref_id": normalize_doi(crossref_id),
                    "award_id": award_id,
                    "provider_asserted_by": normalize(funder.get("doi-asserted-by", "")),
                }
            )
    return rows
