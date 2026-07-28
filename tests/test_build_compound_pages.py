from __future__ import annotations

import json
from pathlib import Path

from scripts.build_compound_pages import (
    FIELD_NAMES,
    build_compound_payload,
    render_compound_page,
    write_compound_page,
)

ROOT = Path(__file__).resolve().parents[1]


def write_columnar_payload(path: Path, findings: list[dict]) -> None:
    values: list[object] = [""]
    value_indices: dict[str, int] = {}
    rows: list[list[int]] = []

    for finding in findings:
        row = []
        for field in FIELD_NAMES:
            value = finding.get(field, "")
            if value in ("", None):
                row.append(0)
                continue
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if key not in value_indices:
                value_indices[key] = len(values)
                values.append(value)
            row.append(value_indices[key])
        rows.append(row)

    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-28T00:00:00+00:00",
                "fields": list(FIELD_NAMES),
                "values": values,
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )


def finding(**overrides: object) -> dict:
    payload = {
        "domain": "clinical_outcome",
        "compound": "Psilocybin",
        "entity_label": "Major depressive disorder",
        "graph_entity_label": "Major depressive disorder",
        "entity_kind": "condition_indication",
        "study_doi": "10.1000/primary",
        "study_title": "A primary psilocybin study",
        "study_year": 2025,
        "study_journal": "Example Journal",
        "authors": "A. Example; B. Example",
        "text_depth": "article_text",
    }
    payload.update(overrides)
    return payload


def test_compound_payload_deduplicates_papers_and_preserves_source_counts(
    tmp_path: Path,
) -> None:
    detail_paths = {
        "primary": tmp_path / "primary.json",
        "meta_analyses": tmp_path / "meta.json",
        "reviews": tmp_path / "reviews.json",
    }
    write_columnar_payload(
        detail_paths["primary"],
        [
            finding(),
            finding(text_depth="abstract_only"),
            finding(
                entity_label="BDNF expression",
                graph_entity_label="BDNF expression",
                graph_parent_label="Neuroplasticity",
                entity_kind="biomarker_readout",
                domain="molecular_pathway_readout",
                study_doi="10.1000/molecular",
                study_title="A molecular psilocybin study",
            ),
            finding(
                entity_label="Norpsilocin",
                graph_entity_label="Norpsilocin",
                entity_kind="compound",
                domain="pharmacokinetics_exposure",
                study_doi="10.1000/pk",
                study_title="A pharmacokinetic psilocybin study",
            ),
        ],
    )
    write_columnar_payload(detail_paths["meta_analyses"], [])
    write_columnar_payload(
        detail_paths["reviews"],
        [
            finding(
                study_doi="10.1000/review",
                study_title="A review of psilocybin for depression",
                study_year=2024,
            )
        ],
    )

    payload = build_compound_payload(
        "Psilocybin",
        detail_paths,
        release_id="release:test",
        concept_allowlist={
            "conditions": {"major depressive disorder"},
            "molecular_effects": {"neuroplasticity"},
        },
    )
    categories = {category["key"]: category for category in payload["categories"]}
    depression = categories["conditions"]["concepts"][0]

    assert depression["label"] == "Major depressive disorder"
    assert depression["sources"]["primary"]["studies"] == 1
    assert depression["sources"]["primary"]["findings"] == 2
    assert depression["sources"]["reviews"]["studies"] == 1
    assert categories["molecular_effects"]["concepts"][0]["label"] == "Neuroplasticity"
    assert categories["pharmacokinetics"]["concepts"][0]["label"] == "Norpsilocin"


def test_compound_page_is_a_restrained_research_matrix(tmp_path: Path) -> None:
    detail_paths = {
        source: tmp_path / f"{source}.json"
        for source in ("primary", "meta_analyses", "reviews")
    }
    write_columnar_payload(detail_paths["primary"], [finding()])
    write_columnar_payload(detail_paths["meta_analyses"], [])
    write_columnar_payload(detail_paths["reviews"], [])
    payload = build_compound_payload("Psilocybin", detail_paths)
    html = render_compound_page(payload)

    assert html.count("<h1>") == 1
    assert "<h1>Psilocybin</h1>" in html
    assert "Research map" in html
    assert "Counts are unique source papers" in html
    assert 'id="compoundGraph"' in html
    assert 'data-compound-view="map"' in html
    assert 'data-compound-view="table"' in html
    assert 'data-compound-graph-source="primary"' in html
    assert "hero-stats" not in html
    assert 'class="pill"' not in html
    assert 'class="site-button primary"' not in html

    output_dir = write_compound_page(payload, tmp_path / "compounds")
    assert (output_dir / "index.html").is_file()
    assert (output_dir / "data.json").is_file()


def test_compound_graph_is_data_driven_and_keyboard_interactive() -> None:
    source = (ROOT / "ui/compound.js").read_text(encoding="utf-8")
    styles = (ROOT / "ui/styles.css").read_text(encoding="utf-8")

    assert "function renderCompoundGraph()" in source
    assert "function bindGraphNode(" in source
    assert 'event.key !== "Enter" && event.key !== " "' in source
    assert "GRAPH_MAX_CONCEPTS = 12" in source
    assert "setGraphSource(" in source
    assert "stroke-width" in source
    assert ".compound-graph-edge.is-selected" in styles
    assert ".compound-concept-node.is-selected" in styles
    assert '.compound-enhanced[data-compound-view="table"]' in styles
