from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.render_release_metadata import render_site


class HeadMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = values.get("name") or values.get("property")
            content = values.get("content")
            if key and content:
                self.meta[key] = content
        elif tag == "link" and values.get("rel") == "canonical":
            href = values.get("href")
            if href:
                self.canonicals.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def parse_page(path: Path) -> HeadMetadataParser:
    parser = HeadMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def test_indexable_html_pages_have_complete_unique_metadata() -> None:
    pages = {
        "index.html": ("https://psychedelicskg.com/", "Psychedelics Knowledge Graph"),
        "about/index.html": (
            "https://psychedelicskg.com/about/",
            "About | Psychedelics Knowledge Graph",
        ),
        "methods/index.html": (
            "https://psychedelicskg.com/methods/",
            "Methods | Psychedelics Knowledge Graph",
        ),
        "api/index.html": (
            "https://psychedelicskg.com/api/",
            "API | Psychedelics Knowledge Graph",
        ),
        "compounds/psilocybin/index.html": (
            "https://psychedelicskg.com/compounds/psilocybin/",
            "Psilocybin | Psychedelics Knowledge Graph",
        ),
        "feedback/index.html": (
            "https://psychedelicskg.com/feedback/",
            "Leave feedback | Psychedelics Knowledge Graph",
        ),
    }
    titles: set[str] = set()
    descriptions: set[str] = set()

    for relative_path, (canonical_url, expected_title) in pages.items():
        metadata = parse_page(ROOT / relative_path)
        description = metadata.meta["description"]

        assert metadata.title == expected_title
        assert len(metadata.canonicals) == 1
        assert metadata.canonicals[0] == canonical_url
        assert metadata.meta["og:title"] == metadata.title
        assert metadata.meta["og:description"] == description
        assert metadata.meta["og:url"] == canonical_url
        assert metadata.meta["twitter:title"] == metadata.title
        assert metadata.meta["twitter:description"] == description

        titles.add(metadata.title)
        descriptions.add(description)

    assert len(titles) == len(pages)
    assert len(descriptions) == len(pages)


def test_homepage_metadata_matches_landing_page_summary() -> None:
    metadata = parse_page(ROOT / "index.html")
    expected = (
        "A living map of psychedelic research, built to keep scientific knowledge "
        "organized, connected, and easily explorable."
    )

    assert metadata.meta["description"] == expected
    assert metadata.meta["og:description"] == expected
    assert metadata.meta["twitter:description"] == expected


def test_feedback_confirmation_is_not_indexable() -> None:
    metadata = parse_page(ROOT / "feedback/sent/index.html")

    assert metadata.meta["robots"] == "noindex,follow"
    assert metadata.canonicals == []


def test_public_html_pages_use_current_favicon_assets() -> None:
    pages = (
        "index.html",
        "about/index.html",
        "methods/index.html",
        "api/index.html",
        "compounds/psilocybin/index.html",
        "feedback/index.html",
        "feedback/sent/index.html",
        "ui/index.html",
        "ui/methods.html",
    )

    for relative_path in pages:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert 'href="/favicon.ico" sizes="16x16 32x32"' in source
        assert 'href="/favicon-search.png" type="image/png" sizes="192x192"' in source
        assert 'href="/favicon.svg" type="image/svg+xml" sizes="any"' in source
        assert 'href="/apple-touch-icon.png" sizes="180x180"' in source


def test_sitemap_lists_only_public_canonical_urls_with_accurate_lastmods() -> None:
    expected = {
        "https://psychedelicskg.com/": "2026-07-28",
        "https://psychedelicskg.com/about/": "2026-07-28",
        "https://psychedelicskg.com/methods/": "2026-07-28",
        "https://psychedelicskg.com/api/": "2026-07-28",
        "https://psychedelicskg.com/api/agent-guide.md": "2026-07-20",
        "https://psychedelicskg.com/compounds/psilocybin/": "2026-07-28",
        "https://psychedelicskg.com/llms.txt": "2026-07-20",
        "https://psychedelicskg.com/feedback/": "2026-07-28",
    }
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    actual = {
        location: lastmod
        for location, lastmod in re.findall(
            r"<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>\s*</url>",
            sitemap,
        )
    }

    assert actual == expected


