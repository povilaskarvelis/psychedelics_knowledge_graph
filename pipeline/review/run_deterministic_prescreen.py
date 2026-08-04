#!/usr/bin/env python3
"""Run deterministic title/abstract pre-screening on the unified corpus tables."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

try:
    from pipeline.ingest.preprint_detection import classify_publication_stage
    from pipeline.review.deterministic_prescreen_rules import (
        deterministic_prescreen_decision,
        normalize_doi,
    )
    from pipeline.workflow.decision_state import (
        ActiveArtifact,
        included_dois_from_candidate,
        reconcile_workflow_decision,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.preprint_detection import classify_publication_stage
    from pipeline.review.deterministic_prescreen_rules import (
        deterministic_prescreen_decision,
        normalize_doi,
    )
    from pipeline.workflow.decision_state import (
        ActiveArtifact,
        included_dois_from_candidate,
        reconcile_workflow_decision,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_PAPERS_TABLE = DEFAULT_CORPUS_DIR / "candidate_papers.parquet"
DEFAULT_CONTEXTS_TABLE = DEFAULT_CORPUS_DIR / "candidate_contexts.parquet"
DEFAULT_DECISIONS_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_decisions.parquet"
DEFAULT_SUMMARY_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_summary.parquet"
DEFAULT_DOMAIN_ROUTING_TABLE = DEFAULT_CORPUS_DIR / "paper_domain_routing_gemini.parquet"
DEFAULT_EXTRACTION_ROUTES_TABLE = DEFAULT_CORPUS_DIR / "paper_extraction_routes.parquet"
DEFAULT_EXTRACTION_TASKS_JSONL = (
    ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
)
DEFAULT_RECONCILIATION_REPORT = DEFAULT_CORPUS_DIR / "prescreen_workflow_reconciliation.json"
TABLE_VERSION = "0.3"
RULE_VERSION = "deterministic_prescreen_v2_9_20260722"
MINIMUM_ABSTRACT_WORD_COUNT = 50
ENGLISH_LANGUAGE_CODES = {"en", "eng", "english"}
CANDIDATE_PRESCREEN_DEFAULTS = {
    "prescreen_retained_for_extraction_candidate": False,
    "prescreen_decisions": "",
    "prescreen_actions": "",
    "prescreen_reasons": "",
    "prescreen_routing_tags": "",
    "prescreen_table_version": "",
    "prescreen_rule_version": "",
    "prescreen_run_id": "",
    "prescreen_updated_at_utc": "",
    "prescreen_has_abstract": False,
    "prescreen_abstract_word_count": 0,
    "pipeline_exclusion_stage": "",
    "pipeline_exclusion_reason": "",
    "pipeline_exclusion_decision_source": "",
}
SCREENING_FIELDS = [
    "study_title",
    "study_year",
    "authors",
    "abstract",
    "study_journal",
    "journal_volume",
    "journal_issue",
    "journal_pages",
    "publication_type",
    "publication_date",
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "trial_registry_ids",
    "mesh_terms",
    "keywords",
    "publisher",
    "language",
    "metadata_enrichment_status",
    "metadata_enrichment_run_id",
]

NON_PAPER_CONTAINER_PUBLICATION_TYPES = {
    "component",
    "journal",
    "journal-issue",
    "journal-volume",
    "paratext",
    "proceedings-series",
    "report-component",
}
NON_SOURCE_PUBLICATION_TYPES = {
    "book chapter",
    "book-chapter",
    "chapter",
    "comment",
    "commentary",
    "conference abstract",
    "conference-abstract",
    "conference paper",
    "conference-paper",
    "dissertation",
    "dispatch",
    "editorial",
    "insight",
    "insight article",
    "introductory journal article",
    "letter",
    "meeting abstract",
    "news",
    "newspaper article",
    "poster abstract",
    "peer review",
    "peer-review",
    "perspective",
    "thesis",
    "viewpoint",
    "visual essay",
}
AMBIGUOUS_NARRATIVE_PUBLICATION_TYPES = {
    "comment",
    "commentary",
    "dispatch",
    "editorial",
    "insight",
    "insight article",
    "perspective",
    "viewpoint",
}
EVIDENCE_BEARING_PUBLICATION_PATTERNS = (
    re.compile(r"\bcase reports?\b", re.IGNORECASE),
    re.compile(r"\bclinical trial\b", re.IGNORECASE),
    re.compile(r"\brandomi[sz]ed controlled trial\b", re.IGNORECASE),
    re.compile(r"\bobservational study\b", re.IGNORECASE),
    re.compile(r"\bcomparative study\b", re.IGNORECASE),
    re.compile(r"\bmeta-analysis\b", re.IGNORECASE),
    re.compile(r"\bsystematic review\b", re.IGNORECASE),
    re.compile(r"\bresearch article\b", re.IGNORECASE),
)
EVIDENCE_BEARING_TEXT_PATTERNS = (
    re.compile(r"\bcase (?:report|series)\b", re.IGNORECASE),
    re.compile(r"\bwe (?:report|describe|present) (?:a|an|the|two|three|four|five) case\b", re.IGNORECASE),
    re.compile(r"\bwe (?:enrolled|randomi[sz]ed|recruited|analysed|analyzed)\b", re.IGNORECASE),
    re.compile(r"\bparticipants? (?:received|were assigned|were randomi[sz]ed|completed)\b", re.IGNORECASE),
    re.compile(r"\bpatients? (?:received|were treated|were assigned|were randomi[sz]ed)\b", re.IGNORECASE),
    re.compile(r"\b(?:results?|findings?)\s*:\s*", re.IGNORECASE),
)
OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES = {
    "abstract book entry": "conference_abstract",
    "book": "book_or_monograph",
    "book chapter": "book_chapter",
    "book-chapter": "book_chapter",
    "chapter": "book_chapter",
    "conference abstract": "conference_abstract",
    "conference-abstract": "conference_abstract",
    "conference paper": "conference_paper",
    "conference-paper": "conference_paper",
    "conference proceedings": "conference_paper",
    "proceedings article": "conference_paper",
    "proceedings-article": "conference_paper",
    "conference poster": "conference_poster",
    "conference-poster": "conference_poster",
    "commentary": "commentary",
    "dissertation": "dissertation",
    "data set": "dataset_or_data_deposit",
    "dataset": "dataset_or_data_deposit",
    "dispatch": "commentary",
    "insight": "commentary",
    "insight article": "commentary",
    "meeting abstract": "conference_abstract",
    "monograph": "book_or_monograph",
    "perspective": "commentary",
    "poster abstract": "conference_abstract",
    "poster": "conference_poster",
    "peer review": "peer_review",
    "peer-review": "peer_review",
    "software": "dataset_or_data_deposit",
    "thesis": "dissertation",
    "viewpoint": "commentary",
    "visual essay": "visual_essay",
}
OUT_OF_SCOPE_PUBLICATION_FORMAT_DOI_PATTERNS = (
    # Psychopharmacology Institute Quick Takes are educational summaries of
    # other publications, not the underlying evidence report.
    (
        re.compile(r"^10\.64239/pi-qt\d+$", re.IGNORECASE),
        "commentary",
    ),
    (
        re.compile(r"^10\.17632/", re.IGNORECASE),
        "dataset_or_data_deposit",
    ),
    # A 10.5281 DOI identifies a Zenodo repository object rather than the
    # canonical journal report. Article-shaped deposits remain repository
    # records; a separately discovered journal DOI is handled as its own paper.
    (
        re.compile(r"^10\.5281/zenodo\.", re.IGNORECASE),
        "repository_deposit",
    ),
    # PsycEXTRA e-series DOIs identify indexed database/repository records,
    # including NIDA monograph chapters, rather than canonical source articles.
    (
        re.compile(r"^10\.1037/e\d", re.IGNORECASE),
        "bibliographic_repository_record",
    ),
    (
        re.compile(r"^10\.25772/", re.IGNORECASE),
        "dissertation",
    ),
    (
        re.compile(r"^10\.14288/1\.", re.IGNORECASE),
        "dissertation",
    ),
    (
        re.compile(r"^10\.26226/morressier\.", re.IGNORECASE),
        "conference_abstract",
    ),
    # European Psychiatry abstract-book blocks whose PII-style DOI ranges are
    # shared with the journal and therefore mislabeled as ordinary articles by
    # some providers. Adjacent regular-issue years/ranges are not matched.
    (
        re.compile(r"^10\.1016/s0924-9338\(02\)8\d{4}-[0-9x]$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/s0924-9338\(12\)7\d{4}-[0-9x]$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/s0924-9338\(15\)3\d{4}-[0-9x]$", re.IGNORECASE),
        "conference_abstract",
    ),
    # Frontiers assigns the 10.3389/conf.* namespace to Event Abstracts, which
    # its landing pages explicitly distinguish from peer-reviewed articles.
    (
        re.compile(r"^10\.3389/conf\.", re.IGNORECASE),
        "conference_abstract",
    ),
    # F1000 uses this DOI namespace for its poster objects rather than its
    # peer-reviewed F1000Research articles.
    (
        re.compile(r"^10\.7490/f1000research\.", re.IGNORECASE),
        "conference_poster",
    ),
    # The Japanese Pharmacological Society assigns this namespace to items in
    # its annual-meeting proceedings rather than to ordinary journal articles.
    (
        re.compile(r"^10\.1254/jpssuppl\.", re.IGNORECASE),
        "conference_abstract",
    ),
    # FASEB annual-meeting abstracts use volume/supplement or volume/issue/A-page
    # identifiers. Ordinary FASEB research articles use the 10.1096/fj.* block.
    (
        re.compile(
            r"^10\.1096/fasebj\.(?:\d{4}\.)?\d+\.(?:s\d+\.|\d+\.a\d)",
            re.IGNORECASE,
        ),
        "conference_abstract",
    ),
    # BMC/Springer supplement contributions use A/P/L item suffixes for
    # abstracts, posters, and lectures (for example, -S1-A33 or -S4-P10).
    (
        re.compile(r"^10\.1186/.+-s\d+-(?:a|p|l)\d+$", re.IGNORECASE),
        "conference_abstract",
    ),
    # Named BMJ congress series. The event token is part of the DOI, so this
    # does not affect ordinary articles in the same journals.
    (
        re.compile(
            r"^10\.1136/[a-z0-9-]+-(?:eular|esra|eahp|sti|europaediatrics)\.\d+$",
            re.IGNORECASE,
        ),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1136/sextrans-icar-\d{4}\.\d+$", re.IGNORECASE),
        "conference_abstract",
    ),
    # STI abstract supplements use an article-level DOI plus a final abstract
    # number. Normal STI articles stop before that final dotted number.
    (
        re.compile(r"^10\.1136/sextrans-\d{4}-\d+[a-z]?\.\d+$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1093/ijnp/[a-z]{4}\d{3}\.\d{1,4}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1007/7854_\d{4}_\d+$", re.IGNORECASE),
        "book_chapter",
    ),
    # Elsevier B978 identifiers are chapters/entries within ISBN-addressed
    # books or abstract volumes, not standalone journal reports.
    (
        re.compile(r"^10\.1016/b978-", re.IGNORECASE),
        "book_chapter",
    ),
    (
        re.compile(r"^10\.17579/abstractbook", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.17579/sepd\d{4}[op]\d+", re.IGNORECASE),
        "conference_abstract",
    ),
    # Publisher-verified conference collections. These patterns are scoped to
    # DOI blocks used by the named collections, not to their journals overall.
    # Neuroscience Applied: ECNP congress/workshop abstract collections.
    (
        re.compile(r"^10\.1016/j\.nsa\.2022\.100\d{3}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/j\.nsa\.2023\.(?:102|103)\d{3}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/j\.nsa\.2024\.(?:103|104)\d{3}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/j\.nsa\.2025\.(?:105|106)\d{3}$", re.IGNORECASE),
        "conference_abstract",
    ),
    # IBRO 11th World Congress of Neuroscience supplement (volume 15, S1).
    (
        re.compile(r"^10\.1016/j\.ibneur\.2023\.08\.\d{3,4}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1017/.+\.pr\d+$", re.IGNORECASE),
        "peer_review",
    ),
    # DOI namespaces dedicated to proceedings series. These are deliberately
    # narrower than publisher prefixes so ordinary articles from the same
    # publishers are not excluded.
    (
        re.compile(r"^10\.1051/(?:bioconf|e3sconf|epjconf|matecconf)/", re.IGNORECASE),
        "conference_paper",
    ),
    (
        re.compile(r"^10\.1088/(?:1742-6596|1755-1315|1757-899x)/", re.IGNORECASE),
        "conference_paper",
    ),
    (
        re.compile(r"^10\.30955/gnc", re.IGNORECASE),
        "conference_paper",
    ),
    (
        re.compile(r"^10\.32470/ccn\.", re.IGNORECASE),
        "conference_paper",
    ),
    # Explicit supplement tokens in an item DOI identify contributions to a
    # journal supplement. In this corpus these are overwhelmingly meeting
    # abstracts; the broader format label remains accurate for the few review
    # or article-shaped supplement contributions.
    (
        re.compile(
            r"(?:^|[._/-])(?:supplement(?:ary)?|suppl)(?:[._/-]|$)",
            re.IGNORECASE,
        ),
        "supplement_issue_contribution",
    ),
)

# Some publishers share a DOI prefix between journals and proceedings. Exclude
# only when both the DOI family and source metadata independently identify a
# conference venue. This protects ordinary AIP and IEEE journal articles and
# avoids relying on venue text alone, which is occasionally misassigned.
CORROBORATED_CONFERENCE_VENUE_PATTERNS = (
    (
        re.compile(r"^10\.1063/1\.", re.IGNORECASE),
        re.compile(r"^aip conference proceedings$", re.IGNORECASE),
    ),
    (
        re.compile(r"^10\.1109/", re.IGNORECASE),
        re.compile(r"\bconference\b", re.IGNORECASE),
    ),
    # The publisher uses this DOI namespace for contributions to its dated
    # InterConf scientific collections. Crossref labels the objects as generic
    # journal articles, so the DOI family and collection title are both needed.
    (
        re.compile(r"^10\.51582/interconf\.", re.IGNORECASE),
        re.compile(r"^InterConf(?:\+)?$", re.IGNORECASE),
    ),
)

# Some conference-abstract supplements share the journal's normal DOI prefix
# and Crossref's generic `journal-article` type. Canonical issue metadata is the
# safe discriminator; a DOI-suffix heuristic would also remove regular papers.
CORROBORATED_CONFERENCE_SUPPLEMENT_PATTERNS = (
    (
        re.compile(r"^European Psychiatry$", re.IGNORECASE),
        re.compile(r"^S\d+$", re.IGNORECASE),
        re.compile(r"^S\d+(?:-S?\d+)?$", re.IGNORECASE),
    ),
)
SINGLE_PAGE_SUPPLEMENT_PAGES_RE = re.compile(
    r"^S(?P<first>\d+)(?:-S?(?P<last>\d+))?$",
    re.IGNORECASE,
)

# Exact article-number ranges assigned by Elsevier to the NPS conference
# sections of the mixed-content ETDAH volumes. Keeping the bounds explicit
# avoids excluding the research and review articles in those same volumes.
VERIFIED_CONFERENCE_COLLECTION_DOI_RANGES = (
    (
        re.compile(r"^10\.1016/j\.etdah\.2023\.(?P<article_number>\d{6})$", re.IGNORECASE),
        100061,
        100131,
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1016/j\.etdah\.2025\.(?P<article_number>\d{6})$", re.IGNORECASE),
        100188,
        100265,
        "conference_abstract",
    ),
)
VISUAL_ESSAY_TEXT_RE = re.compile(r"\bvisual essay\b", re.IGNORECASE)
NON_EVIDENCE_TITLE_PATTERNS = (
    re.compile(r"\bauthor correction\b", re.IGNORECASE),
    re.compile(r"\bcorrection:\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bcorrigendum\b", re.IGNORECASE),
    re.compile(r"\bdecision letter for\b", re.IGNORECASE),
    re.compile(r"\breview for [\"“]", re.IGNORECASE),
    re.compile(r"\bfaculty opinions recommendation\b", re.IGNORECASE),
    re.compile(r"\bsupplementary material for\b", re.IGNORECASE),
    re.compile(
        r"(?:^|[.:;–—-]\s+)\s*(?:supplementary|supplemental|supporting)\s+"
        r"(?:materials?|information|data|files?|figures?|tables?|appendi(?:x|ces))\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bstudy protocol\b", re.IGNORECASE),
    re.compile(r"\btrial protocol\b", re.IGNORECASE),
    re.compile(r"\bprotocol for\b", re.IGNORECASE),
    re.compile(r"\bstudy flow chart\b", re.IGNORECASE),
    re.compile(r"\bconsort diagram\b", re.IGNORECASE),
    re.compile(r"\bstudy-related adverse events\b", re.IGNORECASE),
    re.compile(r"\bsupporting information\b", re.IGNORECASE),
    re.compile(r"\bsupplementary information\b", re.IGNORECASE),
    re.compile(r"\bsupplemental information\b", re.IGNORECASE),
    re.compile(r"\bsupplementary table\b", re.IGNORECASE),
    re.compile(r"\bsupplemental table\b", re.IGNORECASE),
    re.compile(r"\btable\s*\d+[_:]", re.IGNORECASE),
    re.compile(r"\.xlsx\b", re.IGNORECASE),
    re.compile(r"\bprism file\b", re.IGNORECASE),
)
NON_EVIDENCE_PUBLICATION_PATTERNS = (
    re.compile(r"\bpublished erratum\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bretracted publication\b", re.IGNORECASE),
    re.compile(r"\bretraction\b", re.IGNORECASE),
    re.compile(r"\bclinical trial protocol\b", re.IGNORECASE),
    re.compile(r"\bdataset\b", re.IGNORECASE),
)
NON_EVIDENCE_TEXT_PATTERNS = (
    re.compile(r"\bpatent highlight\b", re.IGNORECASE),
    re.compile(r"\bthis theoretical article\b", re.IGNORECASE),
)
NON_EVIDENCE_SOURCE_PATTERNS = (
    re.compile(r"\bbrown university(?: child & adolescent)? psychopharmacology update\b", re.IGNORECASE),
)
NUMBERED_TITLE_TOKEN_RE = re.compile(
    r"^\s*(?:abstract\s+)?(?P<number>\d{1,4})(?P<sep>[.)\]:])?\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)
NUMBERED_TITLE_PROTECTED_REST_PATTERNS = (
    re.compile(r"^(?:hz|khz|mhz|ghz)\b", re.IGNORECASE),
    re.compile(r"^(?:mg|ug|µg|μg|g|kg|ml|mL|l)\b", re.IGNORECASE),
    re.compile(r"^(?:years?|months?|weeks?|days?|hours?|minutes?|mins?)\b", re.IGNORECASE),
    re.compile(r"^%|\bpercent\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS = (
    re.compile(r"\bannual meeting\b", re.IGNORECASE),
    re.compile(r"\bscientific meeting\b", re.IGNORECASE),
    re.compile(r"\bconference abstracts?\b", re.IGNORECASE),
    re.compile(r"\bconference proceedings?\b", re.IGNORECASE),
    re.compile(r"\bcongress\b", re.IGNORECASE),
    re.compile(r"\bsymposium\b", re.IGNORECASE),
    re.compile(r"\bposter\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_PUBLICATION_PATTERNS = (
    re.compile(r"\bconference\b", re.IGNORECASE),
    re.compile(r"\bmeeting abstract\b", re.IGNORECASE),
    re.compile(r"\bcongress\b", re.IGNORECASE),
    re.compile(r"\bposter\b", re.IGNORECASE),
    re.compile(r"\bproceedings\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_JOURNAL_PATTERNS = (
    re.compile(
        r"\bproceedings?\s+(?:for|of)\s+(?:the\s+)?"
        r"(?:annual|scientific)?\s*meeting\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:annual|scientific)\s+meeting\b", re.IGNORECASE),
    re.compile(r"\bconference proceedings?\b", re.IGNORECASE),
    re.compile(r"\binternational journal of neuropsychopharmacology\b", re.IGNORECASE),
    re.compile(r"\bcns spectrums\b", re.IGNORECASE),
    re.compile(r"\bjournal of clinical and translational science\b", re.IGNORECASE),
    re.compile(r"\bbiological psychiatry\b", re.IGNORECASE),
    re.compile(r"\beuropean psychiatry\b", re.IGNORECASE),
    re.compile(r"\beuropean journal of pain\b", re.IGNORECASE),
    re.compile(r"\bjournal of urology\b", re.IGNORECASE),
    re.compile(r"\bthe journal of urology\b", re.IGNORECASE),
    re.compile(r"\bjournal of burn care\b", re.IGNORECASE),
    re.compile(r"\bsleep\b", re.IGNORECASE),
    re.compile(r"\bjournal of the international neuropsychological society\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_DOI_PATTERNS = (
    re.compile(r"^10\.1093/(?:ijnp|sleep|jbcr)/[a-z]{4}\d{3}\.\d{1,4}$", re.IGNORECASE),
    re.compile(r"^10\.1017/(?:cts|s1092852920)\.?\d*", re.IGNORECASE),
    re.compile(r"^10\.1016/j\.biopsych\.\d{4}\.\d{2}\.\d{2,4}$", re.IGNORECASE),
    re.compile(r"^10\.1016/s\d{4}-\d{4}\(\d{2}\)\d{5}-\d$", re.IGNORECASE),
    re.compile(r"^10\.1136/[a-z0-9-]+\.\d{1,4}$", re.IGNORECASE),
)
CODED_CONFERENCE_TITLE_RE = re.compile(
    r"^\s*(?:AS|CS|EPA|P|PW|O|OP|PL|S)[-.]?\d+(?:[-.]S?\d+)*(?:\s|[\u2000-\u206f])",
    re.IGNORECASE,
)
GENERIC_CODED_CONFERENCE_TITLE_RE = re.compile(
    r"^\s*(?P<code>(?:AS|CS|EPA|P|PW|O|OP|PL|S)(?:[.-]\d+){1,3})"
    r"(?:\s*[-–—:]\s*|\s+)(?P<rest>\S.*)$",
    re.IGNORECASE,
)
CODED_CONFERENCE_DOI_RE = re.compile(
    r"^10\.1136/sextrans-.+\.\d+$",
    re.IGNORECASE,
)
NON_EVIDENCE_DOI_PATTERNS = (
    re.compile(r"^10\.1371/journal\.[^.]+\.\d+\.[fgst]\d+$", re.IGNORECASE),
    re.compile(r"^10\.1021/.+\.s\d+$", re.IGNORECASE),
    re.compile(r"^10\.3389/.+\.s\d+$", re.IGNORECASE),
    re.compile(r"^10\.6084/m9\.figshare", re.IGNORECASE),
)
OUT_OF_SCOPE_ACRONYM_FALSE_POSITIVE_PATTERNS = (
    re.compile(r"\blumpy skin disease\b", re.IGNORECASE),
    re.compile(r"\blumpy skin disease virus\b", re.IGNORECASE),
    re.compile(r"\bLSDV\b", re.IGNORECASE),
)
OUT_OF_SCOPE_PRODUCTION_METHOD_FOCUS_PATTERNS = (
    re.compile(r"\bbiosynthesi[sz](?:e|ed|es|ing|s)?\b", re.IGNORECASE),
    re.compile(r"\bbioproduction\b", re.IGNORECASE),
    re.compile(r"\bmetabolic engineering\b", re.IGNORECASE),
    re.compile(r"\bsynthetic biology\b", re.IGNORECASE),
    re.compile(r"\bheterologous expression\b", re.IGNORECASE),
    re.compile(r"\bfermentation\b", re.IGNORECASE),
    re.compile(r"\bproduction (?:of|methods?|platform|pathway|process)\b", re.IGNORECASE),
    re.compile(r"\bsynthesi[sz](?:e|ed|es|ing|s)? pathway\b", re.IGNORECASE),
)
OUT_OF_SCOPE_PRODUCTION_METHOD_CONTEXT_PATTERNS = (
    re.compile(r"\bEscherichia coli\b", re.IGNORECASE),
    re.compile(r"\bE\.?\s*coli\b", re.IGNORECASE),
    re.compile(r"\byeast\b", re.IGNORECASE),
    re.compile(r"\bSaccharomyces\b", re.IGNORECASE),
    re.compile(r"\bmicrobial\b", re.IGNORECASE),
    re.compile(r"\bbacterial\b", re.IGNORECASE),
    re.compile(r"\bbiocatalys(?:is|t|tic)\b", re.IGNORECASE),
    re.compile(r"\benzyme engineering\b", re.IGNORECASE),
    re.compile(r"\bengineered (?:strain|host|microorganism|microbe|bacterium|yeast)\b", re.IGNORECASE),
)
OUT_OF_SCOPE_BROAD_NPS_BACKGROUND_PATTERNS = (
    re.compile(r"\bbrief history of [\"'‘’]?(?:new|novel) psychoactive substances\b", re.IGNORECASE),
)
PLACEHOLDER_ABSTRACTS = {
    "abstract not available",
    "international audience",
    "no abstract",
    "no abstract available",
    "not available",
}
CITATION_ONLY_ABSTRACT_PATTERNS = (
    re.compile(r"^\(\d{4}\)\.\s+.+\.\s+.+:\s+vol\.\s+\d+", re.IGNORECASE),
    re.compile(
        r"^[A-Z][A-Za-z& ]+:\s+[A-Za-z]+\s+\d{4}\s+-\s+Volume\s+\d+\s+-\s+Issue\b.*\bdoi\s*:",
        re.IGNORECASE,
    ),
)
ABSTRACT_WORD_RE = re.compile(r"\b\w+(?:[’'-]\w+)*\b", re.UNICODE)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "deterministic_prescreen_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d")


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = clean(value).lower()
    return text in {"1", "true", "yes", "y"}


def abstract_word_count(value: object) -> int:
    """Count Unicode word tokens while keeping hyphenated terms as one word."""

    return len(ABSTRACT_WORD_RE.findall(clean(value)))


def unusable_abstract_reason(value: object) -> str:
    text = re.sub(r"\s+", " ", clean(value)).strip()
    if not text:
        return "No abstract available for title/abstract screening."
    lowered = text.lower().strip(" .[]")
    if lowered in PLACEHOLDER_ABSTRACTS:
        return "Abstract field contains a placeholder rather than a substantive abstract."
    for pattern in CITATION_ONLY_ABSTRACT_PATTERNS:
        if pattern.search(text):
            return "Abstract field contains citation metadata rather than a substantive abstract."
    word_count = abstract_word_count(text)
    if word_count < MINIMUM_ABSTRACT_WORD_COUNT:
        return (
            f"Abstract contains {word_count} words, below the {MINIMUM_ABSTRACT_WORD_COUNT}-word "
            "minimum for deterministic title/abstract screening."
        )
    return ""


def split_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = re.split(r"\s*[|,;]\s*", clean(value))
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = clean(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def join_values(values: Iterable[object]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return " | ".join(out)


def stable_id(*parts: object) -> str:
    payload = "\u241f".join(clean(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(clean(line))
        if doi and not doi.startswith("#"):
            dois.add(doi)
    return dois


def scoped_dois_from_args(args: argparse.Namespace) -> set[str]:
    dois: set[str] = set()
    doi_file = clean(getattr(args, "doi_file", ""))
    if doi_file:
        dois.update(read_doi_file(Path(doi_file).resolve()))
    for value in getattr(args, "doi", []) or []:
        doi = normalize_doi(clean(value))
        if doi:
            dois.add(doi)
    return dois


def filter_table_to_dois(df: pd.DataFrame, dois: set[str]) -> pd.DataFrame:
    if df.empty or "doi" not in df.columns or not dois:
        return df
    doi_values = df["doi"].map(lambda value: normalize_doi(clean(value)))
    return df[doi_values.isin(dois)].copy()


def existing_run_id(decisions_df: pd.DataFrame) -> str:
    if decisions_df.empty or "run_id" not in decisions_df.columns:
        return ""
    run_ids = [clean(value) for value in decisions_df["run_id"].tolist()]
    run_ids = [value for value in run_ids if value]
    if not run_ids:
        return ""
    return Counter(run_ids).most_common(1)[0][0]


def merge_scoped_decisions(
    existing_rows: list[dict],
    updated_rows: list[dict],
    *,
    scoped_dois: set[str],
) -> tuple[list[dict], int]:
    retained_existing: list[dict] = []
    replaced = 0
    for row in existing_rows:
        doi = normalize_doi(clean(row.get("doi", "")))
        if doi in scoped_dois:
            replaced += 1
            continue
        retained_existing.append(row)
    return [*retained_existing, *updated_rows], replaced


def rows_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if doi and doi not in out:
            out[doi] = row
    return out


def contexts_by_doi(contexts_df: pd.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if contexts_df.empty or "doi" not in contexts_df.columns:
        return out
    for row in contexts_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi:
            continue
        out[doi].append(row)
    return out


def compact_contexts(contexts: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in contexts:
        item = {
            "compound": clean(row.get("compound", "")),
            "entity": clean(row.get("entity", "")),
            "entity_type": clean(row.get("entity_type", "")),
        }
        marker = (item["compound"], item["entity"], item["entity_type"])
        if not item["compound"] and not item["entity"]:
            continue
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def candidate_screening_row(paper: dict) -> dict:
    """Return prescreen input from the materialized candidate ledger only."""
    doi = normalize_doi(clean(paper.get("doi", "")))
    row = {"study_doi": doi}
    for field in SCREENING_FIELDS:
        row[field] = clean(paper.get(field, ""))
    return row


def no_usable_abstract_decision(row: dict, reason: str = "") -> dict:
    title = clean(row.get("study_title", ""))
    detail = reason or "No usable abstract is available."
    if title:
        detail += " The title alone did not clearly establish that the record was in scope."
    else:
        detail += " No usable title or abstract was available for screening."
    return {
        "action": "exclude_no_usable_abstract",
        "confidence": 1.0,
        "supporting_quote": title or "not_found",
        "reason": detail,
        "matched_terms": [],
    }


def non_english_language_decision(row: dict) -> dict | None:
    """Exclude records whose bibliographic metadata explicitly identifies a non-English source.

    Blank language metadata remains undecided here.  This rule deliberately
    avoids guessing language from scientific names, symbols, or short titles.
    """

    languages = {value.lower() for value in split_values(row.get("language", ""))}
    if not languages or languages.intersection(ENGLISH_LANGUAGE_CODES):
        return None
    language = join_values(sorted(languages))
    return {
        "action": "exclude_non_english_language",
        "confidence": 1.0,
        "supporting_quote": language,
        "reason": (
            "Bibliographic metadata explicitly identifies the source language as non-English, "
            "outside the project's English-language evidence corpus."
        ),
        "matched_terms": sorted(languages),
    }


def has_substantive_evidence_signal(row: dict) -> bool:
    publication_type = clean(row.get("publication_type", ""))
    title_abstract = " ".join(
        value for value in (clean(row.get("study_title", "")), clean(row.get("abstract", ""))) if value
    )
    return any(pattern.search(publication_type) for pattern in EVIDENCE_BEARING_PUBLICATION_PATTERNS) or any(
        pattern.search(title_abstract) for pattern in EVIDENCE_BEARING_TEXT_PATTERNS
    )


def non_paper_container_without_title_decision(row: dict) -> dict | None:
    title = clean(row.get("study_title", ""))
    if title:
        return None
    publication_types = {value.lower() for value in split_values(row.get("publication_type", ""))}
    if not publication_types.intersection(NON_PAPER_CONTAINER_PUBLICATION_TYPES):
        return None
    publication_type = join_values(sorted(publication_types))
    return {
        "action": "exclude_non_paper_container",
        "confidence": 1.0,
        "supporting_quote": publication_type or "no paper title",
        "reason": (
            "Metadata identifies this DOI as a journal/container record rather than a titled source paper, "
            "and no paper title is available."
        ),
        "matched_terms": sorted(publication_types),
    }


def out_of_scope_publication_format_decision(row: dict) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", ""))).lower()
    title = clean(row.get("study_title", ""))
    abstract = clean(row.get("abstract", ""))
    journal = clean(row.get("study_journal", ""))
    journal_issue = clean(row.get("journal_issue", ""))
    journal_pages = clean(row.get("journal_pages", ""))
    publication_types = {value.lower() for value in split_values(row.get("publication_type", ""))}
    matched_formats = {
        OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES[value]
        for value in publication_types
        if value in OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES
    }
    matched_terms = sorted(
        value for value in publication_types if value in OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES
    )
    if has_substantive_evidence_signal(row):
        protected_types = {
            value
            for value in publication_types
            if OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES.get(value) == "commentary"
        }
        if protected_types:
            matched_formats.discard("commentary")
            matched_terms = [value for value in matched_terms if value not in protected_types]
    for pattern, publication_format in OUT_OF_SCOPE_PUBLICATION_FORMAT_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_formats.add(publication_format)
            matched_terms.append(match.group(0))
    for pattern, first_article, last_article, publication_format in VERIFIED_CONFERENCE_COLLECTION_DOI_RANGES:
        match = pattern.search(doi)
        if not match:
            continue
        article_number = int(match.group("article_number"))
        if first_article <= article_number <= last_article:
            matched_formats.add(publication_format)
            matched_terms.append(
                f"verified_conference_collection:{first_article}-{last_article}"
            )
    for doi_pattern, venue_pattern in CORROBORATED_CONFERENCE_VENUE_PATTERNS:
        doi_match = doi_pattern.search(doi)
        venue_match = venue_pattern.search(journal)
        if doi_match and venue_match:
            matched_formats.add("conference_paper")
            matched_terms.append(f"corroborated_conference_venue:{venue_match.group(0)}")
    for venue_pattern, issue_pattern, pages_pattern in CORROBORATED_CONFERENCE_SUPPLEMENT_PATTERNS:
        venue_match = venue_pattern.search(journal)
        issue_match = issue_pattern.search(journal_issue)
        pages_match = pages_pattern.search(journal_pages)
        if venue_match and (issue_match or pages_match):
            matched_formats.add("conference_abstract")
            matched_terms.append(
                "corroborated_conference_supplement:"
                f"{venue_match.group(0)}:{journal_issue}:{journal_pages}"
            )
    supplement_page_match = SINGLE_PAGE_SUPPLEMENT_PAGES_RE.search(journal_pages)
    if supplement_page_match:
        first_page = supplement_page_match.group("first")
        last_page = supplement_page_match.group("last")
        if not last_page or last_page == first_page:
            matched_formats.add("supplement_issue_contribution")
            matched_terms.append(f"single_page_supplement:{supplement_page_match.group(0)}")
    if VISUAL_ESSAY_TEXT_RE.search(" ".join(value for value in (title, abstract) if value)):
        matched_formats.add("visual_essay")
        matched_terms.append("visual essay")
    if not matched_formats:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title or clean(row.get("publication_type", "")) or doi,
        "reason": (
            "Record is a book/monograph, book chapter, dataset or repository/index deposit, dissertation/thesis, "
            "conference paper, conference/poster/meeting abstract, abstract-book contribution, "
            "journal-supplement contribution, peer-review/decision object, or visual essay rather "
            "than an eligible source article, review, or meta-analysis."
        ),
        "matched_terms": [*sorted(matched_formats), *matched_terms],
    }


def non_evidence_artifact_decision(row: dict) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = clean(row.get("study_title", ""))
    abstract = clean(row.get("abstract", ""))
    publication_type = clean(row.get("publication_type", ""))
    journal = clean(row.get("study_journal", ""))
    publication_types = {value.lower() for value in split_values(publication_type)}
    title_abstract = " ".join(value for value in (title, abstract) if value)
    matched_terms: list[str] = []
    for pattern in NON_EVIDENCE_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_TITLE_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_PUBLICATION_PATTERNS:
        match = pattern.search(publication_type)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_TEXT_PATTERNS:
        match = pattern.search(title_abstract)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_SOURCE_PATTERNS:
        match = pattern.search(journal)
        if match:
            matched_terms.append(match.group(0))
    non_source_publication_types = publication_types.intersection(NON_SOURCE_PUBLICATION_TYPES)
    if has_substantive_evidence_signal(row):
        non_source_publication_types -= AMBIGUOUS_NARRATIVE_PUBLICATION_TYPES
    if non_source_publication_types:
        matched_terms.extend(sorted(non_source_publication_types))
    if not matched_terms:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title or publication_type or doi,
        "reason": (
            "Record is a protocol, correction, review report, patent highlight, pure "
            "letter/editorial/comment/news item, newsletter/update summary, supplementary material, "
            "figure/table/data deposit, retraction, or citation artifact rather than source evidence."
        ),
        "matched_terms": matched_terms,
    }


def numbered_title_metadata(row: dict) -> dict:
    title = clean(row.get("study_title", ""))
    match = NUMBERED_TITLE_TOKEN_RE.search(title)
    if not match:
        return {}
    number_text = match.group("number")
    rest = clean(match.group("rest") or "").lstrip(" -–—:.)]")
    try:
        number = int(number_text)
    except ValueError:
        return {}
    return {
        "number_text": number_text,
        "number": number,
        "separator": clean(match.group("sep") or ""),
        "rest": rest,
        "title": title,
    }


def numbered_title_is_protected(metadata: dict) -> bool:
    if not metadata:
        return True
    number = int(metadata.get("number", 0))
    rest = clean(metadata.get("rest", ""))
    if 1800 <= number <= 2099 and not any(pattern.search(rest) for pattern in NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS):
        return True
    return any(pattern.search(rest) for pattern in NUMBERED_TITLE_PROTECTED_REST_PATTERNS)


def mostly_uppercase(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 12:
        return False
    uppercase = sum(char.isupper() for char in letters)
    return uppercase / len(letters) >= 0.75


def numbered_conference_abstract_decision(row: dict) -> dict | None:
    metadata = numbered_title_metadata(row)
    if not metadata or numbered_title_is_protected(metadata):
        return None

    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = metadata["title"]
    rest = metadata["rest"]
    number = int(metadata["number"])
    separator = clean(metadata.get("separator", ""))
    publication_type = clean(row.get("publication_type", ""))
    journal = clean(row.get("study_journal", ""))
    matched_terms = [f"numbered_title:{metadata['number_text']}"]

    strong_signal = False
    source_signal = False
    for pattern in NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
            strong_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_PUBLICATION_PATTERNS:
        match = pattern.search(publication_type)
        if match:
            matched_terms.append(match.group(0))
            strong_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_terms.append(match.group(0))
            source_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_JOURNAL_PATTERNS:
        match = pattern.search(journal)
        if match:
            matched_terms.append(match.group(0))
            source_signal = True

    title_format_signal = bool(separator) or number >= 20 or mostly_uppercase(rest)
    if not strong_signal and not (source_signal and title_format_signal):
        return None

    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title,
        "reason": (
            "Record appears to be a numbered conference, poster, or meeting abstract "
            "rather than a source article or review."
        ),
        "matched_terms": matched_terms,
    }


def coded_conference_abstract_decision(row: dict) -> dict | None:
    """Exclude journal-supplement abstracts whose title and DOI carry session codes."""

    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = clean(row.get("study_title", ""))
    if CODED_CONFERENCE_DOI_RE.search(doi) and CODED_CONFERENCE_TITLE_RE.search(title):
        return {
            "action": "exclude_non_evidence_artifact",
            "confidence": 1.0,
            "supporting_quote": title,
            "reason": (
                "The coded title and Sexually Transmitted Infections supplement DOI identify a "
                "conference/poster abstract rather than a source article or review."
            ),
            "matched_terms": ["coded_conference_title", "sextrans_supplement_doi"],
        }

    coded_match = GENERIC_CODED_CONFERENCE_TITLE_RE.search(title)
    if not coded_match:
        return None
    publication_type = clean(row.get("publication_type", ""))
    journal = clean(row.get("study_journal", ""))
    matched_terms = [f"coded_conference_title:{coded_match.group('code')}"]
    for value, patterns in (
        (publication_type, NUMBERED_TITLE_CONFERENCE_PUBLICATION_PATTERNS),
        (journal, NUMBERED_TITLE_CONFERENCE_JOURNAL_PATTERNS),
        (doi, NUMBERED_TITLE_CONFERENCE_DOI_PATTERNS),
    ):
        for pattern in patterns:
            match = pattern.search(value)
            if match:
                matched_terms.append(match.group(0))
    if len(matched_terms) == 1:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title,
        "reason": (
            "The coded title and meeting, proceedings, journal, or DOI metadata identify a "
            "conference/poster abstract rather than a source article or review."
        ),
        "matched_terms": matched_terms,
    }


def publication_stage_row(row: dict) -> dict:
    out = dict(row)
    if not clean(out.get("doi", "")):
        out["doi"] = clean(row.get("study_doi", ""))
    return out


def preprint_or_unpublished_decision(row: dict) -> dict | None:
    classification = classify_publication_stage(publication_stage_row(row))
    if clean(classification.get("publication_stage", "")) != "preprint":
        return None
    basis = clean(classification.get("preprint_detection_basis", "")) or "preprint metadata"
    return {
        "action": "exclude_preprint_or_unpublished",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("publication_type", "")) or clean(row.get("study_title", "")) or basis,
        "reason": f"Record appears to be a preprint or unpublished posted-content record: {basis}.",
        "matched_terms": split_values(basis),
    }


def acronym_false_positive_decision(row: dict) -> dict | None:
    text = " ".join(
        clean(row.get(field, ""))
        for field in ("study_title", "abstract", "keywords", "mesh_terms")
    )
    matched_terms: list[str] = []
    for pattern in OUT_OF_SCOPE_ACRONYM_FALSE_POSITIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_terms.append(match.group(0))
    if not matched_terms:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("study_title", "")) or matched_terms[0],
        "reason": (
            "Record uses LSD/LSDV in the veterinary lumpy-skin-disease sense, "
            "not as psychedelic evidence."
        ),
        "matched_terms": matched_terms,
    }


def production_method_false_positive_decision(row: dict) -> dict | None:
    title = clean(row.get("study_title", ""))
    focus_matches: list[str] = []
    context_matches: list[str] = []
    for pattern in OUT_OF_SCOPE_PRODUCTION_METHOD_FOCUS_PATTERNS:
        match = pattern.search(title)
        if match:
            focus_matches.append(match.group(0))
    for pattern in OUT_OF_SCOPE_PRODUCTION_METHOD_CONTEXT_PATTERNS:
        match = pattern.search(title)
        if match:
            context_matches.append(match.group(0))
    if not focus_matches or not context_matches:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": title or focus_matches[0],
        "reason": (
            "The title explicitly identifies both compound production and a microbial/engineered-production "
            "context, making this a high-confidence bioproduction or manufacturing-method record rather than "
            "biological, clinical, pharmacological, or public-health evidence."
        ),
        "matched_terms": [*focus_matches, *context_matches],
    }


def broad_nps_background_false_positive_decision(row: dict) -> dict | None:
    title = clean(row.get("study_title", ""))
    publication_type = clean(row.get("publication_type", ""))
    matched_terms: list[str] = []
    for pattern in OUT_OF_SCOPE_BROAD_NPS_BACKGROUND_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
    if not matched_terms:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": title or matched_terms[0],
        "reason": (
            "Record is a broad historical or editorial overview of new psychoactive substances, "
            "rather than source evidence or a domain-specific evidence synthesis for the knowledge graph."
        ),
        "matched_terms": [*matched_terms, publication_type] if publication_type else matched_terms,
    }


def before_model_exclusion_decision(row: dict) -> dict | None:
    return (
        non_english_language_decision(row)
        or non_paper_container_without_title_decision(row)
        or out_of_scope_publication_format_decision(row)
        or non_evidence_artifact_decision(row)
        or numbered_conference_abstract_decision(row)
        or coded_conference_abstract_decision(row)
        or preprint_or_unpublished_decision(row)
        or acronym_false_positive_decision(row)
        or production_method_false_positive_decision(row)
        or broad_nps_background_false_positive_decision(row)
    )


def final_prescreen_fields(decision: dict) -> tuple[str, str, str]:
    action = clean(decision.get("action", ""))
    if action.startswith("exclude"):
        return ("exclude", action, clean(decision.get("reason", "")))
    return ("retain", "retain_for_screening", clean(decision.get("reason", "")))


def build_prescreen_decisions(
    papers_df: pd.DataFrame,
    contexts_df: pd.DataFrame,
    *,
    run_id: str,
    generated_at_utc: str,
    progress_every: int = 0,
) -> list[dict]:
    contexts_lookup = contexts_by_doi(contexts_df)
    rows: list[dict] = []

    paper_records = papers_df.to_dict("records")
    for paper_index, paper in enumerate(paper_records, start=1):
        if progress_every and paper_index % progress_every == 0:
            print(f"Processed {paper_index:,}/{len(paper_records):,} candidate papers...", flush=True)
        doi = normalize_doi(clean(paper.get("doi", "")))
        if not doi:
            continue
        paper_contexts = compact_contexts(contexts_lookup.get(doi, []))
        screening_row = candidate_screening_row(paper)
        screening_abstract_word_count = abstract_word_count(screening_row.get("abstract", ""))
        abstract_status_reason = unusable_abstract_reason(screening_row.get("abstract", ""))
        has_abstract = not bool(abstract_status_reason)
        before_model_decision = before_model_exclusion_decision(screening_row)
        if before_model_decision:
            decision = before_model_decision
        elif not has_abstract:
            decision = no_usable_abstract_decision(screening_row, abstract_status_reason)
        else:
            decision = deterministic_prescreen_decision(screening_row)
        prescreen_decision, prescreen_action, prescreen_reason = final_prescreen_fields(decision)
        retained_for_screening = prescreen_decision == "retain" and not clean(
            decision.get("action", "")
        ).startswith("exclude")
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "rule_version": RULE_VERSION,
                "run_id": run_id,
                "generated_at_utc": generated_at_utc,
                "prescreen_decision_id": stable_id(run_id, doi),
                "doi": doi,
                "study_title": clean(screening_row.get("study_title", "")),
                "study_year": clean(screening_row.get("study_year", "")),
                "has_abstract": has_abstract,
                "abstract_char_count": len(clean(screening_row.get("abstract", ""))),
                "abstract_word_count": screening_abstract_word_count,
                "candidate_context_count": len(paper_contexts),
                "context_compounds": join_values(context.get("compound", "") for context in paper_contexts),
                "context_entities": join_values(context.get("entity", "") for context in paper_contexts),
                "context_entity_types": join_values(context.get("entity_type", "") for context in paper_contexts),
                "deterministic_action": clean(decision.get("action", "")),
                "deterministic_reason": clean(decision.get("reason", "")),
                "deterministic_confidence": float(decision.get("confidence", 0) or 0),
                "deterministic_matched_terms": join_values(decision.get("matched_terms", [])),
                "deterministic_supporting_quote": clean(decision.get("supporting_quote", "")),
                "prescreen_decision": prescreen_decision,
                "prescreen_action": prescreen_action,
                "prescreen_reason": prescreen_reason,
                "retained_for_screening": retained_for_screening,
                # Compatibility alias used by existing downstream queue builders.
                "retained_for_extraction_candidate": retained_for_screening,
                "metadata_enrichment_status": clean(screening_row.get("metadata_enrichment_status", "")),
                "metadata_enrichment_run_id": clean(screening_row.get("metadata_enrichment_run_id", "")),
            }
        )
    return rows


def validate_prescreen_decisions(decisions: list[dict], *, expected_dois: set[str] | None = None) -> None:
    errors: list[str] = []
    dois = [normalize_doi(row.get("doi", "")) for row in decisions]
    blank_dois = sum(not doi for doi in dois)
    doi_counts = Counter(doi for doi in dois if doi)
    duplicate_dois = sorted(doi for doi, count in doi_counts.items() if count > 1)
    if blank_dois:
        errors.append(f"{blank_dois} decision rows have blank DOIs")
    if duplicate_dois:
        errors.append(f"duplicate decision DOIs: {duplicate_dois[:10]}")
    if expected_dois is not None and set(dois) != expected_dois:
        missing = sorted(expected_dois - set(dois))
        extra = sorted(set(dois) - expected_dois)
        errors.append(f"DOI coverage mismatch: missing={missing[:10]} extra={extra[:10]}")

    for row in decisions:
        doi = normalize_doi(row.get("doi", "")) or "<blank>"
        decision = clean(row.get("prescreen_decision", ""))
        action = clean(row.get("prescreen_action", ""))
        retained = bool(row.get("retained_for_screening", False))
        extraction_candidate = bool(row.get("retained_for_extraction_candidate", False))
        if decision not in {"retain", "exclude"}:
            errors.append(f"{doi}: unsupported prescreen decision {decision!r}")
        if decision == "retain" and action != "retain_for_screening":
            errors.append(f"{doi}: retained decision has action {action!r}")
        if decision == "exclude" and not action.startswith("exclude_"):
            errors.append(f"{doi}: excluded decision has action {action!r}")
        expected_retained = decision == "retain"
        if "retained_for_screening" in row and retained != expected_retained:
            errors.append(f"{doi}: retained flags conflict with decision {decision!r}")
        if "retained_for_extraction_candidate" in row and extraction_candidate != expected_retained:
            errors.append(f"{doi}: extraction-candidate flag conflicts with decision {decision!r}")
        if (
            clean(row.get("rule_version", "")) == RULE_VERSION
            and expected_retained
            and not bool(row.get("has_abstract", False))
        ):
            errors.append(f"{doi}: title-only record was retained despite the no-abstract exclusion policy")
        if (
            clean(row.get("rule_version", "")) == RULE_VERSION
            and expected_retained
            and int(row.get("abstract_word_count", 0) or 0) < MINIMUM_ABSTRACT_WORD_COUNT
        ):
            errors.append(
                f"{doi}: record with fewer than {MINIMUM_ABSTRACT_WORD_COUNT} abstract words was retained"
            )

    if errors:
        preview = "\n".join(errors[:25])
        suffix = f"\n... and {len(errors) - 25} more" if len(errors) > 25 else ""
        raise ValueError(f"Deterministic prescreen validation failed:\n{preview}{suffix}")


def candidate_prescreen_updates(
    decisions: list[dict],
    candidate_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    candidate_by_doi = rows_by_doi(candidate_df if candidate_df is not None else pd.DataFrame())
    rows: list[dict] = []
    for row in decisions:
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        excluded = clean(row.get("prescreen_decision", "")) == "exclude"
        existing_stage = clean(candidate_by_doi.get(doi, {}).get("pipeline_exclusion_stage", ""))
        later_exclusion_exists = bool(existing_stage and existing_stage != "prescreen")
        if excluded:
            exclusion_stage: object = "prescreen"
            exclusion_reason: object = clean(row.get("prescreen_reason", ""))
            exclusion_source: object = RULE_VERSION
        elif later_exclusion_exists:
            # Preserve a still-valid decision made by a later evidence stage.
            # pd.NA makes candidate reconciliation leave these cells untouched.
            exclusion_stage = pd.NA
            exclusion_reason = pd.NA
            exclusion_source = pd.NA
        else:
            exclusion_stage = ""
            exclusion_reason = ""
            exclusion_source = ""
        rows.append(
            {
                "doi": doi,
                "prescreen_retained_for_extraction_candidate": bool(
                    row.get("retained_for_extraction_candidate", False)
                ),
                "prescreen_decisions": clean(row.get("prescreen_decision", "")),
                "prescreen_actions": clean(row.get("prescreen_action", "")),
                "prescreen_reasons": clean(row.get("prescreen_reason", "")),
                "prescreen_routing_tags": "",
                "prescreen_table_version": clean(row.get("table_version", "")),
                "prescreen_rule_version": clean(row.get("rule_version", "")),
                "prescreen_run_id": clean(row.get("run_id", "")),
                "prescreen_updated_at_utc": clean(row.get("generated_at_utc", "")),
                "prescreen_has_abstract": bool(row.get("has_abstract", False)),
                "prescreen_abstract_word_count": int(row.get("abstract_word_count", 0) or 0),
                "pipeline_exclusion_stage": exclusion_stage,
                "pipeline_exclusion_reason": exclusion_reason,
                "pipeline_exclusion_decision_source": exclusion_source,
            }
        )
    return pd.DataFrame(rows)


def build_summary_rows(decisions: list[dict], *, run_id: str, generated_at_utc: str) -> list[dict]:
    rows: list[dict] = []

    def add(metric: str, label: str, count: int) -> None:
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "rule_version": RULE_VERSION,
                "run_id": run_id,
                "generated_at_utc": generated_at_utc,
                "scope": "all_papers",
                "metric": metric,
                "label": label,
                "count": int(count),
            }
        )

    add("decisions", "total", len(decisions))
    add("papers", "unique_doi", len({row.get("doi") for row in decisions}))
    add("abstract", "missing", sum(not row.get("has_abstract") for row in decisions))
    add(
        "abstract",
        f"below_{MINIMUM_ABSTRACT_WORD_COUNT}_words",
        sum(
            0 < int(row.get("abstract_word_count", 0) or 0) < MINIMUM_ABSTRACT_WORD_COUNT
            for row in decisions
        ),
    )
    for field in ("prescreen_decision", "prescreen_action", "deterministic_action"):
        for label, count in Counter(clean(row.get(field, "")) for row in decisions).items():
            add(field, label, count)
    return rows


def run(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    decisions_table = Path(args.decisions_table).resolve()
    summary_table = Path(args.summary_table).resolve()
    scoped_dois = scoped_dois_from_args(args)
    existing_decisions_df = read_table(decisions_table) if scoped_dois else pd.DataFrame()
    run_id = clean(args.run_id) or (existing_run_id(existing_decisions_df) if scoped_dois else "") or default_run_id()
    generated_at_utc = now_utc()
    papers_df = read_table(Path(args.papers_table).resolve())
    contexts_df = read_table(Path(args.contexts_table).resolve())

    if papers_df.empty:
        raise SystemExit(f"No rows found in papers table: {args.papers_table}")
    previous_candidate_path = clean(getattr(args, "previous_candidate_table", ""))
    if previous_candidate_path:
        previous_candidate_df = read_table(Path(previous_candidate_path).resolve())
        if previous_candidate_df.empty:
            raise SystemExit(f"No rows found in previous candidate table: {previous_candidate_path}")
    else:
        previous_candidate_df = papers_df
    previous_included_dois = included_dois_from_candidate(
        previous_candidate_df,
        column="prescreen_retained_for_extraction_candidate",
    )
    all_paper_dois = {
        normalize_doi(value)
        for value in papers_df.get("doi", pd.Series(dtype=str)).tolist()
        if normalize_doi(value)
    }
    if scoped_dois:
        if existing_decisions_df.empty:
            raise SystemExit(
                "Scoped deterministic pre-screen updates require an existing decisions table. "
                "Run a full pass first, or omit --doi/--doi-file."
            )
        existing_versions = {
            clean(value)
            for value in existing_decisions_df.get("table_version", pd.Series(dtype=str)).tolist()
            if clean(value)
        }
        if existing_versions != {TABLE_VERSION}:
            raise SystemExit(
                "Scoped deterministic pre-screen updates cannot be merged into an older decision schema. "
                f"Expected table_version={TABLE_VERSION}; found {sorted(existing_versions) or ['missing']}. "
                "Run one full deterministic pre-screen pass first."
            )
        papers_df = filter_table_to_dois(papers_df, scoped_dois)
        contexts_df = filter_table_to_dois(contexts_df, scoped_dois)
        if papers_df.empty:
            raise SystemExit("No matching DOI rows found in the papers table for the requested scoped update.")

    updated_decisions = build_prescreen_decisions(
        papers_df,
        contexts_df,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        progress_every=getattr(args, "progress_every", 0),
    )
    if scoped_dois:
        decisions, replaced_count = merge_scoped_decisions(
            existing_decisions_df.to_dict("records"),
            updated_decisions,
            scoped_dois=scoped_dois,
        )
    else:
        decisions = updated_decisions
        replaced_count = 0
    validate_prescreen_decisions(
        decisions,
        expected_dois=None if scoped_dois else all_paper_dois,
    )
    summary = build_summary_rows(decisions, run_id=run_id, generated_at_utc=generated_at_utc)
    write_table(decisions_table, decisions)
    write_table(summary_table, summary)

    candidate_update: dict = {}
    if not getattr(args, "no_update_candidate_table", False):
        current_included_dois = {
            normalize_doi(row.get("doi", ""))
            for row in decisions
            if clean(row.get("prescreen_decision", "")) == "retain"
            and normalize_doi(row.get("doi", ""))
        }
        active_artifacts: list[ActiveArtifact] = []
        for attribute, kind in (
            ("domain_routing_table", "parquet"),
            ("extraction_routes_table", "parquet"),
            ("extraction_tasks_jsonl", "jsonl"),
        ):
            value = clean(getattr(args, attribute, ""))
            if value:
                active_artifacts.append(ActiveArtifact(Path(value), kind=kind))
        report_value = clean(getattr(args, "reconciliation_report", ""))
        candidate_update = reconcile_workflow_decision(
            candidate_table=Path(args.papers_table).resolve(),
            decision_updates=candidate_prescreen_updates(
                updated_decisions if scoped_dois else decisions,
                papers_df,
            ),
            update_defaults=CANDIDATE_PRESCREEN_DEFAULTS,
            stage="prescreen",
            previous_included_dois=previous_included_dois,
            current_included_dois=current_included_dois,
            active_artifacts=active_artifacts,
            pending_status="prescreen_retained_pending_model_screen",
            excluded_status="prescreen_excluded",
            report_path=Path(report_value) if report_value else None,
            context={
                "prescreen_decisions_table": str(decisions_table),
                "prescreen_run_id": run_id,
                "previous_candidate_table": str(Path(previous_candidate_path).resolve())
                if previous_candidate_path
                else str(Path(args.papers_table).resolve()),
            },
        )

    by_action = Counter(row["prescreen_action"] for row in decisions)
    print(f"Run ID: {run_id}")
    if scoped_dois:
        print(f"Scoped DOI update: requested={len(scoped_dois):,} matched_papers={len(papers_df):,}")
        print(f"Updated decision rows: {len(updated_decisions):,}")
        print(f"Replaced existing decision rows: {replaced_count:,}")
    print(f"Decision rows: {len(decisions):,}")
    print(f"Unique DOIs: {len({row['doi'] for row in decisions}):,}")
    print(f"Retained: {sum(row['prescreen_decision'] == 'retain' for row in decisions):,}")
    print(f"Excluded: {sum(row['prescreen_decision'] == 'exclude' for row in decisions):,}")
    print(f"Actions: {dict(by_action)}")
    if candidate_update:
        candidate_summary = candidate_update.get("candidate", {})
        print(
            "Candidate workflow reconciliation: "
            f"stable_includes={candidate_summary.get('stable_included_dois', 0):,} "
            f"reset={candidate_summary.get('downstream_reset_dois', 0):,} "
            f"updated={candidate_summary.get('updated_candidate_rows', 0):,}"
        )
    print(f"Decisions table: {decisions_table}")
    print(f"Summary table: {summary_table}")
    return decisions, summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pre-screening on corpus Parquet tables.")
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument("--contexts-table", default=str(DEFAULT_CONTEXTS_TABLE))
    parser.add_argument("--decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--summary-table", default=str(DEFAULT_SUMMARY_TABLE))
    parser.add_argument(
        "--previous-candidate-table",
        default="",
        help=(
            "Optional pre-promotion candidate snapshot used to identify stable include-to-include "
            "records. Normally the current candidate table is captured automatically before updating."
        ),
    )
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--extraction-routes-table", default=str(DEFAULT_EXTRACTION_ROUTES_TABLE))
    parser.add_argument("--extraction-tasks-jsonl", default=str(DEFAULT_EXTRACTION_TASKS_JSONL))
    parser.add_argument("--reconciliation-report", default=str(DEFAULT_RECONCILIATION_REPORT))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--doi-file", default="", help="Optional newline-delimited DOI list for a scoped update.")
    parser.add_argument("--doi", action="append", default=[], help="Single DOI for a scoped update; can be repeated.")
    parser.add_argument(
        "--no-update-candidate-table",
        action="store_true",
        help=(
            "Write prescreen artifacts without reconciling candidate_papers or downstream active views."
        ),
    )
    parser.add_argument("--progress-every", type=int, default=5000, help="Print progress every N candidate papers; 0 disables progress.")
    return parser


def main() -> None:
    run(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
