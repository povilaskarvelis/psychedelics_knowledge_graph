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
    args = parser.parse_args(argv)

    if args.command == "migrate":
        report = run_migration(decisions_path=args.decisions, check=args.check)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if args.check and not report["in_sync_before"] else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
