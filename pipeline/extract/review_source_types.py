"""Publication types sharing the Reviews relationship-extraction path.

Publication genre is preserved. An analysis enters this path only after an
explicit scope inclusion; its genre alone must never resurrect an exclusion.
"""

REVIEW_TYPES = frozenset({
    "review", "systematic_review", "scoping_review", "narrative_review",
    "literature_review", "umbrella_review",
})
SCHOLARLY_ANALYSIS_TYPES = frozenset({"commentary_editorial", "other_non_primary"})
REVIEW_PATH_TYPES = REVIEW_TYPES | SCHOLARLY_ANALYSIS_TYPES


def is_accepted_scholarly_analysis(row: dict) -> bool:
    source_type = next((str(row.get(key, "") or "").strip() for key in (
        "paper_type", "source_type", "literature_source_type", "primary_secondary_source_type",
    ) if str(row.get(key, "") or "").strip()), "")
    decisions = {
        value.strip()
        for key in ("screening_decision", "domain_screening_decision", "extraction_domain_screening_decisions")
        for value in str(row.get(key, "") or "").split("|")
        if value.strip()
    }
    return source_type in SCHOLARLY_ANALYSIS_TYPES and decisions == {"include_in_scope"}
