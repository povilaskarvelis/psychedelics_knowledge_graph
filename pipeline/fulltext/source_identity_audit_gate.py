"""Fail-closed access to the authoritative full-text source-identity audit."""

from __future__ import annotations

from collections import defaultdict
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
    normalize_doi,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_IDENTITY_AUDIT = (
    ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
)
REGISTRY_FIELDS = (
    ("identity_registry", "identity registry"),
    ("pdf_hash_attestation_registry", "PDF hash-attestation registry"),
)


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).casefold() in {"1", "true", "yes", "y"}


class SourceIdentityAuditGate:
    """Match an exact DOI and resolved artifact path in a fresh audit."""

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
                f"{self.audit_path}. Run audit_fulltext_source_identity.py --fail-on-unverified."
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
        self.verified_paths: dict[str, set[str]] = defaultdict(set)
        self.unverified_rows: list[dict] = []
        for row in payload["rows"]:
            if not isinstance(row, dict):
                continue
            if not clean_bool(row.get("identity_verified", False)):
                self.unverified_rows.append(row)
                continue
            doi = normalize_doi(row.get("requested_doi", ""))
            artifact_raw = clean(row.get("artifact_path", ""))
            if doi and artifact_raw:
                self.verified_paths[doi].add(
                    str(Path(artifact_raw).expanduser().resolve())
                )

        if require_passing and self.unverified_rows:
            sample = ", ".join(
                normalize_doi(row.get("requested_doi", ""))
                for row in self.unverified_rows[:5]
            )
            raise RuntimeError(
                f"Source-identity audit is not passing: {len(self.unverified_rows)} "
                f"artifact(s) are unverified ({sample}). Rerun "
                "audit_fulltext_source_identity.py --fail-on-unverified after repair."
            )

        for registry_key, registry_label in REGISTRY_FIELDS:
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
                raise RuntimeError(
                    f"Source-identity audit is stale: the {registry_label} changed after the audit. "
                    "Rerun audit_fulltext_source_identity.py --fail-on-unverified."
                )

    def is_verified(self, doi: object, artifact_path: Path) -> bool:
        path = Path(artifact_path).expanduser().resolve()
        if not path.is_file():
            return False
        if self.audit_mtime_ns < path.stat().st_mtime_ns:
            raise RuntimeError(
                f"Source-identity audit is stale: artifact changed after the audit: {path}. "
                "Rerun audit_fulltext_source_identity.py --fail-on-unverified."
            )
        return str(path) in self.verified_paths.get(normalize_doi(doi), set())


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
    fail_on_unverified: bool = True,
) -> dict:
    """Regenerate the authoritative audit after a full-text artifact write."""

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
    if fail_on_unverified and unverified:
        raise RuntimeError(
            "Source-identity audit found unverified full-text artifacts; downstream routing "
            f"aborted. See {report_json} and {unverified_path}."
        )
    return report
