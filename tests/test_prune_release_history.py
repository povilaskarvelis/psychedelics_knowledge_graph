import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline.publish import prune_release_history as pruning
from services.query_api.config import R2Settings
from tests.r2_fixtures import FakeObjectStore


class FakeR2Client:
    def __init__(self, store: FakeObjectStore) -> None:
        self.store = store

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        del Bucket, ContinuationToken
        return {
            "Contents": [
                {"Key": key, "Size": len(value)}
                for key, value in sorted(self.store.objects.items())
                if key.startswith(Prefix)
            ],
            "IsTruncated": False,
        }

    def delete_objects(self, *, Bucket, Delete):
        del Bucket
        deleted = []
        for entry in Delete["Objects"]:
            key = entry["Key"]
            self.store.objects.pop(key, None)
            self.store.metadata.pop(key, None)
            deleted.append({"Key": key})
        return {"Deleted": deleted}


def settings(prefix: str) -> R2Settings:
    return R2Settings(
        account_id="account",
        bucket="bucket",
        access_key_id="key",
        secret_access_key="secret",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        prefix=prefix,
    )


class PruneReleaseHistoryTest(unittest.TestCase):
    def test_remote_prune_keeps_only_the_active_release(self) -> None:
        store = FakeObjectStore()
        store.client = FakeR2Client(store)
        active_prefix = "browser/releases/current/release"
        current_key = f"{active_prefix}/manifest.json"
        old_key = "browser/releases/old/release/manifest.json"
        active = {
            "run_id": "current",
            "release_id": "current:public",
            "evidence_release_id": "current:evidence",
            "object_prefix": active_prefix,
            "active_manifest": current_key,
        }
        active_bytes = json.dumps(active).encode()
        store.objects["browser/active.json"] = active_bytes
        store.objects[current_key] = b"current"
        store.objects[old_key] = b"old"
        for key, value in store.objects.items():
            store.metadata[key] = {"sha256": hashlib.sha256(value).hexdigest()}

        result, pointer = pruning.prune_remote_release_history(
            label="browser_r2",
            store=store,
            settings=settings("browser"),
            active_key="browser/active.json",
            releases_prefix="browser/releases/",
            execute=True,
        )

        self.assertEqual(pointer["run_id"], "current")
        self.assertEqual(result.removed_count, 1)
        self.assertNotIn(old_key, store.objects)
        self.assertIn(current_key, store.objects)
        self.assertEqual(store.objects["browser/active.json"], active_bytes)

    def test_remote_pair_must_identify_the_same_release(self) -> None:
        browser = {
            "run_id": "current",
            "release_id": "current:public",
            "evidence_release_id": "current:evidence",
        }
        query = dict(browser, release_id="older:public")

        with self.assertRaisesRegex(ValueError, "do not identify the same release"):
            pruning.require_matching_remote_releases(browser, query)

    def test_local_prune_refuses_cross_run_extraction_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            graph_pointer = root / "graph_active.json"
            extraction_pointer = root / "extraction_active.json"
            graph_pointer.write_text(
                json.dumps(
                    {
                        "run_id": "current",
                        "release_id": "current:evidence",
                        "active_manifest": (
                            "data/processed/graph_payload_runs/current/"
                            "graph_payload_manifest.json"
                        ),
                        "kg_dir": "data/processed/kg_routed_runs/current",
                    }
                ),
                encoding="utf-8",
            )
            extraction_pointer.write_text(
                json.dumps(
                    {
                        "run_id": "current",
                        "release_id": "current:evidence",
                        "outputs_jsonl": (
                            "data/processed/extraction/routed_runs/older/"
                            "route_extraction_outputs.jsonl"
                        ),
                        "evidence_rows_json": (
                            "data/processed/extraction/routed_runs/older/"
                            "routed_evidence_rows.json"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            roots = {
                "graph": root / "data/processed/graph_payload_runs",
                "kg": root / "data/processed/kg_routed_runs",
                "query_api": root / "data/processed/query_api_runs",
                "extraction": root / "data/processed/extraction/routed_runs",
            }
            (roots["graph"] / "current").mkdir(parents=True)
            (roots["graph"] / "current/graph_payload_manifest.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (roots["kg"] / "current").mkdir(parents=True)
            (roots["query_api"] / "current").mkdir(parents=True)
            (roots["query_api"] / "current/manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "current",
                        "release_id": "current:evidence",
                        "evidence_release_id": "current:evidence",
                    }
                ),
                encoding="utf-8",
            )
            (roots["extraction"] / "older").mkdir(parents=True)
            (roots["extraction"] / "older/route_extraction_outputs.jsonl").touch()
            (roots["extraction"] / "older/routed_evidence_rows.json").touch()

            with mock.patch.object(pruning, "ROOT", root), mock.patch.object(
                pruning,
                "ACTIVE_GRAPH_POINTER",
                graph_pointer,
            ), mock.patch.object(
                pruning,
                "ACTIVE_EXTRACTION_POINTER",
                extraction_pointer,
            ), mock.patch.object(
                pruning,
                "LOCAL_RELEASE_ROOTS",
                roots,
            ):
                with self.assertRaisesRegex(ValueError, "not self-contained"):
                    pruning.validate_local_active_release()


if __name__ == "__main__":
    unittest.main()
