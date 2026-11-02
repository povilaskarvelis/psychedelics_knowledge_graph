"""Every construct the normalizer can admit to the main graph is shown by one overview view.

The saved-endpoint vocabulary of 29 October added 41 constructs, including the
normalizer's own "Psychotomimetic effects", without adding them to a view, so
their findings were in no Explore area. This check fails when the vocabulary
or a code rule gains a construct that no view lists.
"""
import json
from pathlib import Path

from pipeline.kg import build_evidence_tables as b

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "schema" / "graph_view_contract.json").read_text())
VOCABULARY = json.loads((ROOT / "schema" / "kg_node_vocabularies.json").read_text())
LISTS = {view["id"]: set(view.get("object_labels", [])) for view in CONTRACT["views"]}
CONSTRUCT_VIEWS = ("cognitive_behavioral_construct", "behavioral_effect")
# Labels assigned in code rather than by the vocabulary or COGNITIVE_BEHAVIORAL_RULES.
CODE_ASSIGNED_CONSTRUCTS = {"Sexual behavior"}


def admissible_construct_labels() -> set[str]:
    vocabulary = {item["label"] for item in VOCABULARY["node_kinds"]["cognitive_behavioral_construct"]}
    rules = {label for label, _pattern in b.COGNITIVE_BEHAVIORAL_RULES}
    return vocabulary | rules | CODE_ASSIGNED_CONSTRUCTS


def test_each_admissible_construct_is_on_exactly_one_construct_view():
    missing, doubled = [], []
    for label in sorted(admissible_construct_labels()):
        views = [view for view in CONSTRUCT_VIEWS if label in LISTS[view]]
        if not views and label not in b.CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS:
            missing.append(label)
        if len(views) > 1:
            doubled.append(label)
    assert not missing, f"constructs on no view list: {missing}"
    assert not doubled, f"constructs on both view lists: {doubled}"


def test_view_lists_name_only_known_constructs():
    known = admissible_construct_labels()
    for view in CONSTRUCT_VIEWS:
        assert LISTS[view] <= known, f"{view} lists unknown labels: {sorted(LISTS[view] - known)}"


def test_psychotomimetic_boundary_label_is_shown_in_cognition():
    # apply_psychosis_family_boundary routes transient psychotomimetic effects to cognition.
    assert "Psychotomimetic effects" in LISTS["cognitive_behavioral_construct"]
