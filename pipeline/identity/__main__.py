"""Commands for source-identity decisions: ``python -m pipeline.identity <command>``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.identity.migrate import run_migration
from pipeline.identity.register import DEFAULT_DECISIONS_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.identity", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser(
        "migrate",
        help="Copy decisions from the older identity files into the one decision file.",
    )
    migrate.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    migrate.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; exit 1 when the decision file no longer matches its sources.",
    )
    audit = commands.add_parser(
        "audit",
        help="List the texts and records that need an identity decision. Writes only a new audit folder.",
    )
    audit.add_argument("--ledger", type=Path, help="Candidate ledger (default: data/processed/corpus/candidate_papers.parquet).")
    audit.add_argument("--artifact-dir", type=Path, help="Stored full texts (default: data/processed/fulltext/articles).")
    audit.add_argument("--discovery-runs", type=Path, help="Discovery runs with stored provider records.")
    audit.add_argument(
        "--outputs",
        type=Path,
        action="append",
        help="Extraction outputs of the release to check for model statements; repeatable. "
        "Without --outputs and --kg-dir, the active release is used.",
    )
    audit.add_argument("--kg-dir", type=Path, help="KG tables of the release, for findings per paper.")
    audit.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    audit.add_argument("--work-registry", type=Path, help="Work registry (default: pipeline/validate/doi_alias_registry.json).")
    audit.add_argument("--out-root", type=Path, help="Folder for audit runs (default: data/processed/identity/audits).")
    audit.add_argument("--no-pdf", action="store_true", help="Do not read the first pages of stored PDFs.")
    audit.add_argument(
        "--include-corpus",
        action="store_true",
        help="Also queue items about records that are neither in the release nor retained for extraction.",
    )
    args = parser.parse_args(argv)

    if args.command == "migrate":
        report = run_migration(decisions_path=args.decisions, check=args.check)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if args.check and not report["in_sync_before"] else 0
    if args.command == "audit":
        # Imported here: the audit reads large tables that migrate does not need.
        from pipeline.identity import audit as identity_audit

        options = {
            "ledger_path": args.ledger,
            "artifact_dir": args.artifact_dir,
            "discovery_runs": args.discovery_runs,
            "outputs": args.outputs,
            "kg_dir": args.kg_dir,
            "decisions_path": args.decisions,
            "work_registry": args.work_registry,
            "out_root": args.out_root,
        }
        summary = identity_audit.run_audit(
            **{key: value for key, value in options.items() if value is not None},
            read_pdfs=not args.no_pdf,
            include_corpus=args.include_corpus,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
