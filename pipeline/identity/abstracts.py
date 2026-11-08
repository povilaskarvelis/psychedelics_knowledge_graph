"""Whether an abstract from a provider record may fill a paper's record (decision D5).

An abstract arrives with the provider record it came from: the provider, the
record's ID, and the DOI, PMID, PMCID and title the record gives as its own.
The abstract passes when

- ``verify.py`` verifies the record for the paper (an identifier and the title
  agree), or the record is a registered version of the paper;
- the same abstract is not on another record whose DOI the work registry does
  not link to this paper's; and
- it is not web-page text.

An abstract fills a record only when it passes. One that does not leaves the
record without an abstract, and ``audit`` lists it for review. Abstracts
already in the ledger are not replaced (decision D5).

Provider records are kept so that each abstract can be checked again later:
enrichment writes them to ``data/processed/identity/provider_records/``, and
discovery keeps its own in each run's ``retrieved_records.parquet``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipeline.identity.evidence import is_web_page_text, text_group_key, word_count
from pipeline.identity.verify import Paper, Source, verify
from pipeline.identity.works import DEDUPLICATED_RELATIONS
from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVIDER_RECORDS_DIR = ROOT / "data" / "processed" / "identity" / "provider_records"
DEFAULT_DISCOVERY_RUNS = ROOT / "data" / "processed" / "discovery" / "runs"
PROVIDER_RECORD_COLUMNS = (
    "doi",
    "provider",
    "provider_record_id",
    "record_doi",
    "record_pmid",
    "record_pmcid",
    "record_title",
    "abstract",
    "retrieved_at_utc",
    "run_id",
)
# Shorter texts recur on unrelated records (for example "No abstract available").
SHARED_ABSTRACT_MIN_WORDS = 50
PASSING_VERDICTS = frozenset({"verified", "version_of"})


@dataclass(frozen=True)
class AbstractCheck:
    passes: bool
    verdict: str
    rule: str
    related_doi: str = ""


def record_source(record: dict) -> Source:
    """The identity evidence a provider record gives about itself."""
    return Source(
        titles=tuple(filter(None, [clean(record.get("record_title", ""))])),
        own_dois=tuple(filter(None, [normalize_doi(record.get("record_doi", ""))])),
        pmids=tuple(filter(None, [clean(record.get("record_pmid", "")).removesuffix(".0")])),
        pmcids=tuple(filter(None, [clean(record.get("record_pmcid", ""))])),
    )


class AbstractChecker:
    """Checks abstracts against their provider records and against the abstracts already in the corpus."""

    def __init__(self, papers: dict[str, Paper], ledger_abstracts: dict[str, str], relations: dict[frozenset[str], str]):
        self.papers = papers
        self.relations = relations
        self.holders: dict[str, set[str]] = defaultdict(set)
        for doi, abstract in ledger_abstracts.items():
            self.add(doi, abstract)

    @classmethod
    def from_ledger(cls, ledger: pd.DataFrame, relations: dict[frozenset[str], str]) -> "AbstractChecker":
        """A checker for the records of a ledger loaded by ``audit.load_ledger``."""
        papers = {
            doi: Paper(doi, clean(title), clean(pmid).removesuffix(".0"), clean(pmcid), clean(journal))
            for doi, title, pmid, pmcid, journal in zip(
                ledger["doi"], ledger["study_title"], ledger["pmid"], ledger["pmcid"], ledger["study_journal"]
            )
        }
        return cls(papers, dict(zip(ledger["doi"], ledger["abstract"])), relations)

    def add(self, doi: str, abstract: object) -> None:
        """Count an abstract as held by a record, so that later copies on unlinked records fail."""
        if word_count(abstract) >= SHARED_ABSTRACT_MIN_WORDS:
            self.holders[text_group_key(abstract)].add(normalize_doi(doi))

    def unlinked_holder(self, doi: str, abstract: object) -> str:
        if word_count(abstract) < SHARED_ABSTRACT_MIN_WORDS:
            return ""
        others = sorted(self.holders.get(text_group_key(abstract), set()) - {doi})
        return next(
            (other for other in others if self.relations.get(frozenset((doi, other)), "") not in DEDUPLICATED_RELATIONS),
            "",
        )

    def check(self, doi: object, record: dict, paper: Paper | None = None) -> AbstractCheck:
        """Check an abstract for the paper with this DOI; ``paper`` for one not in the ledger yet."""
        doi = normalize_doi(doi)
        abstract = clean(record.get("abstract", ""))
        if not abstract:
            return AbstractCheck(False, "", "no_abstract")
        if is_web_page_text(abstract):
            return AbstractCheck(False, "wrong_kind", "abstract_is_web_page_text")
        verdict = verify(paper or self.papers.get(doi, Paper(doi, "")), record_source(record), self.relations)
        if verdict.verdict not in PASSING_VERDICTS:
            return AbstractCheck(False, verdict.verdict, f"record_{verdict.rule}", verdict.related_doi)
        holder = self.unlinked_holder(doi, abstract)
        if holder:
            return AbstractCheck(False, "conflict", "abstract_on_unlinked_doi", holder)
        return AbstractCheck(True, verdict.verdict, f"record_{verdict.rule}", verdict.related_doi)

    def first_passing(self, doi: object, records: Iterable[dict]) -> tuple[dict | None, list[tuple[dict, AbstractCheck]]]:
        """The first record, in the order given, whose abstract passes, and the check of each record tried."""
        tried: list[tuple[dict, AbstractCheck]] = []
        for record in records:
            if not clean(record.get("abstract", "")):
                continue
            result = self.check(doi, record)
            tried.append((record, result))
            if result.passes:
                return record, tried
        return None, tried


def load_abstract_checker(ledger_path: Path | None = None) -> AbstractChecker:
    """A checker for the candidate ledger, with record corrections applied and the work registry's relations."""
    # Imported here: the audit module imports this one.
    from pipeline.identity.audit import DEFAULT_LEDGER, apply_record_corrections, decisions_by_doi, load_ledger
    from pipeline.identity.register import DEFAULT_DECISIONS_PATH
    from pipeline.identity.works import DEFAULT_WORK_REGISTRY, work_relation_index

    ledger = load_ledger(Path(ledger_path) if ledger_path else DEFAULT_LEDGER)
    apply_record_corrections(ledger, decisions_by_doi(DEFAULT_DECISIONS_PATH))
    return AbstractChecker.from_ledger(ledger, work_relation_index(DEFAULT_WORK_REGISTRY))


