"""Per-artifact access to the authoritative full-text source-identity audit.

The audit records one identity verdict per stored artifact.  The gate answers
whether one artifact may be used for one DOI: only when the audit verified that
exact artifact and nothing it depends on has changed since.  Every other case is
a rejection of that artifact alone, with a reason, so one unresolved artifact
never stops routing or packet building for the rest of the store.
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
    file_sha256,
    load_pdf_hash_attestation_registry,
    normalize_doi,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_IDENTITY_AUDIT = (
    ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
)
# Each registry, its label, and the audit-row flag that marks a DOI whose
# verdict used that registry when the audit ran.
REGISTRY_FIELDS = (
    ("identity_registry", "identity registry", "registry_record_present"),
    ("pdf_hash_attestation_registry", "PDF hash-attestation registry", "pdf_hash_attestation_present"),
)

GATE_VERIFIED = "verified"
GATE_ARTIFACT_MISSING = "artifact_missing"
GATE_NOT_AUDITED = "not_audited"
GATE_IDENTITY_UNVERIFIED = "identity_unverified"
GATE_ARTIFACT_CHANGED = "artifact_changed_after_audit"
GATE_REGISTRY_CHANGED = "registry_changed_after_audit"
GATE_REJECTION_REASONS = {
    GATE_ARTIFACT_MISSING: "the artifact file does not exist",
    GATE_NOT_AUDITED: "the artifact is absent from the source-identity audit",
    GATE_IDENTITY_UNVERIFIED: "the source-identity audit did not verify the artifact",
    GATE_ARTIFACT_CHANGED: "the artifact changed after the source-identity audit",
    GATE_REGISTRY_CHANGED: "a curated identity registry entry for this DOI changed after the audit",
}


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def registry_requested_dois(path: Path) -> set[str]:
    """Return the DOIs whose audit verdict can depend on one registry file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as err:
        raise RuntimeError(
            f"Could not read source-identity registry {path}: {type(err).__name__}: {err}"
        ) from err
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if isinstance(records, dict):
        records = list(records.values())
    return {
        doi
        for record in records
        if isinstance(record, dict) and (doi := normalize_doi(record.get("requested_doi", "")))
    }


class SourceIdentityAuditGate:
    """Match an exact DOI and resolved artifact path in the audit, per artifact."""

    def __init__(
        self,
        audit_path: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
        *,
        require_passing: bool = False,
    ) -> None:
        self.audit_path = Path(audit_path).expanduser().resolve()
        if not self.audit_path.is_file():
            raise FileNotFoundError(
                f"Source-identity audit is required before full-text routing or packet generation: "
                f"{self.audit_path}. Run audit_fulltext_source_identity.py."
            )
        try:
            payload = json.loads(self.audit_path.read_text(encoding="utf-8"))
        except Exception as err:
            raise RuntimeError(
                f"Could not read source-identity audit {self.audit_path}: {type(err).__name__}: {err}"
            ) from err
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise RuntimeError(f"Invalid source-identity audit structure: {self.audit_path}")

        self.audit_mtime_ns = self.audit_path.stat().st_mtime_ns
        self.payload = payload
        # (DOI, resolved artifact path) -> verdict and the content hash it was made on.
        self.audited: dict[tuple[str, str], dict[str, object]] = {}
        self.unverified_rows: list[dict] = []
        registry_dois_at_audit: dict[str, set[str]] = {key: set() for key, _label, _flag in REGISTRY_FIELDS}
        for row in payload["rows"]:
            if not isinstance(row, dict):
                continue
            doi = normalize_doi(row.get("requested_doi", ""))
            verified = clean_bool(row.get("identity_verified", False))
            if not verified:
                self.unverified_rows.append(row)
            artifact_raw = clean(row.get("artifact_path", ""))
            if doi and artifact_raw:
                self.audited[(doi, str(Path(artifact_raw).expanduser().resolve()))] = {
                    "verified": verified,
                    "artifact_sha256": clean(row.get("artifact_sha256", "")).casefold(),
                }
            for registry_key, _label, flag in REGISTRY_FIELDS:
                if doi and clean_bool(row.get(flag, False)):
                    registry_dois_at_audit[registry_key].add(doi)

        if require_passing and self.unverified_rows:
            sample = ", ".join(
                normalize_doi(row.get("requested_doi", ""))
                for row in self.unverified_rows[:5]
            )
            raise RuntimeError(
                f"Source-identity audit is not passing: {len(self.unverified_rows)} "
                f"artifact(s) are unverified ({sample}). Rerun "
                "audit_fulltext_source_identity.py after repair."
            )

        # A registry edited after the audit can change only the verdicts of the
        # DOIs it names now or named when the audit ran.  Those DOIs are not
        # usable until the audit is rerun; every other verdict stays valid.
        self.registry_changed_dois: set[str] = set()
        for registry_key, registry_label, _flag in REGISTRY_FIELDS:
            registry_meta = payload.get(registry_key)
            registry_raw = clean(
                registry_meta.get("path", "") if isinstance(registry_meta, dict) else ""
            )
            if not registry_raw:
                raise RuntimeError(
                    f"Source-identity audit does not identify its {registry_label}: {self.audit_path}"
                )
            registry_path = Path(registry_raw).expanduser().resolve()
            if not registry_path.is_file():
                raise FileNotFoundError(
                    f"Source-identity audit {registry_label} is missing: {registry_path}"
                )
            if self.audit_mtime_ns < registry_path.stat().st_mtime_ns:
                self.registry_changed_dois |= (
                    registry_requested_dois(registry_path) | registry_dois_at_audit[registry_key]
                )

        self.rejections: dict[tuple[str, str], str] = {}

    def status(self, doi: object, artifact_path: Path) -> str:
        """Return ``verified`` or the reason this artifact may not be used for ``doi``."""
        path = Path(artifact_path).expanduser().resolve()
        key = (normalize_doi(doi), str(path))
        if not path.is_file():
            return GATE_ARTIFACT_MISSING
        audited = self.audited.get(key)
        if audited is None:
            result = GATE_NOT_AUDITED
        elif key[0] in self.registry_changed_dois:
            result = GATE_REGISTRY_CHANGED
        elif not audited["verified"]:
            result = GATE_IDENTITY_UNVERIFIED
        elif self.audit_mtime_ns < path.stat().st_mtime_ns and not (
            audited["artifact_sha256"] and file_sha256(path) == audited["artifact_sha256"]
        ):
            # A newer file time alone is not a change when the audited content
            # hash still matches; without a recorded hash it must be re-audited.
            result = GATE_ARTIFACT_CHANGED
        else:
            result = GATE_VERIFIED
        if result != GATE_VERIFIED:
            self.rejections[key] = result
        return result

    def is_verified(self, doi: object, artifact_path: Path) -> bool:
        return self.status(doi, artifact_path) == GATE_VERIFIED

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for reason in self.rejections.values():
            counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))


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
    fail_on_unverified: bool = False,
) -> dict:
    """Regenerate the authoritative audit after a full-text artifact write.

    Unverified artifacts are recorded in the report and the unverified-DOI file;
    the gate leaves them unused, so they do not stop the calling run.  Artifacts
    the caller just wrote and the audit does not verify are returned under
    ``written_unverified_artifacts`` for the caller's report.
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
