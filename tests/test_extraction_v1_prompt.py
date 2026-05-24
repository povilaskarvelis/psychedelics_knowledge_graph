from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_extraction_prompt_contains_primary_scope_guard() -> None:
    prompt = (ROOT / "docs" / "extraction_v1_prompt.md").read_text(encoding="utf-8")
    prompt_one_line = " ".join(prompt.split())

    assert "## Routing Algorithm" in prompt
    assert "## Scope Guard" in prompt
    assert "The compound itself must be in scope." in prompt
    assert "anesthetic, sedative, assay reagent, or background exposure" in prompt
    assert "Broad psychopharmacology or neuroscience papers" in prompt_one_line


def test_extraction_dataset_addenda_are_separate() -> None:
    mechanistic = (ROOT / "docs" / "extraction_v1_mechanistic_prompt.md").read_text(encoding="utf-8")
    disorder = (ROOT / "docs" / "extraction_v1_disorder_prompt.md").read_text(encoding="utf-8")

    assert "dataset = \"mechanistic\"" in mechanistic
    assert "compound_target" in mechanistic
    assert "compound_disorder" in disorder
    assert "therapeutic or functional interpretation" in disorder


def test_extraction_protocol_contains_scope_guard_examples() -> None:
    protocol = (ROOT / "docs" / "extraction_v1_protocol.md").read_text(encoding="utf-8")
    protocol_one_line = " ".join(protocol.split())

    assert "## Scope Guard" in protocol
    assert "DOI, DOB, and DOM" in protocol
    assert "ketamine, esketamine, arketamine" in protocol
    assert "not automatically in scope" in protocol_one_line
