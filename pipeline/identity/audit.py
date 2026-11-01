"""Read-only identity audit: the texts and records that need a decision.

``python -m pipeline.identity audit`` checks stored full texts, abstracts
shared by several records and bibliographic records against the papers they
are attributed to, adds the extraction model's statements that a text is
another work, and writes one review queue. It changes no pipeline data: its
only outputs are ``review_queue.csv`` and ``audit_summary.json`` in a new
folder under ``data/processed/identity/audits/``.

| Check | Target | Evidence |
|---|---|---|
| ``fulltext`` | a stored full text | header identifiers and title, DOIs and title printed on the first pages, document kind (``verify.py``) |
| ``shared_abstract`` | an abstract | the same abstract on records that the work registry does not link |
| ``abstract_text`` | an abstract | web-page text (cookie, log-in or subscription notices) stored as the abstract |
| ``record_title`` | a record | PubMed's title for the record's DOI (``verify.py``) |
| ``record_doi`` | a record | a DOI that names no work, or a part of another item |
| ``openalex_pmid_collision`` | a record | an OpenAlex work ID equal to the PMID of another work |
| ``model_report`` | the text a release used | the extraction model wrote that the text and the paper differ |

An item covered by a current decision in the decision file is left out and
counted. Each queued item has a suggested decision for the reviewer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time

import pandas as pd
import pyarrow.parquet as pq

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.fulltext.source_identity import file_sha256
from pipeline.identity.evidence import (
    NOT_A_WORK_DOI_KINDS,
    artifact_evidence,
    doi_kind,
    doi_part_relation,
    doi_variant_relation,
    FRONT_MATTER_CHARS,
    document_kind,
    is_cover_sheet,
    is_not_a_title,
    is_web_page_text,
    pdf_opening_text,
    printed_dois,
    text_group_key,
    text_sha256,
    title_abstract_agreement,
    title_similarity,
    title_state,
    version_relation,
    word_count,
)
from pipeline.identity.model_reports import classify, iter_strings
from pipeline.identity.register import DEFAULT_DECISIONS_PATH, current_decisions, read_decisions
from pipeline.identity.verify import Paper, Source, Verdict, verify
from pipeline.identity.works import DEFAULT_WORK_REGISTRY, work_relation_index
from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_LEDGER = PROCESSED_DIR / "corpus" / "candidate_papers.parquet"
DEFAULT_ARTIFACT_DIR = PROCESSED_DIR / "fulltext" / "articles"
DEFAULT_DISCOVERY_RUNS = PROCESSED_DIR / "discovery" / "runs"
DEFAULT_AUDIT_ROOT = PROCESSED_DIR / "identity" / "audits"
ACTIVE_EXTRACTION_POINTER = PROCESSED_DIR / "extraction" / "active_routed_run.json"

LEDGER_COLUMNS = (
    "doi",
    "study_title",
    "study_journal",
    "abstract",
    "pmid",
    "pmcid",
    "openalex_id",
    "retained_for_extraction_candidate",
)
QUEUE_FIELDS = (
    "item_id",
    "scope",
    "check",
    "doi",
    "verdict",
    "rule",
    "suggested_verdict",
    "suggested_relation",
    "suggested_related_doi",
    "suggested_fields",
    "suggestion_basis",
    "target",
    "paper_title",
    "source_title",
    "title_similarity",
    "release_findings_main",
    "release_findings_detail",
    "release_text",
    "group_id",
    "existing_decisions",
    "evidence",
)
SHARED_ABSTRACT_MIN_WORDS = 50
# A title sharing this many informative words with an abstract owns it, as
# does one that shares at least OWNER_AGREEMENT_MIN and leads the next title by
# OWNER_MARGIN (long review titles share fewer words with their abstracts).
OWNER_AGREEMENT = 0.5
OWNER_AGREEMENT_MIN = 0.3
OWNER_MARGIN = 0.2
# Titles this similar on one shared abstract name the same work.
SAME_WORK_TITLE = 0.8
# A title-only text is suggested for acceptance only at this similarity.
TITLE_ONLY_ACCEPT = 0.95
# OpenAlex created works below this ID from PubMed records, reusing the PMID.
OPENALEX_LEGACY_ID_MAX = 45_000_000
# Words without which a statement cannot say that text and paper differ.
STATEMENT_TRIGGER_RE = re.compile(
    r"match|unrelated|incongruent|inconsistent|correspond|identity|different|attribut|titled|identified|"
    r"metadata|bibliographic|doi|conflict|disagree|title",
    re.IGNORECASE,
)
SCOPE_ORDER = {"release": 0, "extraction": 1, "corpus": 2}
VERDICT_ORDER = {"conflict": 0, "wrong_kind": 1, "model_reported": 2, "unconfirmed": 3}


# --- Inputs ---------------------------------------------------------------


def truthy(value: object) -> bool:
    return clean(value).casefold() in {"true", "1", "yes"}


def clean_pmid(value: object) -> str:
    return re.sub(r"\.0$", "", clean(value))


def load_ledger(path: Path) -> pd.DataFrame:
    available = set(pq.read_schema(path).names)
    frame = pd.read_parquet(path, columns=[column for column in LEDGER_COLUMNS if column in available])
    for column in LEDGER_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["doi"] = frame["doi"].map(normalize_doi)
    frame = frame[frame["doi"] != ""].drop_duplicates("doi")
    return frame.set_index("doi", drop=False)


def paper_for(doi: str, ledger: pd.DataFrame, fallback_title: str = "") -> Paper:
    if doi not in ledger.index:
        return Paper(doi, fallback_title)
    row = ledger.loc[doi]
    return Paper(
        doi,
        clean(row["study_title"]) or fallback_title,
        clean_pmid(row["pmid"]),
        clean(row["pmcid"]),
        clean(row["study_journal"]),
    )


def active_release(pointer: Path = ACTIVE_EXTRACTION_POINTER) -> tuple[list[Path], Path | None]:
    """Extraction outputs and KG folder of the active release."""
    if not pointer.is_file():
        return [], None
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    outputs = clean(payload.get("outputs_jsonl"))
    kg_dir = clean(payload.get("kg_dir"))
    return ([ROOT / outputs] if outputs else []), (ROOT / kg_dir if kg_dir else None)


def release_impact(kg_dir: Path | None) -> dict[str, dict]:
    """Findings per DOI in a release, by graph admission, and the text level used."""
    if kg_dir is None or not (Path(kg_dir) / "findings.parquet").is_file():
        return {}
    findings = pd.read_parquet(
        Path(kg_dir) / "findings.parquet",
        columns=["study_doi", "graph_admission_status", "access_level"],
    )
    impact: dict[str, dict] = {}
    for doi, status, access in findings.itertuples(index=False):
        entry = impact.setdefault(normalize_doi(doi), {"main": 0, "detail": 0, "access": set()})
        if status == "main_graph":
            entry["main"] += 1
        elif status == "paper_detail":
            entry["detail"] += 1
        if clean(access):
            entry["access"].add(clean(access))
    return impact


def release_text(entry: dict) -> str:
    access = entry.get("access", set())
    if "article_text" in access:
        return "fulltext"
    return "abstract" if access else ""


def pubmed_records(discovery_runs: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """PubMed titles from stored discovery records, by DOI and by PMID."""
    by_doi: dict[str, dict] = {}
    by_pmid: dict[str, dict] = {}
    for path in sorted(Path(discovery_runs).glob("*/retrieved_records.parquet")):
        frame = pd.read_parquet(
            path,
            columns=["provider", "doi", "pmid", "title"],
            filters=[("provider", "==", "pubmed")],
        )
        for raw_doi, raw_pmid, raw_title in zip(frame["doi"], frame["pmid"], frame["title"]):
            doi, pmid, title = normalize_doi(raw_doi), clean_pmid(raw_pmid), clean(raw_title)
            if not title:
                continue
            if doi:
                by_doi.setdefault(doi, {"pmid": pmid, "title": title})
            if pmid:
                by_pmid.setdefault(pmid, {"doi": doi, "title": title})
    return by_doi, by_pmid


def apply_record_corrections(ledger: pd.DataFrame, decisions: dict[str, list[dict]]) -> Counter:
    """Apply current record corrections to the audit's copy of the ledger.

    Texts are checked against the record as decided, as the pipeline will read
    it once the decisions are applied.
    """
    counts: Counter = Counter()
    for doi, doi_decisions in decisions.items():
        if doi not in ledger.index:
            continue
        for decision in doi_decisions:
            if clean(decision.get("verdict", "")) != "record_corrected":
                continue
            changes = {**(decision.get("fields") or {}), **{field: "" for field in decision.get("clear_fields") or []}}
            for field, value in changes.items():
                if field not in ledger.columns:
                    continue
                if ledger[field].dtype != object:
                    ledger[field] = ledger[field].astype(object)
                ledger.at[doi, field] = value
                counts["fields_set" if value else "fields_cleared"] += 1
    return counts


def decisions_by_doi(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if Path(path).is_file():
        for decision in current_decisions(read_decisions(path)):
            out[normalize_doi(decision.get("doi", ""))].append(decision)
    return out


# --- Queue items ----------------------------------------------------------


def suggestion(verdict: str = "", basis: str = "", relation: str = "", related_doi: str = "", fields: dict | None = None) -> dict:
    return {"verdict": verdict, "basis": basis, "relation": relation, "related_doi": related_doi, "fields": fields or {}}


def queue_item(
    *,
    check: str,
    doi: str,
    verdict: str,
    rule: str,
    target: dict,
    text_ids: dict | None = None,
    paper_title: str = "",
    source_title: str = "",
    similarity: float | None = None,
    suggested: dict | None = None,
    evidence: dict | None = None,
    group_id: str = "",
) -> dict:
    suggested = suggested or suggestion()
    key = json.dumps([check, doi, target, rule], sort_keys=True)
    return {
        "item_id": "idq-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
        "check": check,
        "doi": doi,
        "verdict": verdict,
        "rule": rule,
        "suggested_verdict": suggested["verdict"],
        "suggested_relation": suggested["relation"],
        "suggested_related_doi": suggested["related_doi"],
        "suggested_fields": json.dumps(suggested["fields"], ensure_ascii=False, sort_keys=True) if suggested["fields"] else "",
        "suggestion_basis": suggested["basis"],
        "target": json.dumps(target, sort_keys=True),
        "paper_title": paper_title,
        "source_title": source_title,
        "title_similarity": "" if similarity is None else similarity,
        "group_id": group_id,
        "evidence": json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True, default=sorted),
        "_target_kind": target["kind"],
        "_text_ids": text_ids or {},
    }


def target_matches(target: dict, text_ids: dict) -> bool:
    """True when a decision target names this text by an identifier both carry."""
    for key in ("sha256", "pdf_sha256", "provider", "source_url"):
        value = clean(target.get(key, "")).casefold()
        if value and value in text_ids.get(key, set()):
            return True
    document_doi = normalize_doi(target.get("document_doi", ""))
    return bool(document_doi) and document_doi in text_ids.get("document_doi", set())


def covering_decisions(decisions: list[dict], target_kind: str, text_ids: dict, *, check: str = "") -> list[str]:
    """Ids of current decisions that already settle an item.

    A text item is settled by a decision on the same text. Any item is settled
    when the record's DOI was found to belong to another work. A record item, a
    model report, or an abstract item whose abstract was replaced or cleared,
    is settled by a record correction. A hold settles nothing: it waits for
    these decisions.
    """
    covered = []
    for decision in decisions:
        target = decision.get("target") or {}
        kind, verdict = clean(target.get("kind", "")), clean(decision.get("verdict", ""))
        if kind == "record":
            changed = set(decision.get("fields") or {}) | set(decision.get("clear_fields") or [])
            if verdict == "wrong_doi" or (
                verdict == "record_corrected"
                and (
                    target_kind == "record"
                    or check == "model_report"
                    or (target_kind == "abstract" and "abstract" in changed)
                )
            ):
                covered.append(decision["decision_id"])
        elif kind == target_kind and target_matches(target, text_ids):
            covered.append(decision["decision_id"])
    return covered


# --- Full texts -----------------------------------------------------------


def fulltext_source(evidence: dict, paper: Paper, pdf_text: str = "") -> Source:
    headers = evidence["headers"]
    titles = tuple(header["title"] for header in headers if header["title"])
    kind = document_kind(titles[0] if titles else "", evidence["opening"], paper.title)
    if kind == "article" and pdf_text:
        kind = document_kind("", pdf_text.lstrip(), paper.title)
    return Source(
        titles=titles,
        own_dois=tuple(header["doi"] for header in headers if header["doi"]),
        printed_dois=tuple(sorted(set(evidence["printed_dois"]) | printed_dois(pdf_text))),
        pmids=tuple(header["pmid"] for header in headers if header["pmid"]),
        pmcids=tuple(header["pmcid"] for header in headers if header["pmcid"]),
        document_kind=kind,
        opening_text=pdf_text or evidence["opening"],
    )


def after_cover_sheet_source(pages: list[str], paper: Paper) -> Source:
    """Evidence from the pages after a repository cover sheet: the attached text itself.

    A cover sheet describes the deposit record. Its title and DOI say nothing
    about whether the attached file is that publication, so the parsed header,
    which may come from the cover sheet, is not used.
    """
    first = pages[1]
    body = "\f".join(pages[1:3])[:FRONT_MATTER_CHARS]
    return Source(
        own_dois=tuple(sorted(printed_dois(first[:4000]))),
        printed_dois=tuple(sorted(printed_dois(body))),
        document_kind=document_kind("", first.lstrip(), paper.title),
        opening_text=body,
    )


def suggest_for_text(verdict: Verdict, paper: Paper) -> dict:
    """Suggested decision for a text or provider record that is not verified."""
    rule, other = verdict.rule, verdict.related_doi
    similarity = verdict.evidence.get("title_similarity")
    if rule.startswith("paper_doi_is_"):
        kind = rule.removeprefix("paper_doi_is_")
        if kind == "component":
            return suggestion("hold", "the record's DOI names a part of another item, such as a peer-review report, figure or supplement")
        return suggestion("wrong_doi", f"the record's DOI is a {kind} DOI and names no work")
    if rule.startswith("document_is_"):
        return suggestion("wrong_kind", f"the stored text is a {rule.removeprefix('document_is_')}, not the article")
    if verdict.verdict == "wrong_kind":
        return suggestion("wrong_kind", f"the text's DOI is registered as {verdict.relation} of the paper", verdict.relation, other)
    if rule in {"title_matches_identifier_differs", "identifier_differs_title_unclear"}:
        relation = version_relation(paper.doi, other)
        if relation:
            return suggestion(
                "version_of",
                f"the text has the paper's title under {other}; the DOIs indicate {relation.replace('_', ' ')}",
                relation,
                other,
            )
        if rule == "title_matches_identifier_differs":
            return suggestion(
                "version_of",
                f"the text has the paper's title under another DOI, {other}; confirm both name the same publication",
                "same_publication",
                other,
            )
        return suggestion("", f"review: the text gives {other} as its DOI, and its title does not clearly agree", related_doi=other)
    if rule == "identifier_and_title_differ":
        relation = version_relation(paper.doi, other)
        if relation:
            return suggestion("", f"review: {other} indicates {relation.replace('_', ' ')}, but the parsed title differs", relation, other)
        return suggestion("not_this_work", f"the text's DOI ({other}) and title name another work", related_doi=other)
    if rule == "identifier_matches_title_differs":
        source_title = verdict.evidence.get("source_title", "")
        if is_not_a_title(paper.title) and source_title:
            return suggestion(
                "record_corrected",
                "the record's title is not a title; the text with this DOI gives the title",
                fields={"study_title": source_title},
            )
        return suggestion("", "review: the text has the paper's DOI under another title; the record's title or DOI may belong to another work")
    if rule == "possible_multi_item_page":
        others = ", ".join(verdict.evidence.get("other_printed_dois", [])[:3])
        return suggestion("", f"review: the page also prints {others}; the text may hold several items")
    if rule == "printed_doi_matches_parsed_doi_differs":
        return suggestion(
            "",
            f"review: the paper's DOI is printed, but the parser read {other} as the document's DOI: "
            "a cited article, or a cover sheet attached to another text",
            related_doi=other,
        )
    if rule == "cover_sheet_not_separated":
        return suggestion("", "review: the text starts with a repository cover sheet, and no PDF was available to check the attached text")
    if rule == "title_only" and (verdict.evidence.get("title_printed") or (similarity or 0) >= TITLE_ONLY_ACCEPT):
        return suggestion("verified", "the title agrees; the paper's DOI is not printed in the text or was cut by the parser")
    if rule == "identifier_only":
        if verdict.evidence.get("title_printed") and (similarity or 0) < 0.5:
            return suggestion("", "review: the paper's DOI and title are printed, but the document's heading is another title; it may hold several items")
        return suggestion("verified", "the identifier agrees; the parsed title is missing or only partly agrees")
    return suggestion("", "review: the text has too little identity evidence")


def fulltext_items(
    ledger: pd.DataFrame,
    artifact_dir: Path,
    relations: dict[frozenset[str], str],
    *,
    read_pdfs: bool = True,
) -> tuple[list[dict], Counter]:
    items: list[dict] = []
    counts: Counter = Counter()
    for path in sorted(Path(artifact_dir).glob("*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts["artifacts_unreadable"] += 1
            continue
        doi = normalize_doi(artifact.get("study_doi", ""))
        if not doi:
            counts["artifacts_without_doi"] += 1
            continue
        counts["artifacts"] += 1
        paper = paper_for(doi, ledger, clean(artifact.get("study_title", "")))
        evidence = artifact_evidence(artifact)
        verdict = verify(paper, fulltext_source(evidence, paper), relations)
        pdf_value = clean(artifact.get("pdf_local_path", ""))
        pdf_path = Path(pdf_value).expanduser() if pdf_value else None
        cover_sheet = is_cover_sheet(evidence["opening"])
        separated = False
        if (cover_sheet or verdict.verdict != "verified") and read_pdfs and pdf_path is not None:
            # Parsed texts drop page headers and footers, where the DOI is often
            # printed, and do not mark where a cover sheet ends.
            pages = pdf_opening_text(pdf_path, pages=4, max_chars=4 * FRONT_MATTER_CHARS).split("\f")
            if any(page.strip() for page in pages):
                counts["pdf_first_pages_read"] += 1
                if len(pages) > 1 and is_cover_sheet(pages[0]):
                    counts["cover_sheets_separated"] += 1
                    separated = True
                    source = after_cover_sheet_source(pages, paper)
                else:
                    cover_sheet = False
                    source = fulltext_source(evidence, paper, "\f".join(pages[:2])[:FRONT_MATTER_CHARS])
                verdict = verify(paper, source, relations)
        if cover_sheet and not separated and verdict.verdict == "verified":
            verdict = Verdict("unconfirmed", "cover_sheet_not_separated", evidence=verdict.evidence)
        counts[f"verdict_{verdict.verdict}"] += 1
        if verdict.verdict in {"verified", "version_of"}:
            continue
        target = {"kind": "fulltext", "sha256": file_sha256(path)}
        if pdf_path is not None and pdf_path.is_file():
            target["pdf_sha256"] = file_sha256(pdf_path)
        header_dois = sorted({header["doi"] for header in evidence["headers"] if header["doi"]})
        if header_dois:
            target["document_doi"] = header_dois[0]
        items.append(
            queue_item(
                check="fulltext",
                doi=doi,
                verdict=verdict.verdict,
                rule=verdict.rule,
                target=target,
                text_ids={
                    "sha256": {target["sha256"]},
                    "pdf_sha256": {target["pdf_sha256"]} if "pdf_sha256" in target else set(),
                    "document_doi": set(header_dois),
                },
                paper_title=paper.title,
                source_title=verdict.evidence.get("source_title", ""),
                similarity=verdict.evidence.get("title_similarity"),
                suggested=suggest_for_text(verdict, paper),
                evidence={
                    **verdict.evidence,
                    "artifact": path.name,
                    "related_doi": verdict.related_doi,
                    "cover_sheet_separated": separated,
                },
            )
        )
    return items, counts


# --- Shared abstracts -----------------------------------------------------


def shared_abstract_items(ledger: pd.DataFrame, relations: dict[frozenset[str], str]) -> tuple[list[dict], Counter]:
    """Items for abstracts that several records carry without a registered relation."""
    counts: Counter = Counter()
    groups: dict[str, list[str]] = defaultdict(list)
    for doi, abstract in zip(ledger["doi"], ledger["abstract"]):
        if word_count(abstract) >= SHARED_ABSTRACT_MIN_WORDS:
            groups[text_group_key(abstract)].append(doi)
    items: list[dict] = []
    for key, members in groups.items():
        dois = sorted(set(members))
        if len(dois) < 2:
            continue
        counts["groups"] += 1
        counts["group_records"] += len(dois)
        if all(frozenset((a, b)) in relations for index, a in enumerate(dois) for b in dois[index + 1 :]):
            counts["groups_registered"] += 1
            continue
        group_id = "abs-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        items.extend(shared_group_items(group_id, dois, ledger, relations, counts))
    return items, counts


def web_page_abstract_items(ledger: pd.DataFrame) -> tuple[list[dict], Counter]:
    """Items for abstracts that are web-page text, on records that do not share them."""
    counts: Counter = Counter()
    items: list[dict] = []
    found = [
        (doi, clean(title), clean(abstract))
        for doi, title, abstract in zip(ledger["doi"], ledger["study_title"], ledger["abstract"])
        if clean(abstract) and is_web_page_text(abstract)
    ]
    # Shared copies are left to the shared-abstract check.
    shared = Counter(
        text_group_key(abstract)
        for abstract in ledger["abstract"]
        if word_count(abstract) >= SHARED_ABSTRACT_MIN_WORDS
    )
    for doi, title, abstract in found:
        counts["web_page_abstracts"] += 1
        if word_count(abstract) >= SHARED_ABSTRACT_MIN_WORDS and shared[text_group_key(abstract)] > 1:
            continue
        sha = text_sha256(abstract)
        items.append(
            queue_item(
                check="abstract_text",
                doi=doi,
                verdict="wrong_kind",
                rule="abstract_is_web_page_text",
                target={"kind": "abstract", "sha256": sha},
                text_ids={"sha256": {sha}},
                paper_title=title,
                suggested=suggestion("wrong_kind", "the abstract is web-page text, not an abstract"),
                evidence={"abstract_start": abstract[:240]},
            )
        )
    return items, counts


def anchor_doi(dois: Iterable[str]) -> str:
    """The member other DOIs of one work are registered against: an article DOI first."""
    return sorted(dois, key=lambda doi: (doi_kind(doi) != "article", len(doi), doi))[0]


def shared_group_items(
    group_id: str,
    dois: list[str],
    ledger: pd.DataFrame,
    relations: dict[frozenset[str], str],
    counts: Counter,
) -> list[dict]:
    titles = {doi: clean(ledger.at[doi, "study_title"]) for doi in dois}
    abstracts = {doi: clean(ledger.at[doi, "abstract"]) for doi in dois}
    agreement = {doi: title_abstract_agreement(titles[doi], abstracts[doi]) for doi in dois}

    # Members joined by a registered relation, a DOI-form variant or nearly
    # identical titles are one work.
    parent = {doi: doi for doi in dois}

    def root(doi: str) -> str:
        while parent[doi] != doi:
            parent[doi] = parent[parent[doi]]
            doi = parent[doi]
        return doi

    pair_relation: dict[frozenset[str], str] = {}
    for index, a in enumerate(dois):
        for b in dois[index + 1 :]:
            relation = relations.get(frozenset((a, b))) or doi_variant_relation(a, b)
            if not relation and (title_similarity(titles[a], titles[b]) or 0) >= SAME_WORK_TITLE:
                relation = "same_publication"
            if relation:
                pair_relation[frozenset((a, b))] = relation
                parent[root(a)] = root(b)
    clusters: dict[str, list[str]] = defaultdict(list)
    for doi in dois:
        clusters[root(doi)].append(doi)
    scored = sorted(((score, doi) for doi, score in agreement.items() if score is not None), reverse=True)
    best_score, best_doi = scored[0] if scored else (None, "")
    runner_up = next((score for score, doi in scored[1:] if root(doi) != root(best_doi)), 0.0)
    owner = (
        root(best_doi)
        if best_score is not None
        and (best_score >= OWNER_AGREEMENT or (best_score >= OWNER_AGREEMENT_MIN and best_score - runner_up >= OWNER_MARGIN))
        else None
    )

    def item(doi: str, verdict: str, rule: str, suggested: dict) -> dict:
        sha = text_sha256(abstracts[doi])
        return queue_item(
            check="shared_abstract",
            doi=doi,
            verdict=verdict,
            rule=rule,
            target={"kind": "abstract", "sha256": sha},
            text_ids={"sha256": {sha}},
            paper_title=titles[doi],
            similarity=None,
            suggested=suggested,
            evidence={
                "group_size": len(dois),
                "group_dois": dois,
                "title_abstract_agreement": agreement[doi],
                "best_agreeing_doi": best_doi if owner else "",
                "abstract_start": abstracts[doi][:240],
            },
            group_id=group_id,
        )

    def same_work_items(members: list[str]) -> list[dict]:
        anchor = anchor_doi(members)
        out = []
        for doi in members:
            if doi == anchor or frozenset((doi, anchor)) in relations:
                continue
            relation = pair_relation.get(frozenset((doi, anchor))) or version_relation(doi, anchor) or "same_publication"
            out.append(
                item(
                    doi,
                    "unconfirmed",
                    "same_text_on_unlinked_dois",
                    suggestion(
                        "version_of",
                        f"{anchor} has the same abstract and its DOI or title names the same work; "
                        "registering the relation counts the report once",
                        relation,
                        anchor,
                    ),
                )
            )
        return out

    if is_web_page_text(abstracts[dois[0]]):
        counts["groups_web_page_text"] += 1
        return [
            item(doi, "wrong_kind", "shared_text_is_web_page", suggestion("wrong_kind", "the shared text is web-page text, not an abstract"))
            for doi in dois
        ]
    if len(clusters) == 1:
        counts["groups_one_work"] += 1
        return same_work_items(dois)

    counts["groups_several_works" if owner else "groups_no_title_agrees"] += 1
    items: list[dict] = []
    for cluster_root, members in clusters.items():
        if cluster_root == owner:
            if len(members) > 1:
                items.extend(same_work_items(members))
            continue
        others = [doi for doi in dois if root(doi) != cluster_root]
        part_of = [other for other in others for doi in members if doi_part_relation(doi, other)]
        title_agrees = any((agreement[doi] or 0) >= OWNER_AGREEMENT for doi in members)
        for doi in members:
            if agreement[doi] is None or is_not_a_title(titles[doi]):
                items.append(
                    item(
                        doi,
                        "unconfirmed",
                        "shared_abstract_title_unusable",
                        suggestion("", "review: the record has no usable title to compare with the shared abstract"),
                    )
                )
            elif part_of:
                items.append(
                    item(
                        doi,
                        "wrong_kind",
                        "shared_abstract_part_of_item",
                        suggestion(
                            "wrong_kind",
                            f"the abstract is shared with {part_of[0]}, of which this record is a part or which is a part of it",
                            related_doi=part_of[0],
                        ),
                    )
                )
            elif title_agrees:
                items.append(
                    item(
                        doi,
                        "unconfirmed",
                        "shared_abstract_title_also_agrees",
                        suggestion("", "review: another work with this abstract also has an agreeing title, such as a reply, a duplicate publication or a sibling item"),
                    )
                )
            elif owner:
                items.append(
                    item(
                        doi,
                        "conflict",
                        "shared_abstract_title_disagrees",
                        suggestion("not_this_work", f"the title does not agree with the abstract, which agrees with the title of {best_doi}", related_doi=best_doi),
                    )
                )
            else:
                items.append(
                    item(
                        doi,
                        "conflict",
                        "shared_abstract_no_title_agrees",
                        suggestion("not_this_work", "the abstract is on several records and agrees with none of their titles"),
                    )
                )
    return items


# --- Records --------------------------------------------------------------


def openalex_number(value: object) -> int | None:
    match = re.search(r"W(\d+)$", clean(value), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def record_items(
    ledger: pd.DataFrame,
    pubmed_by_doi: dict[str, dict],
    pubmed_by_pmid: dict[str, dict],
    relations: dict[frozenset[str], str],
) -> tuple[list[dict], Counter]:
    items: list[dict] = []
    counts: Counter = Counter()
    for row in ledger.itertuples(index=False):
        doi = row.doi
        paper = Paper(doi, clean(row.study_title), clean_pmid(row.pmid), clean(row.pmcid), clean(row.study_journal))
        abstract = clean(row.abstract)
        counts["records"] += 1

        kind = doi_kind(doi)
        if kind in NOT_A_WORK_DOI_KINDS or kind == "component":
            counts[f"doi_{kind}"] += 1
            verdict = Verdict("wrong_kind", f"paper_doi_is_{kind}")
            items.append(
                queue_item(
                    check="record_doi",
                    doi=doi,
                    verdict=verdict.verdict,
                    rule=verdict.rule,
                    target={"kind": "record"},
                    paper_title=paper.title,
                    suggested=suggest_for_text(verdict, paper),
                )
            )
            continue

        number = openalex_number(row.openalex_id)
        legacy_id = number is not None and number < OPENALEX_LEGACY_ID_MAX
        own_pubmed = pubmed_by_doi.get(doi)
        if own_pubmed:
            counts["records_with_pubmed_title"] += 1
            verdict = verify(
                paper,
                Source(titles=(own_pubmed["title"],), own_dois=(doi,), pmids=tuple(filter(None, [own_pubmed["pmid"]]))),
                relations,
            )
            if verdict.verdict == "conflict":
                counts["pubmed_title_conflicts"] += 1
                merged = legacy_id and own_pubmed["pmid"] == str(number)
                counts["pubmed_title_conflicts_openalex_id_is_doi_pmid"] += int(merged)
                items.append(record_title_item(paper, abstract, own_pubmed, verdict, openalex_merged=merged))

        other = pubmed_by_pmid.get(str(number)) if legacy_id else None
        if not other or not other["doi"] or other["doi"] == doi or paper.pmid == str(number):
            continue
        # OpenAlex built this work from PubMed record <number>, which is another article.
        counts["openalex_pmid_collisions"] += 1
        state, similarity = title_state(paper.title, other["title"])
        own_state = title_state(paper.title, own_pubmed["title"])[0] if own_pubmed else "missing"
        if state != "agrees" and own_state == "agrees":
            continue
        if state == "agrees":
            rule = "record_title_from_other_work"
            if (title_abstract_agreement(paper.title, abstract) or 0) >= OWNER_AGREEMENT:
                suggested = suggestion(
                    "wrong_doi",
                    f"the record's title and abstract are PubMed {number}'s, whose DOI is {other['doi']}",
                    related_doi=other["doi"],
                )
            elif own_pubmed:
                suggested = suggestion(
                    "record_corrected",
                    f"the record's title is PubMed {number}'s; PubMed lists this DOI as {own_pubmed['title']!r}",
                    fields={"study_title": own_pubmed["title"]},
                )
            else:
                suggested = suggestion("", f"review: the record's title is PubMed {number}'s, whose DOI is {other['doi']}", related_doi=other["doi"])
        else:
            rule = "openalex_id_is_pmid_of_other_work"
            suggested = suggestion("", f"review: OpenAlex merged this DOI with PubMed {number} ({other['doi']}); no other source confirms the record")
        items.append(
            queue_item(
                check="openalex_pmid_collision",
                doi=doi,
                verdict="conflict" if state == "agrees" else "unconfirmed",
                rule=rule,
                target={"kind": "record"},
                paper_title=paper.title,
                source_title=other["title"],
                similarity=similarity,
                suggested=suggested,
                evidence={"openalex_id": clean(row.openalex_id), "pubmed_pmid": str(number), "pubmed_doi": other["doi"]},
            )
        )
    return items, counts


def record_title_item(paper: Paper, abstract: str, pubmed: dict, verdict: Verdict, *, openalex_merged: bool = False) -> dict:
    """Item for a record whose title differs from PubMed's title for its DOI.

    ``openalex_merged`` marks records whose OpenAlex ID equals the DOI's PMID:
    OpenAlex merged that PubMed record with an older work, whose title and
    abstract the record may carry.
    """
    own = title_abstract_agreement(paper.title, abstract)
    theirs = title_abstract_agreement(pubmed["title"], abstract)
    if (own or 0) >= OWNER_AGREEMENT and (theirs or 0) < OWNER_AGREEMENT:
        suggested = suggestion(
            "wrong_doi",
            "the record's title and abstract describe one work, and PubMed lists this DOI under another title",
        )
    elif (theirs or 0) >= OWNER_AGREEMENT:
        suggested = suggestion(
            "record_corrected",
            "PubMed's title for this DOI agrees with the record's abstract; the record's title belongs to another work",
            fields={"study_title": pubmed["title"]},
        )
    else:
        suggested = suggestion("", "review: PubMed lists this DOI under another title")
    if openalex_merged:
        suggested["basis"] += "; the record's OpenAlex ID equals this DOI's PMID, so OpenAlex merged it with another work"
    return queue_item(
        check="record_title",
        doi=paper.doi,
        verdict=verdict.verdict,
        rule=verdict.rule,
        target={"kind": "record"},
        paper_title=paper.title,
        source_title=pubmed["title"],
        similarity=verdict.evidence.get("title_similarity"),
        suggested=suggested,
        evidence={
            "pubmed_pmid": pubmed["pmid"],
            "title_abstract_agreement": own,
            "pubmed_title_abstract_agreement": theirs,
            "openalex_id_is_doi_pmid": openalex_merged,
        },
    )


# --- Model statements -----------------------------------------------------


def release_text_target(doi: str, text: str, ledger: pd.DataFrame, artifact_dir: Path) -> tuple[dict, dict]:
    """Target and identifiers of the text a release used for a paper, as stored now."""
    if text == "fulltext":
        path = Path(artifact_dir) / f"{doi_to_slug(doi)}.json"
        if path.is_file():
            sha = file_sha256(path)
            return {"kind": "fulltext", "sha256": sha}, {"sha256": {sha}}
    if doi in ledger.index and clean(ledger.at[doi, "abstract"]):
        sha = text_sha256(clean(ledger.at[doi, "abstract"]))
        return {"kind": "abstract", "sha256": sha}, {"sha256": {sha}}
    return {"kind": "record"}, {}


def model_report_items(
    outputs: Iterable[Path],
    impact: dict[str, dict],
    ledger: pd.DataFrame,
    artifact_dir: Path,
) -> tuple[list[dict], Counter]:
    counts: Counter = Counter()
    statements: dict[str, list[dict]] = defaultdict(list)
    for path in outputs:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                counts["outputs"] += 1
                doi = normalize_doi(row.get("study_doi", ""))
                for json_path, text in iter_strings({"result": row.get("result"), "qa_flags": row.get("qa_flags")}):
                    if len(text) < 25 or not STATEMENT_TRIGGER_RE.search(text):
                        continue
                    categories = classify(text)
                    for category in categories:
                        counts[f"statements_{category}"] += 1
                    if "D" in categories:
                        statements[doi].append({"path": json_path, "text": clean(text)[:400], "patterns": categories["D"]})
    items: list[dict] = []
    for doi, found in sorted(statements.items()):
        target, text_ids = release_text_target(doi, release_text(impact.get(doi, {})), ledger, artifact_dir)
        items.append(
            queue_item(
                check="model_report",
                doi=doi,
                verdict="model_reported",
                rule="model_reported_different_work",
                target=target,
                text_ids=text_ids,
                paper_title=clean(ledger.at[doi, "study_title"]) if doi in ledger.index else "",
                suggested=suggestion("", "review: the extraction model wrote that the supplied text and the paper's title or metadata describe different works"),
                evidence={"statement_count": len(found), "statements": found[:3]},
            )
        )
    counts["papers_with_statements"] = len(statements)
    return items, counts


# --- Run ------------------------------------------------------------------


def run_audit(
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    discovery_runs: Path = DEFAULT_DISCOVERY_RUNS,
    outputs: list[Path] | None = None,
    kg_dir: Path | None = None,
    decisions_path: Path = DEFAULT_DECISIONS_PATH,
    work_registry: Path = DEFAULT_WORK_REGISTRY,
    out_root: Path = DEFAULT_AUDIT_ROOT,
    read_pdfs: bool = True,
    include_corpus: bool = False,
    audit_id: str | None = None,
) -> dict:
    """Write the review queue and its summary; return the summary.

    Items about records that are neither in the release nor retained for
    extraction are counted but queued only with ``include_corpus``.
    """
    started = time.monotonic()
    audit_id = audit_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(out_root) / audit_id
    if out_dir.exists():
        raise FileExistsError(f"Audit folder already exists: {out_dir}")
    if outputs is None and kg_dir is None:
        outputs, kg_dir = active_release()
    outputs = [Path(path) for path in outputs or []]

    ledger = load_ledger(Path(ledger_path))
    relations = work_relation_index(Path(work_registry))
    decisions = decisions_by_doi(Path(decisions_path))
    corrections = apply_record_corrections(ledger, decisions)
    impact = release_impact(kg_dir)
    pubmed_by_doi, pubmed_by_pmid = pubmed_records(Path(discovery_runs))

    checks: dict[str, dict] = {}
    items: list[dict] = []
    for name, (found, counts) in (
        ("fulltext", fulltext_items(ledger, Path(artifact_dir), relations, read_pdfs=read_pdfs)),
        ("shared_abstract", shared_abstract_items(ledger, relations)),
        ("abstract_text", web_page_abstract_items(ledger)),
        ("records", record_items(ledger, pubmed_by_doi, pubmed_by_pmid, relations)),
        ("model_report", model_report_items(outputs, impact, ledger, Path(artifact_dir))),
    ):
        checks[name] = dict(sorted(counts.items()))
        items.extend(found)

    queue: list[dict] = []
    left_out: Counter = Counter()
    out_of_scope: Counter = Counter()
    for item in items:
        target_kind, text_ids = item.pop("_target_kind"), item.pop("_text_ids")
        doi_decisions = decisions.get(item["doi"], [])
        if covering_decisions(doi_decisions, target_kind, text_ids, check=item["check"]):
            left_out[item["check"]] += 1
            continue
        entry = impact.get(item["doi"], {})
        findings = entry.get("main", 0) + entry.get("detail", 0)
        retained = item["doi"] in ledger.index and truthy(ledger.at[item["doi"], "retained_for_extraction_candidate"])
        scope = "release" if findings else ("extraction" if retained else "corpus")
        if scope == "corpus" and not include_corpus:
            out_of_scope[item["check"]] += 1
            continue
        item.update(
            {
                "scope": scope,
                "release_findings_main": entry.get("main", 0),
                "release_findings_detail": entry.get("detail", 0),
                "release_text": release_text(entry),
                "existing_decisions": " ".join(decision["decision_id"] for decision in doi_decisions),
            }
        )
        queue.append(item)
    queue.sort(
        key=lambda item: (
            SCOPE_ORDER[item["scope"]],
            VERDICT_ORDER.get(item["verdict"], 9),
            -item["release_findings_main"],
            item["check"],
            item["doi"],
        )
    )

    out_dir.mkdir(parents=True)
    queue_path = out_dir / "review_queue.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(queue)

    release_dois = {item["doi"] for item in queue if item["scope"] == "release"}
    summary = {
        "schema_version": "identity_audit_v1",
        "audit_id": audit_id,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "seconds": round(time.monotonic() - started, 1),
        "inputs": {
            "ledger": str(Path(ledger_path).resolve()),
            "artifact_dir": str(Path(artifact_dir).resolve()),
            "discovery_runs": str(Path(discovery_runs).resolve()),
            "release_outputs": [str(path.resolve()) for path in outputs],
            "release_kg_dir": str(Path(kg_dir).resolve()) if kg_dir else "",
            "decisions": str(Path(decisions_path).resolve()),
            "current_decisions": sum(len(values) for values in decisions.values()),
            "record_corrections_applied": dict(corrections),
            "work_registry": str(Path(work_registry).resolve()),
            "registered_pairs": len(relations),
            "pubmed_titles_by_doi": len(pubmed_by_doi),
            "pdf_first_pages_read": read_pdfs,
            "corpus_scope_queued": include_corpus,
        },
        "checks": checks,
        "left_out_as_decided": dict(sorted(left_out.items())),
        "not_queued_corpus_scope": dict(sorted(out_of_scope.items())),
        "queued": len(queue),
        "queued_by_check": dict(Counter(item["check"] for item in queue).most_common()),
        "queued_by_scope": dict(Counter(item["scope"] for item in queue).most_common()),
        "queued_by_verdict": dict(Counter(item["verdict"] for item in queue).most_common()),
        "queued_by_rule": dict(Counter(f"{item['check']}:{item['rule']}" for item in queue).most_common()),
        "suggested": dict(Counter(item["suggested_verdict"] or "review" for item in queue).most_common()),
        "release": {
            "papers": len(release_dois),
            "findings_main": sum(impact[doi]["main"] for doi in release_dois),
            "findings_detail": sum(impact[doi]["detail"] for doi in release_dois),
        },
        "outputs": {"review_queue": str(queue_path.resolve()), "summary": str((out_dir / "audit_summary.json").resolve())},
    }
    (out_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
