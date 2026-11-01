import json
import tempfile
import unittest
from pathlib import Path

from pipeline.publish import release_archive as archive
from tests.r2_fixtures import FakeObjectStore, write_built_site


class RelocationTest(unittest.TestCase):
    SITE = "/browser/archive/2026-09-18-abcdef12"

    def test_slug_combines_publication_date_and_release_hash(self) -> None:
        slug = archive.archive_slug("run:public:1", "2026-09-18T23:30:00-02:00")
        self.assertRegex(slug, r"^2026-09-19-[0-9a-f]{8}$")
        self.assertEqual(slug, archive.archive_slug("run:public:1", "2026-09-19T01:30:00+00:00"))

    def test_relocates_archived_pages_and_keeps_live_pages(self) -> None:
        cases = {
            "/": f"{self.SITE}/index.html",
            "/methods/": f"{self.SITE}/methods/index.html",
            "/methods": f"{self.SITE}/methods/index.html",
            "/methods/#release-notes": f"{self.SITE}/methods/index.html#release-notes",
            "/ui/app.js?v=1": f"{self.SITE}/ui/app.js?v=1",
            "/compounds/psilocybin/": f"{self.SITE}/compounds/psilocybin/index.html",
            "../": "../index.html",
            "./": "./index.html",
            "styles.css?v=1": "styles.css?v=1",
            "/about/": "/about/",
            "/feedback/?source=graph": "/feedback/?source=graph",
            "/favicon.ico": "/favicon.ico",
            "https://doi.org/10.1/x": "https://doi.org/10.1/x",
            "#section": "#section",
            "mailto:a@example.org": "mailto:a@example.org",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(archive.relocated_url(value, site_path=self.SITE), expected)
        self.assertEqual(
            archive.relocated_url("../", site_path=self.SITE, url_attribute=False),
            "../",
        )

    def test_snapshot_loads_only_its_own_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            built = write_built_site(root)
            destination = root / "archived"
            files = archive.prepare_site_snapshot(
                built_site=built,
                destination=destination,
                slug="2026-09-18-abcdef12",
                browser_prefix="browser",
                data_origin="https://data.psychedelicskg.com",
                release_id="run:public:1",
                published_at="2026-09-18T20:00:00+00:00",
                paper_total=21735,
            )

            self.assertNotIn("ui/index.html", files)
            self.assertIn("compounds/psilocybin/data.json", files)
            index = (destination / "index.html").read_text(encoding="utf-8")
            pointer_url = "https://data.psychedelicskg.com/browser/archive/2026-09-18-abcdef12/pointer.json"
            self.assertIn(f'href="{pointer_url}"', index)
            self.assertIn('<base href="./ui/" />', index)
            self.assertIn(f'href="{self.SITE}/methods/index.html"', index)
            self.assertIn(f'src="{self.SITE}/ui/site-nav.js?v=1"', index)
            self.assertIn('href="/about/"', index)
            self.assertIn('content="noindex,follow"', index)
            self.assertNotIn('content="index,follow"', index)
            self.assertIn('name="kg-archived-release" content="2026-09-18-abcdef12"', index)
            self.assertIn("Archived release, published September 18, 2026 (21,735 papers)", index)
            self.assertIn('live.release_id !== "run:public:1"', index)

            methods = (destination / "methods" / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'href="{self.SITE}/index.html"', methods)
            self.assertIn('href="../index.html"', methods)
            compound = (destination / "compounds" / "psilocybin" / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'data-compound-data="{self.SITE}/compounds/psilocybin/data.json"', compound)
            self.assertIn('data-label="/not-a-path/"', compound)

            app = (destination / "ui" / "app.js").read_text(encoding="utf-8")
            self.assertIn(f'"{pointer_url}"', app)
            self.assertIn(f'"{self.SITE}/pointer.json"', app)
            self.assertIn(f'new Worker("{self.SITE}/ui/analysis-worker.js?v=1")', app)
            self.assertNotIn("browser/active.json", app)

    def test_snapshot_fails_when_site_code_stops_naming_the_live_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            built = write_built_site(root)
            (built / "ui" / "methods.js").write_text("const PUBLIC = window.pointer;\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no longer names the live data pointer"):
                archive.prepare_site_snapshot(
                    built_site=built,
                    destination=root / "archived",
                    slug="2026-09-18-abcdef12",
                    browser_prefix="browser",
                    data_origin="https://data.psychedelicskg.com",
                    release_id="run:public:1",
                    published_at="2026-09-18T20:00:00+00:00",
                    paper_total=None,
                )

    def test_snapshot_fails_on_unhandled_live_site_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            built = write_built_site(root)
            app = built / "ui" / "app.js"
            app.write_text(app.read_text(encoding="utf-8") + 'const x = `/ui/${name}`;\n', encoding="utf-8")
            snapshot = archive.prepare_site_snapshot(
                built_site=built,
                destination=root / "archived",
                slug="2026-09-18-abcdef12",
                browser_prefix="browser",
                data_origin="https://data.psychedelicskg.com",
                release_id="run:public:1",
                published_at="2026-09-18T20:00:00+00:00",
                paper_total=None,
            )
            self.assertIn("ui/app.js", snapshot)
            (built / "methods" / "index.html").write_text(
                '<html><head></head><body><a href = "/schema/">x</a>'
                '<script src="/ui/methods.js"></script></body></html>',
                encoding="utf-8",
            )
            relocated = archive.relocate_html(
                (built / "methods" / "index.html").read_text(encoding="utf-8"),
                site_path=self.SITE,
                pointer_url="https://example.org/p.json",
                pointer_path=f"{self.SITE}/pointer.json",
            )[0]
            self.assertIn(f'href = "{self.SITE}/schema/index.html"', relocated)


class RetentionTest(unittest.TestCase):
    def entry(self, release_id: str, evidence: str, published_at: str) -> dict:
        return {
            "release_id": release_id,
            "evidence_release_id": evidence,
            "run_id": evidence.split(":")[0],
            "published_at": published_at,
            "object_prefix": f"browser/releases/{release_id}",
            "slug": f"2026-01-0{published_at[9]}-0000000{published_at[9]}",
        }

    def test_keeps_live_previous_and_last_release_of_each_evidence_release(self) -> None:
        entries = [
            self.entry("a:public:1", "a:ev", "2026-01-01T00:00:00+00:00"),
            self.entry("a:public:2", "a:ev", "2026-01-02T00:00:00+00:00"),
            self.entry("b:public:1", "b:ev", "2026-01-03T00:00:00+00:00"),
            self.entry("b:public:2", "b:ev", "2026-01-04T00:00:00+00:00"),
            self.entry("c:public:1", "c:ev", "2026-01-05T00:00:00+00:00"),
        ]

        plan = archive.plan_archive_retention(entries, "c:public:1")

        self.assertEqual(plan.previous["release_id"], "b:public:2")
        self.assertEqual(
            [entry["release_id"] for entry in plan.kept],
            ["c:public:1", "b:public:2", "a:public:2"],
        )
        self.assertEqual(
            [entry["release_id"] for entry in plan.dropped],
            ["b:public:1", "a:public:1"],
        )

    def test_refresh_keeps_the_release_it_replaced_as_previous(self) -> None:
        entries = [
            self.entry("a:public:1", "a:ev", "2026-01-01T00:00:00+00:00"),
            self.entry("a:public:2", "a:ev", "2026-01-02T00:00:00+00:00"),
        ]

        plan = archive.plan_archive_retention(entries, "a:public:2")

        self.assertEqual(plan.previous["release_id"], "a:public:1")
        self.assertEqual(plan.dropped, ())

    def test_key_helpers(self) -> None:
        self.assertEqual(
            archive.release_prefix_of_key("browser/releases/run-1/rel-2/file.json", "browser/releases/"),
            "browser/releases/run-1/rel-2",
        )
        self.assertEqual(
            archive.archive_slug_of_key("browser/archive/2026-01-01-00000001/ui/app.js", "browser"),
            "2026-01-01-00000001",
        )
        self.assertEqual(archive.archive_slug_of_key("browser/archive/index.json", "browser"), "")


class ArchiveStoreTest(unittest.TestCase):
    def test_index_round_trip_sorts_newest_first(self) -> None:
        store = FakeObjectStore()
        self.assertEqual(archive.read_archive_index(store, "browser")["releases"], [])
        archive.write_archive_index(
            store,
            "browser",
            entries=[
                {"release_id": "old", "published_at": "2026-01-01T00:00:00+00:00"},
                {"release_id": "new", "published_at": "2026-02-01T00:00:00+00:00"},
            ],
            current_release_id="new",
        )
        index = archive.read_archive_index(store, "browser")
        self.assertEqual([entry["release_id"] for entry in index["releases"]], ["new", "old"])
        self.assertEqual(
            store.metadata["browser/archive/index.json"]["cache_control"],
            archive.INDEX_CACHE_CONTROL,
        )

    def test_frozen_pointer_cannot_change(self) -> None:
        store = FakeObjectStore()
        key = "browser/archive/2026-01-01-00000001/pointer.json"
        self.assertEqual(archive.write_archive_pointer(store, key, b"{}\n"), "uploaded")
        self.assertEqual(archive.write_archive_pointer(store, key, b"{}\n"), "existing")
        with self.assertRaises(archive.ArchiveConflict):
            archive.write_archive_pointer(store, key, b'{"x": 1}\n')

    def test_live_release_counts_as_archived_from_pointer_or_index(self) -> None:
        index = {"releases": [{"release_id": "b", "site_entry_key": "browser/archive/x/index.html"}]}
        self.assertTrue(archive.live_release_is_archived({"release_id": "a", "archive": {"site_entry_key": "k"}}, index))
        self.assertTrue(archive.live_release_is_archived({"release_id": "b"}, index))
        self.assertFalse(archive.live_release_is_archived({"release_id": "c"}, index))

    def test_entry_from_pointer_reads_archive_metadata(self) -> None:
        entry = archive.entry_from_pointer(
            {
                "release_id": "r",
                "evidence_release_id": "e",
                "run_id": "run",
                "published_at": "2026-01-01T00:00:00+00:00",
                "object_prefix": "browser/releases/run/r",
                "archive": {"slug": "2026-01-01-00000001", "paper_counts": {"total": 5}},
            }
        )
        self.assertEqual(entry["slug"], "2026-01-01-00000001")
        self.assertEqual(entry["paper_counts"], {"total": 5})
        self.assertIsNone(entry["finding_count"])
        self.assertEqual(json.loads(json.dumps(entry))["site_entry_key"], "")


if __name__ == "__main__":
    unittest.main()
