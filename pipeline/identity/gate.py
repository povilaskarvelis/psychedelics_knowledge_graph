"""The full-text gate: whether one stored text may be read for one paper.

The gate reads the verdict table (``bindings.py``). A text may be read only when
the table has a row for this paper and this text, the row is usable, and the
file is the one the row was made on. Every other case rejects that text alone,
with a reason, so one unresolved text never stops routing or packet building
for the rest of the store. A paper whose text is rejected falls back to its
abstract.

The table depends on the decision file and the work registry. When either has
changed since ``apply --install`` the gate stops, because any verdict may be out
of date: the table is rebuilt with ``python -m pipeline.identity apply --install``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.source_identity import clean, file_sha256, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERDICTS_PATH = ROOT / "data" / "processed" / "identity" / "verdicts.parquet"

GATE_VERIFIED = "verified"
GATE_ARTIFACT_MISSING = "artifact_missing"
GATE_NOT_AUDITED = "not_audited"
GATE_IDENTITY_UNVERIFIED = "identity_unverified"
GATE_ARTIFACT_CHANGED = "artifact_changed_after_audit"
GATE_REJECTION_REASONS = {
    GATE_ARTIFACT_MISSING: "the artifact file does not exist",
    GATE_NOT_AUDITED: "the artifact is absent from the verdict table",
    GATE_IDENTITY_UNVERIFIED: "the verdict table does not allow the artifact",
    GATE_ARTIFACT_CHANGED: "the artifact changed after the verdict table was built",
}


def require_current_inputs(verdicts_path: Path) -> None:
    """Stop when the decisions or the work registry changed after the table was installed."""
    summary_path = verdicts_path.with_suffix(".json")
    if not summary_path.is_file():
        return
    inputs = json.loads(summary_path.read_text(encoding="utf-8")).get("inputs", {})
    for name, path_key, digest_key in (
        ("decision file", "decisions", "decisions_sha256"),
        ("work registry", "work_registry", "work_registry_sha256"),
    ):
        path = Path(clean(inputs.get(path_key, "")))
        recorded = clean(inputs.get(digest_key, ""))
        if not recorded or not path.is_file():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != recorded:
            raise RuntimeError(
                f"The {name} changed after the verdict table {verdicts_path} was installed. "
                "Run `python -m pipeline.identity apply --install`."
            )


class IdentityGate:
    """Match a DOI and a stored text in the verdict table."""

    def __init__(self, verdicts_path: Path = DEFAULT_VERDICTS_PATH) -> None:
        self.verdicts_path = Path(verdicts_path).expanduser().resolve()
        if not self.verdicts_path.is_file():
            raise FileNotFoundError(
                f"The verdict table is required before full-text routing or packet generation: "
                f"{self.verdicts_path}. Run `python -m pipeline.identity apply --install`."
            )
        require_current_inputs(self.verdicts_path)
        self.table_mtime_ns = self.verdicts_path.stat().st_mtime_ns
        frame = pd.read_parquet(self.verdicts_path)
        rows = frame.loc[frame["target_kind"] == "fulltext"].to_dict("records")
        self.withholding = {row["doi"]: row["reason"] for row in frame.loc[frame["target_kind"] == "record"].to_dict("records")}
        self.rows = {(row["doi"], row["artifact"]): row for row in rows}
        self.carried = {row["doi"]: row["artifact"] for row in rows if row["usable"] and clean(row["carried_from"])}
        self.rejections: dict[tuple[str, str], str] = {}

    def status(self, doi: object, artifact_path: Path) -> str:
        """Return ``verified`` or the reason this text may not be read for ``doi``."""
        path = Path(artifact_path).expanduser().resolve()
        key = (normalize_doi(doi), path.name)
        if not path.is_file():
            return GATE_ARTIFACT_MISSING
        row = self.rows.get(key)
        if row is None:
            result = GATE_NOT_AUDITED
        elif not row["usable"]:
            result = GATE_IDENTITY_UNVERIFIED
        elif self.table_mtime_ns < path.stat().st_mtime_ns and file_sha256(path) != row["artifact_sha256"]:
            # A newer file time alone is not a change when the content hash still matches.
            result = GATE_ARTIFACT_CHANGED
        else:
            result = GATE_VERIFIED
        if result != GATE_VERIFIED:
            self.rejections[key] = result
        return result

    def is_verified(self, doi: object, artifact_path: Path) -> bool:
        return self.status(doi, artifact_path) == GATE_VERIFIED

    def carried_artifact(self, doi: object) -> str:
        """The file name of another DOI's text that this paper reads, or ``""``."""
        return self.carried.get(normalize_doi(doi), "")

    def withheld(self, doi: object) -> str:
        """Why a record decision withholds this paper, or ``""``."""
        return self.withholding.get(normalize_doi(doi), "")

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for reason in self.rejections.values():
            counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))
