from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


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
        "index.html": "https://psychedelicskg.com/",
        "about/index.html": "https://psychedelicskg.com/about/",
        "methods/index.html": "https://psychedelicskg.com/methods/",
        "api/index.html": "https://psychedelicskg.com/api/",
        "feedback/index.html": "https://psychedelicskg.com/feedback/",
    }
    titles: set[str] = set()
    descriptions: set[str] = set()

    for relative_path, canonical_url in pages.items():
        metadata = parse_page(ROOT / relative_path)
        description = metadata.meta["description"]

        assert metadata.title
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


def test_feedback_confirmation_is_not_indexable() -> None:
    metadata = parse_page(ROOT / "feedback/sent/index.html")

    assert metadata.meta["robots"] == "noindex,follow"
    assert metadata.canonicals == []


def test_sitemap_lists_only_public_canonical_urls_with_accurate_lastmods() -> None:
    expected = {
        "https://psychedelicskg.com/": "2026-07-28",
        "https://psychedelicskg.com/about/": "2026-07-28",
        "https://psychedelicskg.com/methods/": "2026-07-28",
        "https://psychedelicskg.com/api/": "2026-07-28",
        "https://psychedelicskg.com/api/agent-guide.md": "2026-07-20",
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


def test_discovery_prototype_is_not_part_of_the_public_build() -> None:
    build_script = (ROOT / "scripts/build_site.sh").read_text(encoding="utf-8")
    homepage = (ROOT / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "ui/styles.css").read_text(encoding="utf-8")

    assert not (ROOT / "scripts/build_discovery_pages.py").exists()
    assert "/compounds/psilocybin/" not in homepage
    assert "build_discovery_pages.py" not in build_script
    assert "Psilocybin research brief" not in styles
