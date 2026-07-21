from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHODS_JS = ROOT / "ui" / "methods.js"
PUBLIC_SITE_MANIFEST = ROOT / "scripts" / "public_site_files.txt"
SITE_NAV_JS = ROOT / "ui" / "site-nav.js"


def test_methods_page_uses_versioned_r2_release_by_default() -> None:
    source = METHODS_JS.read_text(encoding="utf-8")

    assert "https://data.psychedelicskg.com/browser/active.json" in source
    assert 'PUBLIC_PREVIEW_POINTER_URL = "/__preview__/published.json"' in source
    assert 'loadMethodsData("pipeline_status")' in source
    assert 'loadMethodsData("bibliography")' in source
    assert "objectPrefix.startsWith(\"browser/releases/\")" in source
    assert "key.startsWith(`${objectPrefix}/`)" in source


def test_methods_local_data_requires_explicit_local_preview_mode() -> None:
    source = METHODS_JS.read_text(encoding="utf-8")

    assert 'LOCAL_DATA_POINTER_URL = "/__preview__/active.json"' in source
    assert 'LOCAL_DATA_SOURCE_QUERY_PARAMETER = "data-source"' in source
    assert "LOCAL_DATA_HOSTS.has(window.location.hostname)" in source
    assert '=== "local"' in source
    assert 'key.startsWith("data/kg/views/")' in source


def test_netlify_bundle_contains_no_generated_data_files() -> None:
    public_files = {
        line.split("#", 1)[0].strip()
        for line in PUBLIC_SITE_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }

    assert not any(path.startswith("data/") for path in public_files)


def test_local_data_mode_is_preserved_across_internal_navigation() -> None:
    source = SITE_NAV_JS.read_text(encoding="utf-8")

    assert 'query.get("data-source") === "local"' in source
    assert 'url.searchParams.set("data-source", "local")' in source
    assert "url.origin !== window.location.origin" in source
