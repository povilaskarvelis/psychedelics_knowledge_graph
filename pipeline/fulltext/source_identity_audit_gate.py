"""Refresh the identity records after a full-text artifact is written.

The acquisition audit report is regenerated, and the written artifacts get new
rows in the verdict table, which is what the gate reads (``pipeline/identity/gate.py``).
"""

from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path

from pipeline.fulltext.audit_fulltext_source_identity import (
    DEFAULT_IDENTITY_REGISTRY,
    DEFAULT_REPORT_CSV as DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
    DEFAULT_UNVERIFIED_DOIS as DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
    audit_artifacts,
    load_identity_registry,
    metadata_map as source_identity_metadata_map,
    write_csv as write_source_identity_audit_csv,
)
from pipeline.fulltext.source_identity import (
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    clean,
    load_pdf_hash_attestation_registry,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_IDENTITY_AUDIT = (
    ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
)


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def refresh_source_identity_audit(
    *,
    artifact_dir: Path,
    candidate_table: Path,
    metadata_table: Path,
    report_json: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
    report_csv: Path = DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
    unverified_doi_file: Path = DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
    identity_registry_path: Path = DEFAULT_IDENTITY_REGISTRY,
    pdf_hash_attestation_registry_path: Path = DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    written_artifacts: Iterable[Path | str] = (),
    identity_verdicts: Path | None = None,
    fail_on_unverified: bool = False,
) -> dict:
    """Regenerate the acquisition audit and the verdict rows of the written artifacts.

    Written artifacts the verdict table does not make usable are returned under
    ``written_unverified_artifacts`` for the caller's report; the gate leaves them
    unused, so they do not stop the calling run. Without ``identity_verdicts``, or
    before a table is installed, the audit report decides that list.
    ``fail_on_unverified`` keeps the strict whole-store check for explicit audits.
    """

    report = audit_artifacts(
        Path(artifact_dir).resolve(),
        source_identity_metadata_map(
            Path(metadata_table).resolve(),
            Path(candidate_table).resolve(),
        ),
        identity_registry=load_identity_registry(Path(identity_registry_path).resolve()),
        pdf_hash_registry=load_pdf_hash_attestation_registry(
            Path(pdf_hash_attestation_registry_path).resolve()
        ),
    )
    report_json = Path(report_json).resolve()
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_source_identity_audit_csv(Path(report_csv).resolve(), report["rows"])
    unverified = [
        clean(row.get("requested_doi", ""))
        for row in report["rows"]
        if not clean_bool(row.get("identity_verified", False))
        and clean(row.get("requested_doi", ""))
    ]
    unverified_path = Path(unverified_doi_file).resolve()
    unverified_path.parent.mkdir(parents=True, exist_ok=True)
    unverified_path.write_text(
        "".join(f"{doi}\n" for doi in unverified),
        encoding="utf-8",
    )
    if identity_verdicts is not None and Path(identity_verdicts).is_file():
        # Imported here: the identity package needs the ledger and the PDF checks.
        from pipeline.identity.apply import refresh_fulltext_rows

        report["written_unverified_artifacts"] = refresh_fulltext_rows(
            written_artifacts, artifact_dir=Path(artifact_dir).resolve(), verdicts_path=Path(identity_verdicts)
        )
    else:
        verified_paths = {
            str(Path(clean(row.get("artifact_path", ""))).resolve())
            for row in report["rows"]
            if clean_bool(row.get("identity_verified", False)) and clean(row.get("artifact_path", ""))
        }
        report["written_unverified_artifacts"] = sorted(
            {
                str(Path(path).resolve())
                for path in written_artifacts
                if str(Path(path).resolve()) not in verified_paths
            }
        )
    if fail_on_unverified and unverified:
        raise RuntimeError(
            "Source-identity audit found unverified full-text artifacts; "
            f"see {report_json} and {unverified_path}."
        )
    return report
