"""Readout identity must not distribute one observation across named molecules."""
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.molecular_readout_identity import molecular_readout_recovery_reason


def typed_row(marker, **fields):
    return {
        "domain": "molecular_pathway_readout", "source_item_type": "primary_item",
        "source_type": "primary", "specific_readout_or_marker": marker,
        "molecular_effect_category": "Neurotransmitter release, uptake & turnover",
        "assay_or_method": "Radiolabeled substrate uptake assay",
        "finding_summary": "No change in the measured endpoint versus vehicle.",
        **fields,
    }


def reason(row):
    return molecular_readout_recovery_reason(
        row, row["specific_readout_or_marker"], b.MOLECULAR_EFFECT_RULE_LABELS,
    )


@pytest.mark.parametrize("marker", [
    "SERT-mediated [3H]5-HT release", "[3H]dopamine uptake via DAT",
    "[DOPAC + HVA]/[dopamine] dopamine-turnover ratio",
    "NMDA receptor NR1 subunit mRNA", "NR2A (NMDAR subunit) membrane protein level",
    "Phosphorylated CREB (pCREB; Ser133) immunoreactivity",
    "Synaptic density (synapsin-1/PSD-95 puncta pairs)",
    "MAO-A-mediated deamination rate (hydrogen peroxide generation; Vmax and Km)",
    "phosphorylated μ-opioid receptor Ser375, normalized to total receptor",
])
def test_single_measurement_keeps_all_molecular_roles(marker):
    row = typed_row(marker)
    original = dict(row)
    assert reason(row) == ""
    assert row == original
    # Significance, direction and incidental molecules do not change identity.
    assert reason({**row, "finding_summary": "Uptake increased; BDNF and mTOR did not change."}) == ""


@pytest.mark.parametrize("marker", [
    "IL-6, TNF-α, and BDNF mRNA",
    "NR1 (NMDA receptor subunit) mRNA and protein expression",
    "Dopamine turnover (HVA/DA ratio) and asymmetric spine synapse number",
    "p-CREB protein; dopamine release", "D1/D2 receptor expression",
    "Dopamine neurotoxicity (dopamine, DOPAC, and dopamine transporter density)",
    "Beta-arrestin-2 recruitment to the mu opioid receptor; mu opioid receptor internalization",
    "Unknown marker/CREB protein expression",
])
def test_panels_are_retained_as_one_detail_finding(marker):
    assert reason(typed_row(marker)) == "bundled_molecular_readouts_require_resolution"


@pytest.mark.parametrize("fields", [
    {"assay_or_method": "not_reported"}, {"finding_summary": "not_reported"},
    {"molecular_effect_category": "unknown"},
    {"molecular_effect_category": "Other molecular effects"},
    {"source_item_type": "review_relationship"},
])
def test_missing_typed_evidence_does_not_get_inferred_from_prose(fields):
    assert reason(typed_row("SERT-mediated 5-HT release", **fields)) is None


def test_raw_label_must_be_the_typed_marker_and_computations_stay_detail():
    row = typed_row("MAO-A-mediated DMT oxidation; activation barrier",
                    assay_or_method="In silico QM:MM calculations")
    assert reason(row) == "computed_molecular_readout_detail_only"
    assert molecular_readout_recovery_reason(row, "DMT", b.MOLECULAR_EFFECT_RULE_LABELS) is None
    assert reason(typed_row("BDNF-TrkB pathway")) == "molecular_readout_requires_measurement_resolution"


def test_saved_observations_keep_values_parent_subject_and_scope(tmp_path):
    path = Path(__file__).parent / "fixtures/molecular_readout_saved_rows.json"
    source = json.loads(path.read_text())
    originals = {(r.get("task_id"), str(r["source_item_index"])): r for r in source}
    b.build_tables(out_dir=tmp_path, write_duckdb=False, graph_sources={
        "routed_extractions": {"path": path, "domain": "routed", "dataset": "routed",
                               "default_evidence_type": "primary_evidence", "skip_audit": True},
    })
    findings = pd.read_parquet(tmp_path / "findings.parquet").fillna("")
    assert pd.read_parquet(tmp_path / "normalization_audit.parquet").empty
    assert len(findings) == len(source) == 12
    assert findings.finding_id.is_unique
    assert set(findings.entity_match_type) == {"explicit_molecular_readout_preserved"}
    for finding in findings.to_dict("records"):
        raw = json.loads(finding["raw_row_json"])
        original = originals[(raw.get("task_id"), str(raw["source_item_index"]))]
        for field in ["specific_readout_or_marker", "pathway_or_readout", "assay_or_method",
                      "molecular_effect_category", "quantitative_value", "effect_or_statistic",
                      "unit", "finding_summary", "support", "evidence_location", "evidence_locator",
                      "model_system", "species_or_cell_line", "dose_or_exposure", "assessment_timepoint"]:
            assert raw.get(field, "") == original.get(field, ""), field
        assert finding["graph_parent_label"] == original["molecular_effect_category"]
        assert not raw.get("entity_split_source_label")
    by_doi = findings.set_index("study_doi")
    for doi in ["10.1007/s10571-009-9426-y", "10.1016/j.cub.2020.07.008",
                "10.1111/j.1476-5381.1993.tb13520.x", "10.1016/j.toxlet.2015.12.001",
                "10.3390/biomedicines13040787", "10.1111/bph.16466"]:
        assert by_doi.loc[doi, "graph_admission_status"] == "main_graph"
    for doi in ["10.1002/dta.2197", "10.1021/acsptsci.0c00102", "10.1186/s12871-018-0511-y"]:
        assert by_doi.loc[doi, "graph_admission_reason"] == "bundled_molecular_readouts_require_resolution"
    assert by_doi.loc["10.1039/d0ob01118e", "graph_admission_reason"] == "computed_molecular_readout_detail_only"
    assert by_doi.loc["10.1007/s00213-018-5075-5", "graph_admission_reason"] == "uncontrolled_subject_detail_only"
    # A null kinetic comparison remains usable evidence with its original units.
    null = json.loads(by_doi.loc["10.1111/bph.16466", "raw_row_json"])
    assert "No overt differences" in null["effect_or_statistic"]
