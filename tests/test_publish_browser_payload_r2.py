import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.publish.publish_browser_payload_r2 import (
    BROWSER_ACTIVE_SCHEMA_VERSION,
    publish_active_browser_release,
)
from pipeline.publish.publish_query_api_r2 import ImmutableObjectConflict
from tests.r2_fixtures import FakeObjectStore
from tests.test_publish_query_api_r2 import r2_settings


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

    def test_uploads_immutable_release_before_switching_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, runs, methods_views = self.build_release(root)
            store = FakeObjectStore()

            result = publish_active_browser_release(
                store=store,
                settings=r2_settings(),
                active_pointer_path=pointer,
                browser_runs_dir=runs,
                methods_views_dir=methods_views,
                published_at="2026-07-19T00:00:00+00:00",
            )

            self.assertEqual(result["schema_version"], BROWSER_ACTIVE_SCHEMA_VERSION)
            self.assertEqual(result["active_key"], "browser/active.json")
            self.assertEqual(store.operations[-2:], [
                ("put_bytes", "browser/active.json"),
                ("get_bytes", "browser/active.json"),
            ])
            active = json.loads(store.objects["browser/active.json"])
            self.assertTrue(active["active_manifest"].startswith("browser/releases/"))
            self.assertTrue(
                active["active_detail_bootstraps"]["primary"].endswith(
                    "/detail_bootstrap_primary.json"
                )
            )
            self.assertTrue(
                active["methods"]["bibliography"].endswith(
                    "/methods_bibliography.json"
                )
            )
            self.assertEqual(result["uploaded_count"], 13)

            second = publish_active_browser_release(
                store=store,
                settings=r2_settings(),
                active_pointer_path=pointer,
                browser_runs_dir=runs,
                methods_views_dir=methods_views,
            )
            self.assertEqual(second["uploaded_count"], 0)
            self.assertEqual(second["existing_count"], 13)

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
            store = FakeObjectStore()
            first = publish_active_browser_release(
                store=store,
                settings=r2_settings(),
                active_pointer_path=pointer,
                browser_runs_dir=runs,
                methods_views_dir=methods_views,
            )
            previous = store.objects["browser/active.json"]
            detail_key = first["active_detail_bootstraps"]["primary"]
            store.objects[detail_key] = b"different"
            store.metadata[detail_key] = {"sha256": "0" * 64}

            with self.assertRaises(ImmutableObjectConflict):
                publish_active_browser_release(
                    store=store,
                    settings=r2_settings(),
                    active_pointer_path=pointer,
                    browser_runs_dir=runs,
                    methods_views_dir=methods_views,
                )
            self.assertEqual(store.objects["browser/active.json"], previous)


if __name__ == "__main__":
    unittest.main()
