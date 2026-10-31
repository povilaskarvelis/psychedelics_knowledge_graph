"""Retain typed molecular observations whose names mention several molecules.

A transporter and its substrate, or a ratio's numerator and denominator, do not
make independent outcomes. This fallback runs only after existing matching and
complete-list expansion fail. It never resolves a molecule to a new identity or
distributes a shared result across the molecules named in a readout.
"""
from __future__ import annotations

import re


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _present(value: object) -> bool:
    return _text(value).casefold().replace("_", " ") not in {
        "", "none", "null", "n/a", "na", "unknown", "not reported", "not specified",
    }


MEASUREMENT_RE = re.compile(
    r"\b(?:mrna|transcripts?|protein|expression|levels?|abundance|density|"
    r"immunoreactiv\w*|phosphorylat\w*|release|uptake|efflux|outflow|clearance|"
    r"turnover|ratio|binding|deamination|catabolism|transport|activity|activation|"
    r"internalization|trafficking|formation|hydrolysis|current|epsc|desensitization)\b"
    r"|\b(?:phospho[- ]|p-(?:creb|erk|mtor|p38)\b)", re.I,
)
COMPUTATIONAL_RE = re.compile(
    r"\b(?:computational|in[- ]silico|simulat\w*|molecular docking|qm:mm|oniom)\b", re.I,
)


def molecular_readout_recovery_reason(
    row: dict, raw_label: str, known_categories: tuple[str, ...],
) -> str | None:
    """None: insufficient typed evidence; empty: single measured readout.

    A nonempty reason retains the entire observation in paper detail. A single
    readout still passes the normal subject, provenance and admission gates.
    Category and endpoint must come from the extraction's typed fields, never
    from incidental molecules in the result narrative.
    """
    if _text(row.get("source_item_type")) != "primary_item":
        return None
    marker = _text(row.get("specific_readout_or_marker"))
    category = _text(row.get("molecular_effect_category"))
    if (marker != _text(raw_label) or not _present(marker)
            or category not in known_categories or category == "Other molecular effects"
            or not _present(row.get("assay_or_method"))
            or not _present(row.get("finding_summary"))):
        return None

    method = " ".join(_text(row.get(k)) for k in (
        "experimental_system_category", "system", "assay_or_method", "study_design",
    ))
    if COMPUTATIONAL_RE.search(method):
        return "computed_molecular_readout_detail_only"

    # A phosphosite annotation is part of one modified-protein measurement.
    # Other semicolons, conjunctions and comma lists remain bundled: sharing an
    # assay or a direction does not establish separate marker-level results.
    shape = re.sub(r";\s*(?:Ser|Thr|Tyr)\d+(?=\s*\))", "", marker, flags=re.I)
    # Two kinetic parameters describe the same reaction rate; a total-protein
    # denominator likewise belongs to the normalized phosphoprotein readout.
    shape = re.sub(r";\s*Vmax\s+and\s+Km(?=\s*\))", "", shape, flags=re.I)
    shape = re.sub(r",\s*((?:normalized|relative) to total\b)", r" \1", shape, flags=re.I)
    if re.search(r"[;,]|\b(?:and|or|versus|vs)\b|\s&\s", shape, re.I):
        return "bundled_molecular_readouts_require_resolution"
    # Slash-separated subunits/markers need resolution unless the endpoint
    # explicitly names a ratio or turnover. ERK1/2-style isoform notation is
    # retained literally; it is not projected into two independent findings.
    shape = re.sub(r"(?<=\d)/(?=\d)", "", shape)
    paired_density = re.fullmatch(r"synaptic density\s*\([^();,]+ puncta pairs\)", shape, re.I)
    if "/" in shape and not paired_density and not re.search(r"\b(?:ratio|turnover)\b", shape, re.I):
        return "bundled_molecular_readouts_require_resolution"
    if not MEASUREMENT_RE.search(marker):
        return "molecular_readout_requires_measurement_resolution"
    return ""
