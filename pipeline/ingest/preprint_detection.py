"""Deterministic publication-stage detection for preprint handling."""

from __future__ import annotations

import re
from collections.abc import Mapping


PREPRINT_DOI_PATTERNS = (
    ("doi:bioRxiv/medRxiv", re.compile(r"^10\.1101/", re.I)),
    ("doi:PsyArXiv/OSF", re.compile(r"^10\.31234/", re.I)),
    ("doi:OSF preprint", re.compile(r"^10\.31219/osf\.io/", re.I)),
    ("doi:OSF preprint", re.compile(r"^10\.31235/osf\.io/", re.I)),
    ("doi:OSF", re.compile(r"^10\.17605/osf\.io/", re.I)),
    ("doi:Authorea", re.compile(r"^10\.22541/", re.I)),
    ("doi:Preprints.org", re.compile(r"^10\.20944/preprints", re.I)),
    ("doi:JMIR preprints", re.compile(r"^10\.2196/preprints", re.I)),
    ("doi:arXiv", re.compile(r"^10\.48550/arxiv", re.I)),
    ("doi:PeerJ preprints", re.compile(r"^10\.7287/peerj\.preprints", re.I)),
    ("doi:ChemRxiv", re.compile(r"^10\.26434/chemrxiv", re.I)),
    ("doi:Research Square", re.compile(r"^10\.21203/rs\.", re.I)),
)

PREPRINT_VENUE_MARKERS = (
    "biorxiv",
    "medrxiv",
    "psyarxiv",
    "chemrxiv",
    "authorea",
    "osf preprints",
    "preprints.org",
    "research square",
    "researchsquare",
    "openrxiv",
)

PREPRINT_URL_MARKERS = (
    "biorxiv.org",
    "medrxiv.org",
    "psyarxiv.com",
    "osf.io/preprints",
    "arxiv.org",
    "preprints.org",
    "chemrxiv.org",
    "authorea.com",
    "researchsquare.com",
)


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower(value: object) -> str:
    return clean(value).lower()


def add_signal(signals: list[str], signal: str) -> None:
    if signal and signal not in signals:
        signals.append(signal)


def classify_publication_stage(row: Mapping[str, object]) -> dict[str, object]:
    """Classify whether a metadata row is a preprint record.

    URL-only preprint signals are treated as weak because a published article
    can legitimately carry a preprint PDF URL while the DOI itself is published.
    """

    doi = lower(row.get("doi", ""))
    publication_type = lower(row.get("publication_type", ""))
    journal = lower(row.get("study_journal", ""))
    publisher = lower(row.get("publisher", ""))
    url_text = " ".join(
        lower(row.get(field, ""))
        for field in (
            "best_pdf_url",
            "pdf_url_candidates",
            "probable_pdf_url_candidates",
            "other_url_candidates",
            "open_access_url",
        )
    )

    strong_signals: list[str] = []
    weak_signals: list[str] = []

    for label, pattern in PREPRINT_DOI_PATTERNS:
        if pattern.search(doi):
            add_signal(strong_signals, label)

    if "posted-content" in publication_type:
        add_signal(strong_signals, "publication_type:posted-content")
    elif "preprint" in publication_type:
        add_signal(strong_signals, "publication_type:preprint")

    venue_text = f"{journal} {publisher}"
    for marker in PREPRINT_VENUE_MARKERS:
        if marker in venue_text:
            add_signal(strong_signals, f"venue:{marker}")

    for marker in PREPRINT_URL_MARKERS:
        if marker in url_text:
            add_signal(weak_signals, f"url:{marker}")

    is_preprint = bool(strong_signals)
    all_signals = strong_signals + [signal for signal in weak_signals if signal not in strong_signals]
    return {
        "publication_stage": "preprint" if is_preprint else "published",
        "is_preprint_like": bool(all_signals),
        "preprint_signal_strength": "strong" if strong_signals else ("weak" if weak_signals else "none"),
        "preprint_detection_basis": " | ".join(all_signals),
    }
