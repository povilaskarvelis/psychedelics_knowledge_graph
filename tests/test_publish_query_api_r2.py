import json
import tempfile
import unittest
from pathlib import Path

from pipeline.publish.publish_query_api_r2 import (
    ImmutableObjectConflict,
    publish_active_query_release,
)
from services.query_api.config import R2Settings
from tests.query_api_fixtures import build_active_query_release
from tests.r2_fixtures import FakeObjectStore


def r2_settings() -> R2Settings:
    return R2Settings(
        account_id="account",
        bucket="bucket",
        access_key_id="key",
        secret_access_key="secret",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        prefix="query-api",
    )


class PublishQueryApiR2Test(unittest.TestCase):
    def test_publishes_immutable_files_then_switches_active_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, query_runs = build_active_query_release(root)
            store = FakeObjectStore()
            settings = r2_settings()

            result = publish_active_query_release(
                store=store,
                settings=settings,
                active_pointer_path=pointer,
                query_runs_dir=query_runs,
                published_at="2026-07-17T00:00:00+00:00",
            )

            self.assertEqual(result["release_id"], "test_run:r1")
            self.assertEqual(store.operations[-2], ("put_bytes", settings.active_key))
            self.assertEqual(store.operations[-1], ("get_bytes", settings.active_key))
            active = json.loads(store.objects[settings.active_key])
            self.assertIn("database", active["files"])
            self.assertIn("table:papers", active["files"])
            self.assertIn("table:relationships", active["files"])
            self.assertNotIn("table:findings", active["files"])
            self.assertTrue(active["manifest"]["key"].endswith("/manifest.json"))
            self.assertEqual(result["uploaded_count"], len(active["files"]) + 1)

            second = publish_active_query_release(
                store=store,
                settings=settings,
                active_pointer_path=pointer,
                query_runs_dir=query_runs,
                published_at="2026-07-17T01:00:00+00:00",
            )
            self.assertEqual(second["uploaded_count"], 0)
            self.assertEqual(second["existing_count"], result["uploaded_count"])

    def test_local_checksum_failure_does_not_switch_remote_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, query_runs = build_active_query_release(root)
            store = FakeObjectStore()
            settings = r2_settings()
            database = query_runs / "test_run" / "public_api.duckdb"
            database.write_bytes(database.read_bytes() + b"corrupt")

            with self.assertRaisesRegex(ValueError, "size mismatch"):
                publish_active_query_release(
                    store=store,
                    settings=settings,
                    active_pointer_path=pointer,
                    query_runs_dir=query_runs,
                )
            self.assertNotIn(settings.active_key, store.objects)

    def test_remote_release_key_conflict_does_not_switch_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, query_runs = build_active_query_release(root)
            store = FakeObjectStore()
            settings = r2_settings()
            first = publish_active_query_release(
                store=store,
                settings=settings,
                active_pointer_path=pointer,
                query_runs_dir=query_runs,
            )
            previous_active = store.objects[settings.active_key]
            database_key = first["files"]["database"]["key"]
            store.objects[database_key] = b"different"
            store.metadata[database_key] = {"sha256": "0" * 64}

            with self.assertRaises(ImmutableObjectConflict):
                publish_active_query_release(
                    store=store,
                    settings=settings,
                    active_pointer_path=pointer,
                    query_runs_dir=query_runs,
                )
            self.assertEqual(store.objects[settings.active_key], previous_active)


if __name__ == "__main__":
    unittest.main()
