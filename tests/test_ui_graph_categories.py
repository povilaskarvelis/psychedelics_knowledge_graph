from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"


def test_real_world_use_contains_exposure_contexts_without_a_separate_graph_view() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert 'key: "public_health_measure",\n    kinds: ["public_health_measure", "exposure_context"]' in source
    assert 'label: "Use contexts"' not in source
