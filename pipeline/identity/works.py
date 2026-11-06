"""Relations between identifiers of one work.

The work registry is ``pipeline/validate/doi_alias_registry.json``: each record
maps an alias DOI to the canonical DOI of the same work. Its records name the
relation in free-form ``relationship_type`` strings, and many name none. This
module gives the relations one fixed vocabulary and maps the older names onto
it, without changing the registry file or how deduplication reads it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORK_REGISTRY = ROOT / "pipeline" / "validate" / "doi_alias_registry.json"

WORK_RELATIONS = {
    "same_publication": "another DOI for the same publication: an alternate journal or publisher DOI, a legacy PII, or a malformed or duplicated variant",
    "repository_copy": "a repository deposit of the publication",
    "preprint": "a preprint of the publication",
    "preprint_or_repository_copy": "a preprint or a repository copy; the older record does not say which",
    "accepted_manuscript": "the authors' accepted manuscript of the publication",
    "version_doi": "a DOI for one version of the same work, such as a DataCite concept or version DOI",
    "translation": "another language edition of the publication",
    "correction_pair": "a correction notice and the article it corrects",
    "part_of": "a part of the item, such as a supplement, a peer-review report or one item in a collection",
}
# Relations under which two DOIs count as one report.
DEDUPLICATED_RELATIONS = frozenset(
    {
        "same_publication",
        "repository_copy",
        "preprint",
        "preprint_or_repository_copy",
        "accepted_manuscript",
        "version_doi",
        "translation",
    }
)
# Older free-form relation names in the work registry. A record without a name
# was registered as the same report, so it maps to ``same_publication``.
LEGACY_ALIAS_RELATIONS = {
    "": "same_publication",
    "verified_same_report_identifier": "same_publication",
    "verified_same_report_legacy_pii": "same_publication",
    "alternate_journal_doi": "same_publication",
    "alternate_publisher_doi": "same_publication",
    "publisher_duplicate_identifier": "same_publication",
    "malformed_doi_punctuation_alias": "same_publication",
    "malformed_duplicate_identifier": "same_publication",
    "duplicated_doi_prefix_alias": "same_publication",
    "enumerated_identifier_repair": "same_publication",
    "identical_pdf_version_alias": "same_publication",
    "repository_wrapper_doi": "repository_copy",
    "repository_report_identifier": "repository_copy",
    "repository_or_published_version_alias": "repository_copy",
    "repository_or_preprint_wrapper_doi": "preprint_or_repository_copy",
    "datacite_concept_version_alias": "version_doi",
}


def relation_for_legacy_alias_type(value: object) -> str:
    """The fixed relation for a registry record's ``relationship_type``.

    Records added by ``decide`` already name a fixed relation.
    """
    legacy = clean(value)
    if legacy in WORK_RELATIONS:
        return legacy
    if legacy not in LEGACY_ALIAS_RELATIONS:
        raise ValueError(f"Unmapped work-registry relationship_type: {legacy!r}")
    return LEGACY_ALIAS_RELATIONS[legacy]


def work_relation_index(path: Path = DEFAULT_WORK_REGISTRY) -> dict[frozenset[str], str]:
    """Map each registered pair of DOIs, in either order, to its relation."""
    return {
        frozenset((record["alias_doi"], record["canonical_doi"])): record["relation"]
        for record in load_work_relations(path)
    }


def load_work_relations(path: Path = DEFAULT_WORK_REGISTRY) -> list[dict[str, str]]:
    """Return the registry's alias records with their relation in the fixed vocabulary."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    for record in payload.get("records", []):
        if not isinstance(record, dict):
            continue
        alias = normalize_doi(record.get("alias_doi", ""))
        canonical = normalize_doi(record.get("canonical_doi", ""))
        if not alias or not canonical:
            continue
        out.append(
            {
                "alias_doi": alias,
                "canonical_doi": canonical,
                "relation": relation_for_legacy_alias_type(record.get("relationship_type")),
                "legacy_relationship_type": clean(record.get("relationship_type")),
                "evidence_basis": clean(record.get("evidence_basis")),
            }
        )
    return out
