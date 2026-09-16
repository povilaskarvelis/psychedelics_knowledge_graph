import pandas as pd
import pytest

from pipeline.validate.carry_forward_research_area_reviews import IDENTITY_FIELDS, carry_forward


def inputs():
    row = {field: field for field in IDENTITY_FIELDS}
    row.update(finding_id="old", research_area_adjudication_status="corrected",
               research_area_classification_origin="agent_reviewed",
               graph_admission_status="paper_detail", graph_admission_reason="reviewed_hold")
    baseline = pd.DataFrame([row])
    candidate = pd.DataFrame([dict(row, research_area_adjudication_status="",
                                  research_area_classification_origin="deterministic",
                                  graph_admission_status="main_graph"),
                              dict(row, finding_id="new", study_doi="new-doi")])
    edges = pd.DataFrame([dict(finding_id=fid, projection_type="direct", entity_id="e",
                               compound_id="c", graph_admission_status="main_graph",
                               graph_admission_reason="") for fid in ("old", "new")])
    return baseline, candidate, edges.iloc[:0].copy(), edges


def test_preserves_hold_and_new_evidence():
    findings, edges, report = carry_forward(*inputs())
    assert list(edges.finding_id) == ["new"]
    assert findings.iloc[0].graph_admission_reason == "reviewed_hold"
    assert findings.iloc[0].research_area_classification_origin == "agent_reviewed"
    assert report["previously_held_edges_removed_from_rebuild"] == 1


@pytest.mark.parametrize("field", ["research_area_evidence_fingerprint", "entity_label", "domain"])
def test_changed_evidence_or_projection_rejected(field):
    b, c, be, ce = inputs()
    c.loc[0, field] = "changed"
    with pytest.raises(ValueError, match="changed"):
        carry_forward(b, c, be, ce)


def test_missing_reviewed_finding_rejected():
    b, c, be, ce = inputs()
    with pytest.raises(ValueError, match="Missing"):
        carry_forward(b, c.iloc[1:], be, ce)


def test_missing_previously_admitted_edge_rejected():
    b, c, be, ce = inputs()
    with pytest.raises(ValueError, match="projection is missing"):
        carry_forward(b, c, ce.iloc[:1], ce.iloc[1:])


def test_confirmed_edge_preserved():
    b, c, be, ce = inputs()
    b.loc[0, "graph_admission_status"] = "main_graph"
    _, edges, report = carry_forward(b, c, ce.iloc[:1], ce)
    assert list(edges.finding_id) == ["old", "new"]
    assert report["reviewed_edge_projections_preserved"] == 1
