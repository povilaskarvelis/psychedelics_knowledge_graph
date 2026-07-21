from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.fulltext.register_retrieved_pdf_aliases import select_aliases


def test_select_aliases_preserves_explicit_relationship_type() -> None:
    with TemporaryDirectory() as tmpdir:
        audit = Path(tmpdir) / "aliases.csv"
        pd.DataFrame(
            [
                {
                    "requested_doi": "10.1254/example",
                    "foreign_front_dois": "10.1016/example",
                    "front_title_score": 1.0,
                    "final_outcome": "alias_or_foreign_doi_mismatch",
                    "relationship_type": "alternate_journal_doi",
                    "artifact_evidence": "Exact title, authors, journal, and year match.",
                }
            ]
        ).to_csv(audit, index=False)

        rows = select_aliases([audit], {"10.1254/example", "10.1016/example"})

        assert rows == [
            {
                "alias_doi": "10.1254/example",
                "canonical_doi": "10.1016/example",
                "relationship_type": "alternate_journal_doi",
                "evidence_basis": "Exact title, authors, journal, and year match.",
                "source_artifact": str(audit.resolve()),
            }
        ]
