"""The verdict table: which texts the pipeline may read for each paper.

The table has one row per stored full text, and one per abstract or record
that a current decision names. A text's verdict is the current reviewed
decision about it (``register.py``) when there is one, and otherwise the
verdict ``verify.py`` computes from the text's own evidence. ``usable`` says
whether extraction may read the text:

| Verdict | Usable |
|---|---|
| ``verified`` | yes |
| ``version_of`` | yes, except a full text that is a preprint or an accepted manuscript, which follows the version-text policy (decision D1) |
| ``unconfirmed``, ``conflict``, ``wrong_kind``, ``not_this_work`` | no |

A record row withholds the paper: ``hold`` until its source is resolved,
``wrong_doi`` when its DOI belongs to another work. Record corrections change
field values and have no row.

``apply`` writes the table, and ``IdentityVerdicts`` reads it.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.fulltext.source_identity import file_sha256
from pipeline.identity.audit import check_fulltext, stored_fulltexts, target_matches
from pipeline.identity.evidence import VERSION_DOI_KINDS, doi_kind, text_sha256
from pipeline.ingest.candidate_status import clean, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERDICTS_PATH = ROOT / "data" / "processed" / "identity" / "verdicts.parquet"
# Decision D1: a published paper's full text is never a preprint of it. Accepted
# manuscripts are peer reviewed and are used. A paper whose own DOI is a preprint
# or repository deposit may read the published text.
PREPRINT_RELATIONS = frozenset({"preprint", "preprint_or_repository_copy"})
WITHHOLDING_VERDICTS = frozenset({"hold", "wrong_doi"})
TABLE_COLUMNS = (
    "doi",
    "target_kind",
    "artifact",
    "artifact_sha256",
    "text_sha256",
    "computed_verdict",
    "computed_rule",
    "decision_ids",
    "verdict",
    "relation",
    "related_doi",
    "usable",
    "reason",
)


def usable_for(target_kind: str, verdict: str, relation: str, doi: str) -> tuple[bool, str]:
    """Whether extraction may read a text with this verdict, and why."""
    if verdict == "verified":
        return True, "verified"
    if verdict == "version_of":
        if target_kind == "fulltext" and relation in PREPRINT_RELATIONS and doi_kind(doi) not in VERSION_DOI_KINDS:
            return False, f"version_of ({relation}): a published paper does not read a preprint"
        return True, f"version_of ({relation})"
    return False, verdict


def fulltext_rows(
    ledger: pd.DataFrame,
    artifact_dir: Path,
    relations: dict[frozenset[str], str],
    decisions: dict[str, list[dict]],
    *,
    read_pdfs: bool = True,
) -> tuple[list[dict], Counter]:
    """One row per stored full text: the decision about it, or else the computed verdict."""
    counts: Counter = Counter()
    rows = []
    for path, artifact, doi in stored_fulltexts(artifact_dir, counts):
        check = check_fulltext(path, artifact, doi, ledger, relations, counts, read_pdfs=read_pdfs)
        computed = check.verdict
        artifact_sha = file_sha256(path)
        text_decisions = [d for d in decisions.get(doi, []) if d["target"].get("kind") == "fulltext"]
        covering: list[dict] = []
        if text_decisions:
            text_ids = {"sha256": {artifact_sha}, "document_doi": {normalize_doi(value) for value in check.header_dois}}
            named_by_pdf = any(clean(d["target"].get("pdf_sha256", "")) for d in text_decisions)
            if named_by_pdf and check.pdf_path and check.pdf_path.is_file():
                text_ids["pdf_sha256"] = {file_sha256(check.pdf_path)}
            covering = [d for d in text_decisions if target_matches(d["target"], text_ids)]
        # The latest current decision about the text applies.
        decision = covering[-1] if covering else None
        verdict = decision["verdict"] if decision else computed.verdict
        relation = clean(decision.get("relation", "")) if decision else computed.relation
        related = normalize_doi(decision.get("related_doi", "")) if decision else computed.related_doi
        usable, reason = usable_for("fulltext", verdict, relation, doi)
        counts[f"{'decided' if decision else 'computed'}_{verdict}"] += 1
        rows.append(
            {
                "doi": doi,
                "target_kind": "fulltext",
                "artifact": path.name,
                "artifact_sha256": artifact_sha,
                "text_sha256": "",
                "computed_verdict": computed.verdict,
                "computed_rule": computed.rule,
                "decision_ids": " ".join(d["decision_id"] for d in covering),
                "verdict": verdict,
                "relation": relation,
                "related_doi": related,
                "usable": usable,
                "reason": reason if usable or decision else f"{reason}: {computed.rule}",
            }
        )
    return rows, counts


def decision_rows(decisions: dict[str, list[dict]]) -> tuple[list[dict], Counter]:
    """Rows for abstracts that decisions name, and for records that decisions withhold."""
    counts: Counter = Counter()
    rows = []
    for doi, doi_decisions in sorted(decisions.items()):
        for decision in doi_decisions:
            kind, verdict = decision["target"].get("kind"), decision["verdict"]
            if kind == "abstract":
                relation = clean(decision.get("relation", ""))
                usable, reason = usable_for("abstract", verdict, relation, doi)
            elif kind == "record" and verdict in WITHHOLDING_VERDICTS:
                relation, usable, reason = "", False, f"{verdict}: {decision['basis']}"
            else:
                continue
            counts[f"{kind}_{verdict}"] += 1
            rows.append(
                {
                    "doi": doi,
                    "target_kind": kind,
                    "artifact": "",
                    "artifact_sha256": "",
                    "text_sha256": clean(decision["target"].get("sha256", "")),
                    "computed_verdict": "",
                    "computed_rule": "",
                    "decision_ids": decision["decision_id"],
                    "verdict": verdict,
                    "relation": relation,
                    "related_doi": normalize_doi(decision.get("related_doi", "")),
                    "usable": usable,
                    "reason": reason,
                }
            )
    return rows, counts


def verdict_table(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(TABLE_COLUMNS))
    for column in TABLE_COLUMNS:
        if column != "usable":
            frame[column] = frame[column].fillna("").astype(str)
    frame["usable"] = frame["usable"].astype(bool)
    return frame.sort_values(["doi", "target_kind", "artifact", "text_sha256"]).reset_index(drop=True)


class IdentityVerdicts:
    """Lookups in a verdict table."""

    def __init__(self, table: pd.DataFrame | Path = DEFAULT_VERDICTS_PATH) -> None:
        frame = pd.read_parquet(table) if isinstance(table, (str, Path)) else table
        rows = frame.to_dict("records")
        self.fulltexts = {(row["doi"], row["artifact"]): row for row in rows if row["target_kind"] == "fulltext"}
        self.abstracts: dict[str, list[dict]] = {}
        self.withholding: dict[str, dict] = {}
        for row in rows:
            if row["target_kind"] == "abstract":
                self.abstracts.setdefault(row["doi"], []).append(row)
            elif row["target_kind"] == "record":
                self.withholding[row["doi"]] = row

    def fulltext(self, doi: object, artifact_path: Path) -> dict | None:
        return self.fulltexts.get((normalize_doi(doi), Path(artifact_path).name))

    def abstract(self, doi: object, abstract: object) -> dict | None:
        """The decision row about this abstract, matched by its SHA-256; ``None`` when undecided."""
        sha = text_sha256(clean(abstract))
        matching = [row for row in self.abstracts.get(normalize_doi(doi), []) if row["text_sha256"] == sha]
        return matching[-1] if matching else None

    def abstract_usable(self, doi: object, abstract: object) -> bool:
        if not clean(abstract):
            return False
        row = self.abstract(doi, abstract)
        return row is None or bool(row["usable"])

    def withheld(self, doi: object) -> dict | None:
        return self.withholding.get(normalize_doi(doi))