def test_robots_points_crawlers_to_the_canonical_sitemap() -> None:
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")

    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Sitemap: https://psychedelicskg.com/sitemap.xml" in robots


def test_release_metadata_renders_site_citation_and_structured_data(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    (site_dir / "about").mkdir(parents=True)
    shutil.copy2(ROOT / "index.html", site_dir / "index.html")
    shutil.copy2(ROOT / "about/index.html", site_dir / "about/index.html")
    render_site(ROOT / "release-metadata.json", site_dir)

    metadata = json.loads((ROOT / "release-metadata.json").read_text(encoding="utf-8"))
    citation_cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    homepage = (site_dir / "index.html").read_text(encoding="utf-8")
    about_page = (site_dir / "about/index.html").read_text(encoding="utf-8")
    pages_with_footers = (
        "index.html",
        "about/index.html",
        "methods/index.html",
        "api/index.html",
        "compounds/psilocybin/index.html",
        "feedback/index.html",
        "feedback/sent/index.html",
    )

    assert 'id="citation"' in about_page
    assert f"Graph version: v{metadata['version']}" in homepage
    assert f"Literature updated: {metadata['literature_updated']}" in homepage
    assert f'"datePublished": "{metadata["release_date"]}"' in homepage
    assert f'"dateModified": "{metadata["literature_updated"]}"' in homepage
    assert f'"version": "{metadata["version"]}"' in homepage
    assert f'"identifier": "https://doi.org/{metadata["doi"]}"' in homepage
    assert f'"sameAs": "https://doi.org/{metadata["concept_doi"]}"' in homepage

    assert (
        f"Version {metadata['version']}; literature updated {metadata['literature_updated']}"
        in about_page
    )
    assert f"https://doi.org/{metadata['doi']}" in about_page
    assert f"@software{{Karvelis{metadata['release_date'][:4]}PKG," in about_page
    assert (
        "title     = {Psychedelics Knowledge Graph "
        f"(Version {metadata['version']}; literature updated {metadata['literature_updated']})}}"
        in about_page
    )
    assert "subtitle  =" not in about_page
    assert "version   =" not in about_page
    assert f"doi       = {{{metadata['doi']}}}" in about_page
    assert "note      =" not in about_page
    assert "Computer software" not in about_page
    assert "Copy BibTeX" in about_page
    assert "View on Zenodo" not in about_page
    assert "Machine-readable citation metadata" not in about_page
    assert about_page.index('id="work-in-progress"') < about_page.index('id="citation"')
    assert "{{RELEASE_" not in homepage
    assert "{{RELEASE_" not in about_page
    assert f'version: "{metadata["version"]}"' in citation_cff
    assert f'doi: "{metadata["doi"]}"' in citation_cff
    assert f"date-released: {metadata['release_date']}" in citation_cff
    assert metadata["literature_updated"] in citation_cff

    for relative_path in pages_with_footers:
        page = (ROOT / relative_path).read_text(encoding="utf-8")
        assert '<a href="/about/#citation">Cite this project</a>' in page


def test_compound_view_is_part_of_the_public_build() -> None:
    build_script = (ROOT / "scripts/build_site.sh").read_text(encoding="utf-8")
    homepage = (ROOT / "index.html").read_text(encoding="utf-8")
    public_files = (ROOT / "scripts/public_site_files.txt").read_text(encoding="utf-8")

    assert (ROOT / "scripts/build_compound_pages.py").exists()
    assert (ROOT / "compounds/psilocybin/index.html").exists()
    assert (ROOT / "compounds/psilocybin/data.json").exists()
    assert "/compounds/psilocybin/" not in homepage
    assert "build_compound_pages.py" not in build_script
    assert "compounds" in public_files.splitlines()
    assert "schema/graph_view_contract.json" in public_files.splitlines()
    assert "ui/compound.js" in public_files.splitlines()


def test_site_build_keeps_the_existing_preview_available_until_ready() -> None:
    build_script = (ROOT / "scripts/build_site.sh").read_text(encoding="utf-8")

    assert 'BUILD_DIR="$(mktemp -d)"' in build_script
    assert 'rsync -a --delete-after "${BUILD_DIR}/" "${DIST_DIR}/"' in build_script
    assert 'rm -rf "${DIST_DIR}"' not in build_script
