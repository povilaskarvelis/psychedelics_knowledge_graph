import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.kg.graph_view_contract import graph_view_ids
from pipeline.publish.publish_browser_payload_r2 import (
    BROWSER_ACTIVE_SCHEMA_VERSION,
    UnarchivedLiveRelease,
    publish_active_browser_release,
)
from pipeline.publish.publish_query_api_r2 import ImmutableObjectConflict
from tests.r2_fixtures import FakeObjectStore, write_built_site
from tests.test_publish_query_api_r2 import r2_settings

DETAIL_VIEW_KEYS = graph_view_ids()


class PublishBrowserPayloadR2Test(unittest.TestCase):
    def build_release(self, root: Path) -> tuple[Path, Path, Path]:
        runs = root / "data" / "processed" / "graph_payload_runs"
        release = runs / "test_run"
        release.mkdir(parents=True)
        files = {}
        pointer_maps = {
            "active_graph_bootstraps": {},
            "active_dashboard_bootstraps": {},
            "active_detail_bootstraps": {},
            "active_detail_bootstraps_by_view": {},
        }
        for prefix, pointer_key in (
            ("graph", "active_graph_bootstraps"),
            ("dashboard", "active_dashboard_bootstraps"),
            ("detail", "active_detail_bootstraps"),
        ):
            for source_key in ("primary", "meta_analyses", "reviews"):
                path = release / f"{prefix}_bootstrap_{source_key}.json"
                path.write_text(
                    json.dumps({"kind": prefix, "source": source_key}),
                    encoding="utf-8",
                )
                relative = path.relative_to(root).as_posix()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                files[f"{prefix}:{source_key}"] = {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
                pointer_maps[pointer_key][source_key] = relative
        for source_key in ("primary", "meta_analyses", "reviews"):
            pointer_maps["active_detail_bootstraps_by_view"][source_key] = {}
            for view_key in DETAIL_VIEW_KEYS:
                path = release / f"detail_bootstrap_{source_key}_{view_key}.json"
                path.write_text(
                    json.dumps(
                        {"kind": "detail_view", "source": source_key, "view": view_key}
                    ),
                    encoding="utf-8",
                )
                relative = path.relative_to(root).as_posix()
                files[f"detail_view:{source_key}:{view_key}"] = {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                pointer_maps["active_detail_bootstraps_by_view"][source_key][view_key] = relative

        manifest = {
            "schema_version": "route_native_evidence_manifest_v1",
            "release_id": "test_run:public:r1",
            "evidence_release_id": "test_run:evidence:r1",
            "files": files,
            "summary_stats": {},
        }
        manifest_path = release / "graph_payload_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        pointer = {
            "schema_version": "route_native_evidence_payload_active_v1",
            "run_id": "test_run",
            "release_id": "test_run:evidence:r1",
            "public_release_id": "test_run:public:r1",
            "active_manifest": manifest_path.relative_to(root).as_posix(),
            **pointer_maps,
        }
        pointer_path = root / "data" / "processed" / "graph_payload_active.json"
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
        methods_views = root / "data" / "kg" / "views"
        methods_views.mkdir(parents=True)
        for filename in (
            "pipeline_status_graph.json",
            "methods_bibliography.json",
            "graph_inclusion_dispositions.json",
        ):
            (methods_views / filename).write_text(
                json.dumps(
                    {
                        "view": filename.removesuffix(".json"),
                        "run_id": "test_run",
                        "release_id": "test_run:evidence:r1",
                    }
                ),
                encoding="utf-8",
            )
        return pointer_path, runs, methods_views

    def publish(self, store, pointer, runs, methods_views, site, **options):
        return publish_active_browser_release(
            store=store,
            settings=r2_settings(),
            active_pointer_path=pointer,
            browser_runs_dir=runs,
            methods_views_dir=methods_views,
            site_source_root=None,
            site_build_dir=site,
            **options,
        )

    def switch_public_release(self, pointer: Path, runs: Path, release_id: str) -> None:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        payload["public_release_id"] = release_id
        pointer.write_text(json.dumps(payload), encoding="utf-8")
        manifest_path = runs / "test_run" / "graph_payload_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["release_id"] = release_id
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_uploads_immutable_release_before_switching_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            site = write_built_site(root)
            store = FakeObjectStore()

            result = self.publish(
                store, pointer, runs, methods_views, site,
                published_at="2026-07-19T00:00:00+00:00",
            )

            self.assertEqual(result["schema_version"], BROWSER_ACTIVE_SCHEMA_VERSION)
            self.assertEqual(result["active_key"], "browser/active.json")
            written = [key for operation, key in store.operations if operation in {"put_bytes", "upload_file"}]
            pointer_key = result["archive"]["pointer_key"]
            self.assertTrue(pointer_key.startswith("browser/archive/2026-07-19-"))
            self.assertLess(written.index(pointer_key), written.index("browser/active.json"))
            self.assertLess(
                written.index(result["archive"]["site_entry_key"]),
                written.index("browser/active.json"),
            )
            self.assertEqual(written[-1], "browser/archive/index.json")
            self.assertEqual(store.objects[pointer_key], store.objects["browser/active.json"])
            index = json.loads(store.objects["browser/archive/index.json"])
            self.assertEqual(index["current_release_id"], "test_run:public:r1")
            self.assertEqual([entry["release_id"] for entry in index["releases"]], ["test_run:public:r1"])
            active = json.loads(store.objects["browser/active.json"])
            self.assertTrue(active["active_manifest"].startswith("browser/releases/"))
            self.assertTrue(
                active["active_detail_bootstraps"]["primary"].endswith(
                    "/detail_bootstrap_primary.json"
                )
            )
            self.assertTrue(
                active["active_detail_bootstraps_by_view"]["primary"]["brain_system"].endswith(
                    "/detail_bootstrap_primary_brain_system.json"
                )
            )
            self.assertTrue(
                active["methods"]["bibliography"].endswith(
                    "/methods_bibliography.json"
                )
            )
            self.assertEqual(set(active["active_analysis_bootstraps"]), {"primary", "meta_analyses", "reviews"})
            self.assertIn("analysis_index_", active["active_analysis_index"])
            self.assertEqual(result["uploaded_count"], 47)

            first_pointer = store.objects["browser/active.json"]
            second = self.publish(store, pointer, runs, methods_views, site)
            self.assertEqual(second["uploaded_count"], 0)
            self.assertEqual(second["existing_count"], 47)
            self.assertEqual(second["archive_result"]["site_upload"]["uploaded"], 0)
            self.assertEqual(store.objects["browser/active.json"], first_pointer)

    def test_new_release_keeps_the_replaced_release_in_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            site = write_built_site(root)
            store = FakeObjectStore()
            first = self.publish(
                store, pointer, runs, methods_views, site,
                published_at="2026-07-19T00:00:00+00:00",
            )
            self.switch_public_release(pointer, runs, "test_run:public:r2")

            second = self.publish(
                store, pointer, runs, methods_views, site,
                published_at="2026-08-19T00:00:00+00:00",
            )

            index = json.loads(store.objects["browser/archive/index.json"])
            self.assertEqual(index["current_release_id"], "test_run:public:r2")
            self.assertEqual(
                [entry["release_id"] for entry in index["releases"]],
                ["test_run:public:r2", "test_run:public:r1"],
            )
            self.assertIn(first["archive"]["site_entry_key"], store.objects)
            self.assertNotEqual(first["archive"]["slug"], second["archive"]["slug"])

    def test_unarchived_live_release_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            site = write_built_site(root)
            store = FakeObjectStore()
            legacy = {
                "release_id": "legacy:public:1",
                "evidence_release_id": "legacy:evidence",
                "run_id": "legacy",
                "published_at": "2026-06-01T00:00:00+00:00",
                "object_prefix": "browser/releases/legacy/public",
            }
            store.objects["browser/active.json"] = json.dumps(legacy).encode()

            with self.assertRaises(UnarchivedLiveRelease):
                self.publish(store, pointer, runs, methods_views, site)
            self.assertEqual(json.loads(store.objects["browser/active.json"]), legacy)
            self.assertFalse(any(key.startswith("browser/releases/") for key in store.objects))

            self.publish(store, pointer, runs, methods_views, site, allow_unarchived_outgoing=True)
            index = json.loads(store.objects["browser/archive/index.json"])
            legacy_entry = [entry for entry in index["releases"] if entry["release_id"] == "legacy:public:1"]
            self.assertEqual(len(legacy_entry), 1)
            self.assertEqual(legacy_entry[0]["site_entry_key"], "")

    def test_checksum_failure_does_not_switch_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            detail = runs / "test_run" / "detail_bootstrap_primary.json"
            detail.write_text("corrupt", encoding="utf-8")
            store = FakeObjectStore()

            with self.assertRaisesRegex(ValueError, "size mismatch"):
                publish_active_browser_release(
                    store=store,
                    settings=r2_settings(),
                    active_pointer_path=pointer,
                    browser_runs_dir=runs,
                    methods_views_dir=methods_views,
                )
            self.assertNotIn("browser/active.json", store.objects)

    def test_missing_methods_data_does_not_switch_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            (methods_views / "methods_bibliography.json").unlink()
            store = FakeObjectStore()

            with self.assertRaisesRegex(FileNotFoundError, "Methods data file"):
                publish_active_browser_release(
                    store=store,
                    settings=r2_settings(),
                    active_pointer_path=pointer,
                    browser_runs_dir=runs,
                    methods_views_dir=methods_views,
                )
            self.assertNotIn("browser/active.json", store.objects)

    def test_stale_methods_release_does_not_switch_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            bibliography = methods_views / "methods_bibliography.json"
            payload = json.loads(bibliography.read_text(encoding="utf-8"))
            payload["release_id"] = "older:evidence:release"
            bibliography.write_text(json.dumps(payload), encoding="utf-8")
            store = FakeObjectStore()

            with self.assertRaisesRegex(ValueError, "Methods data release ID mismatch"):
                publish_active_browser_release(
                    store=store,
                    settings=r2_settings(),
                    active_pointer_path=pointer,
                    browser_runs_dir=runs,
                    methods_views_dir=methods_views,
                )
            self.assertNotIn("browser/active.json", store.objects)

    def test_conflicting_immutable_object_preserves_previous_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            site = write_built_site(root)
            store = FakeObjectStore()
            first = self.publish(store, pointer, runs, methods_views, site)
            previous = store.objects["browser/active.json"]
            detail_key = first["active_detail_bootstraps"]["primary"]
            store.objects[detail_key] = b"different"
            store.metadata[detail_key] = {"sha256": "0" * 64}

            with self.assertRaises(ImmutableObjectConflict):
                self.publish(store, pointer, runs, methods_views, site)
            self.assertEqual(store.objects["browser/active.json"], previous)


if __name__ == "__main__":
    unittest.main()
