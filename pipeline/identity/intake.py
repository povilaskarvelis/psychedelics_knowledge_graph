"""The identity check every path that stores a full text goes through.

A retrieval or conversion path builds the full-text artifact, asks
``FulltextIntake.may_store`` whether to write it, writes it, and passes the
written files to ``FulltextIntake.record``, which gives them their rows in the
verdict table. The check is the one the audit runs (``audit.check_fulltext``,
which calls ``verify.py``).

A text that is not verified is stored as well, so that it can be reviewed and
decided (``python -m pipeline.identity audit``); its row in the verdict table
leaves it unused, and the paper reads its abstract. It never replaces a stored
text that the table allows for the paper.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from pipeline.identity.apply import refresh_fulltext_rows
from pipeline.identity.audit import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_LEDGER,
    apply_record_corrections,
    check_fulltext,
    decisions_by_doi,
    load_ledger,
)
from pipeline.identity.bindings import IdentityVerdicts
from pipeline.identity.gate import DEFAULT_VERDICTS_PATH, require_current_inputs
from pipeline.identity.register import DEFAULT_DECISIONS_PATH
from pipeline.identity.verify import Verdict
from pipeline.identity.works import DEFAULT_WORK_REGISTRY, work_relation_index
from pipeline.ingest.candidate_status import clean, normalize_doi


STORED_VERIFIED = "stored: verified"
STORED_FOR_REVIEW = "stored for review, not used until decided"
KEPT_USABLE_TEXT = "not stored: the verdict table allows the stored text"
NO_EXTRACTION = "not stored: no successful extraction"


class FulltextIntake:
    def __init__(
        self,
        *,
        verdicts_path: Path = DEFAULT_VERDICTS_PATH,
        artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
        ledger_path: Path = DEFAULT_LEDGER,
        decisions_path: Path = DEFAULT_DECISIONS_PATH,
        work_registry: Path = DEFAULT_WORK_REGISTRY,
    ) -> None:
        self.verdicts_path = Path(verdicts_path)
        if not self.verdicts_path.is_file():
            raise FileNotFoundError(
                f"The verdict table is required before full texts are stored: {self.verdicts_path}. "
                "Run `python -m pipeline.identity apply --install`."
            )
        require_current_inputs(self.verdicts_path)
        self.artifact_dir = Path(artifact_dir)
        self.ledger_path = Path(ledger_path)
        self.decisions_path = Path(decisions_path)
        self.work_registry = Path(work_registry)
        self.ledger = load_ledger(self.ledger_path)
        apply_record_corrections(self.ledger, decisions_by_doi(self.decisions_path))
        self.relations = work_relation_index(self.work_registry)
        self.verdicts = IdentityVerdicts(self.verdicts_path)
        self.counts: Counter = Counter()

    def check(self, artifact_path: Path, artifact: dict) -> Verdict:
        """The computed verdict for a text before it is stored."""
        doi = normalize_doi(artifact.get("study_doi", ""))
        return check_fulltext(Path(artifact_path), artifact, doi, self.ledger, self.relations, self.counts).verdict

    def may_store(self, artifact_path: Path, artifact: dict) -> tuple[bool, str, Verdict | None]:
        """Whether to write the artifact, why, and its computed verdict."""
        if not clean(artifact.get("best_backend", "")):
            return False, NO_EXTRACTION, None
        verdict = self.check(artifact_path, artifact)
        if verdict.verdict == "verified":
            return True, STORED_VERIFIED, verdict
        stored = self.verdicts.fulltext(artifact.get("study_doi", ""), artifact_path)
        if stored is not None and stored["usable"] and Path(artifact_path).is_file():
            return False, KEPT_USABLE_TEXT, verdict
        return True, STORED_FOR_REVIEW, verdict

    def record(self, written_artifacts: Iterable[Path | str]) -> list[str]:
        """Give written texts their verdict-table rows; return those the table does not make usable."""
        written = [str(path) for path in written_artifacts]
        if not written:
            return []
        return refresh_fulltext_rows(
            written,
            artifact_dir=self.artifact_dir,
            verdicts_path=self.verdicts_path,
            ledger_path=self.ledger_path,
            decisions_path=self.decisions_path,
            work_registry=self.work_registry,
        )
