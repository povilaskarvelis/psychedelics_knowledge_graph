from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHODS_JS = ROOT / "ui" / "methods.js"
PUBLIC_SITE_MANIFEST = ROOT / "scripts" / "public_site_files.txt"


def test_methods_page_uses_versioned_r2_release_without_local_fallback() -> None:
    source = METHODS_JS.read_text(encoding="utf-8")

    assert "https://data.psychedelicskg.com/browser/active.json" in source
    assert 'loadMethodsData("pipeline_status")' in source
    assert 'loadMethodsData("bibliography")' in source
    assert "data/kg/views/pipeline_status_graph.json" not in source
    assert "data/kg/views/methods_bibliography.json" not in source
    assert "objectPrefix.startsWith(\"browser/releases/\")" in source
    assert "key.startsWith(`${objectPrefix}/`)" in source


def test_netlify_bundle_contains_no_generated_data_files() -> None:
    public_files = {
        line.split("#", 1)[0].strip()
        for line in PUBLIC_SITE_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }

    assert not any(path.startswith("data/") for path in public_files)