def provider_records_frame(rows: Iterable[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=list(PROVIDER_RECORD_COLUMNS))
    return frame.fillna("").astype(str)


def write_provider_records(rows: Iterable[dict], run_id: str, records_dir: Path = DEFAULT_PROVIDER_RECORDS_DIR) -> Path:
    """Keep the provider records a run read, one file per run."""
    path = Path(records_dir) / f"{clean(run_id)}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    provider_records_frame(rows).to_parquet(path, index=False)
    return path


def read_provider_records(
    records_dir: Path = DEFAULT_PROVIDER_RECORDS_DIR,
    discovery_runs: Path = DEFAULT_DISCOVERY_RUNS,
) -> pd.DataFrame:
    """All kept provider records: enrichment's, and discovery's from each run."""
    frames = [pd.read_parquet(path) for path in sorted(Path(records_dir).glob("*.parquet"))]
    for path in sorted(Path(discovery_runs).glob("*/retrieved_records.parquet")):
        found = pd.read_parquet(path)
        if found.empty:
            continue
        frames.append(
            provider_records_frame(
                {
                    "doi": doi,
                    "provider": provider,
                    "provider_record_id": record_id,
                    "record_doi": doi,
                    "record_pmid": pmid,
                    "record_pmcid": pmcid,
                    "record_title": title,
                    "abstract": abstract,
                    "retrieved_at_utc": "",
                    "run_id": path.parent.name,
                }
                for doi, provider, record_id, pmid, pmcid, title, abstract in zip(
                    *(
                        found[column] if column in found else [""] * len(found)
                        for column in ("doi", "provider", "provider_record_id", "pmid", "pmcid", "title", "abstract")
                    )
                )
            )
        )
    if not frames:
        return provider_records_frame([])
    frame = pd.concat(frames, ignore_index=True).fillna("").astype(str)
    frame["doi"] = frame["doi"].map(normalize_doi)
    return frame[frame["doi"] != ""].reset_index(drop=True)


def kept_abstracts(records: pd.DataFrame | None = None) -> dict[str, dict[str, str]]:
    """For each DOI, the abstracts kept provider records give, by their SHA-256."""
    from pipeline.identity.evidence import text_sha256

    records = read_provider_records() if records is None else records
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for doi, abstract in zip(records["doi"], records["abstract"]):
        abstract = clean(abstract)
        if abstract:
            out[doi][text_sha256(abstract)] = abstract
    return dict(out)
