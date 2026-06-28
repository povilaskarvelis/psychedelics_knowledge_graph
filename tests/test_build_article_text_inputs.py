import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from pipeline.fulltext.build_article_text_inputs import build_article_text_inputs


TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract><p>This article reports a psilocybin experiment.</p></abstract>
    </front>
    <body>
      <div><head>Introduction</head><p>Background material.</p></div>
      <div><head>Methods</head><p>Participants received psilocybin.</p></div>
      <div><head>Results</head><p>Clinical outcomes improved.</p></div>
      <div><head>Discussion</head><p>Interpretation and speculation.</p></div>
    </body>
  </text>
</TEI>
"""


def make_args(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        route_table=str(root / "routes.parquet"),
        out_jsonl=str(root / "article_text_inputs.jsonl"),
        report_json=str(root / "report.json"),
        audit_csv=str(root / "audit.csv"),
        audit_md=str(root / "audit.md"),
        policy_csv="",
        primary_section_selection_strategy="primary_study",
        secondary_section_selection_strategy="all_sections",
        prompt_profile=[],
        schema_profile=[],
        domain_route=[],
        limit=0,
        max_chunk_chars=500,
        chunk_overlap_chars=0,
        max_chunks_per_paper=0,
        max_references=50,
        large_token_threshold=25000,
        include_unretained=False,
        markdown_preview_limit=10,
    )


def route_row(**overrides: object) -> dict:
    row = {
        "route_id": "route-primary",
        "doi": "10.1000/article",
        "retained_for_extraction_candidate": True,
        "study_title": "Example article",
        "study_year": "2026",
        "source_type": "primary_or_unclear",
        "domain_route": "clinical_outcome",
        "prompt_profile": "primary_clinical",
        "schema_profile": "primary_evidence_schema",
        "route_action": "extract_from_full_text",
        "fulltext_artifact_paths": "",
    }
    row.update(overrides)
    return row


def test_build_article_text_inputs_uses_primary_selection_and_secondary_full_text() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        artifact_path = root / "artifact.json"
        route_doi = "10.1000/article/with/slashes"
        artifact_path.write_text(
            json.dumps(
                {
                    "study_doi": "10.1000/article_with_slashes",
                    "study_title": "Example article",
                    "best_backend": "grobid",
                    "best_char_count": len(TEI),
                    "best_section_count": 4,
                    "extractions": [{"backend": "grobid", "status": "ok", "text": TEI}],
                }
            ),
            encoding="utf-8",
        )
        pd.DataFrame(
            [
                route_row(doi=route_doi, fulltext_artifact_paths=str(artifact_path)),
                route_row(
                    doi=route_doi,
                    route_id="route-meta",
                    source_type="meta_analysis",
                    prompt_profile="secondary_meta_analysis",
                    schema_profile="meta_analysis_evidence_schema",
                    fulltext_artifact_paths=str(artifact_path),
                ),
            ]
        ).to_parquet(root / "routes.parquet", engine="pyarrow", index=False)

        report, audit_rows, packets = build_article_text_inputs(make_args(root))

    assert report["packets_written"] == 2
    assert report["by_packet_profile"] == {"full": 1, "primary_empirical": 1}
    by_profile = {packet["packet_profile"]: packet for packet in packets}
    assert {packet["study_doi"] for packet in packets} == {route_doi}

    primary_text = "\n".join(chunk["text"] for chunk in by_profile["primary_empirical"]["llm_chunks"])
    assert "Participants received psilocybin" in primary_text
    assert "Clinical outcomes improved" in primary_text
    assert "Background material" not in primary_text
    assert "Interpretation and speculation" not in primary_text

    secondary_text = "\n".join(chunk["text"] for chunk in by_profile["full"]["llm_chunks"])
    assert "Background material" in secondary_text
    assert "Participants received psilocybin" in secondary_text
    assert "Clinical outcomes improved" in secondary_text
    assert "Interpretation and speculation" in secondary_text

    by_strategy = {row["section_selection_strategy"]: row for row in audit_rows}
    assert by_strategy["primary_study"]["status"] == "ok"
    assert by_strategy["all_sections"]["status"] == "ok"
