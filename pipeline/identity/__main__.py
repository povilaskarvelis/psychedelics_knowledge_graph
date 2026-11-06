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
    decide = commands.add_parser(
        "decide",
        help="Append reviewed decisions to the decision file, from an audit queue, a CSV or one at a time.",
    )
    source = decide.add_mutually_exclusive_group(required=True)
    source.add_argument("--queue", type=Path, help="An audit folder or its review_queue.csv: decide on its items.")
    source.add_argument("--csv", type=Path, help="A CSV with the decision file's fields; target, fields, clear_fields and evidence hold JSON.")
    source.add_argument("--doi", help="Decide on one paper.")
    decide.add_argument(
        "--where",
        action="append",
        default=[],
        metavar="COLUMN=VALUE",
        help="With --queue: select items; COLUMN!=VALUE excludes. Repeatable; every condition must hold.",
    )
    decide.add_argument(
        "--accept-suggested",
        action="store_true",
        help="With --queue: record each selected item's suggested decision. Items without one are skipped.",
    )
    decide.add_argument("--target", help='With --doi: the text or record, as JSON, e.g. {"kind": "fulltext", "sha256": "..."}.')
    decide.add_argument("--verdict", help="The verdict; with --queue it replaces the suggestion for every selected item.")
    decide.add_argument("--relation", default="", help="For version_of: how the text's work relates to the paper.")
    decide.add_argument("--related-doi", default="", help="For version_of: the DOI the text carries.")
    decide.add_argument("--fields", default="", help="For record_corrected: replaced values as JSON, keyed by ledger column.")
    decide.add_argument("--clear-field", action="append", default=[], help="For record_corrected: a ledger column to clear; repeatable.")
    decide.add_argument("--basis", default="", help="Why; required unless every CSV row gives one.")
    decide.add_argument("--reviewer", default="", help="Who decided; required unless every CSV row gives one.")
    decide.add_argument("--evidence", action="append", default=[], help="A file or record the decision rests on; repeatable.")
    decide.add_argument("--decided-at", default="", help="ISO date (default: today).")
    decide.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    decide.add_argument("--work-registry", type=Path, help="Work registry (default: pipeline/validate/doi_alias_registry.json).")
    decide.add_argument("--ledger", type=Path, help="Candidate ledger, for record and abstract decisions.")
    decide.add_argument("--artifact-dir", type=Path, help="Stored full texts (default: data/processed/fulltext/articles).")
    decide.add_argument("--dry-run", action="store_true", help="Check and report; write nothing.")
    apply = commands.add_parser(
        "apply",
        help="Recompute verdicts with the decisions and list the papers whose text changes. "
        "Writes a new update folder; changes what the pipeline reads only with --install.",
    )
    apply.add_argument("--update-id", help="Name of the update folder (default: identity_<UTC time>).")
    apply.add_argument(
        "--outputs",
        type=Path,
        action="append",
        help="Extraction outputs of the base release; repeatable. Without --outputs and --kg-dir, the active release is used.",
    )
    apply.add_argument("--kg-dir", type=Path, help="KG tables of the base release, for findings per paper.")
    apply.add_argument("--ledger", type=Path, help="Candidate ledger (default: data/processed/corpus/candidate_papers.parquet).")
    apply.add_argument("--artifact-dir", type=Path, help="Stored full texts (default: data/processed/fulltext/articles).")
    apply.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    apply.add_argument("--work-registry", type=Path, help="Work registry (default: pipeline/validate/doi_alias_registry.json).")
    apply.add_argument("--route-table", type=Path, help="Route table, for the papers held now.")
    apply.add_argument("--out-root", type=Path, help="Folder for update folders (default: data/processed/identity/updates).")
    apply.add_argument("--no-pdf", action="store_true", help="Do not read the first pages of stored PDFs.")
    apply.add_argument("--install", action="store_true", help="Make the new table the one the pipeline reads.")
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
    if args.command == "decide":
        return run_decide(args, parser)
    if args.command == "apply":
        from pipeline.identity import apply as identity_apply

        options = {
            "update_id": args.update_id,
            "outputs": args.outputs,
            "kg_dir": args.kg_dir,
            "ledger_path": args.ledger,
            "artifact_dir": args.artifact_dir,
            "decisions_path": args.decisions,
            "work_registry": args.work_registry,
            "route_table": args.route_table,
            "out_root": args.out_root,
        }
        summary = identity_apply.run_apply(
            **{key: value for key, value in options.items() if value is not None},
            read_pdfs=not args.no_pdf,
            install=args.install,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    return 2


def run_decide(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from pipeline.identity import decide as identity_decide

    if args.accept_suggested and not args.queue:
        parser.error("--accept-suggested needs --queue")
    if args.queue and not (args.accept_suggested or args.verdict):
        parser.error("--queue needs --accept-suggested or --verdict")
    if args.queue:
        decisions, counts = identity_decide.decisions_from_queue(
            args.queue,
            args.where,
            basis=args.basis,
            reviewer=args.reviewer,
            verdict=args.verdict or "",
            relation=args.relation,
            related_doi=args.related_doi,
            evidence=args.evidence,
            decided_at=args.decided_at,
        )
    elif args.csv:
        decisions, counts = (
            identity_decide.decisions_from_csv(args.csv, basis=args.basis, reviewer=args.reviewer, decided_at=args.decided_at),
            {},
        )
    else:
        if not args.target or not args.verdict:
            parser.error("--doi needs --target and --verdict")
        decisions, counts = (
            [
                identity_decide.make_decision(
                    doi=args.doi,
                    target=json.loads(args.target),
                    verdict=args.verdict,
                    relation=args.relation,
                    related_doi=args.related_doi,
                    fields=json.loads(args.fields) if args.fields else None,
                    clear_fields=args.clear_field,
                    basis=args.basis,
                    reviewer=args.reviewer,
                    evidence=args.evidence,
                    decided_at=args.decided_at,
                )
            ],
            {},
        )
    texts = identity_decide.Texts(
        **{
            key: value
            for key, value in {"artifact_dir": args.artifact_dir, "ledger_path": args.ledger}.items()
            if value is not None
        },
        decisions_path=args.decisions,
    )
    options = {"work_registry": args.work_registry} if args.work_registry else {}
    try:
        report = identity_decide.record_decisions(
            decisions, decisions_path=args.decisions, texts=texts, dry_run=args.dry_run, **options
        )
    except ValueError as err:
        print(err)
        return 1
    report["selection"] = dict(counts)
    print(json.dumps({key: value for key, value in report.items() if key != "decision_ids"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
