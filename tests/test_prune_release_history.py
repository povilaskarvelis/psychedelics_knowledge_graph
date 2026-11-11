import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline.publish import prune_release_history as pruning
from pipeline.publish import release_archive as archive
from pipeline.publish.release_history import append_release_history
from services.query_api.config import R2Settings
from tests.r2_fixtures import FakeObjectStore


DAY = 86400.0


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


def fake_store() -> FakeObjectStore:
    store = FakeObjectStore()
    store.client = FakeR2Client(store)
    return store


def put(store: FakeObjectStore, key: str, value: bytes) -> None:
    store.objects[key] = value
    store.metadata[key] = {"sha256": hashlib.sha256(value).hexdigest()}


def release_entry(name: str, evidence: str, day: int) -> dict:
    return {
        "release_id": f"{name}:public",
        "evidence_release_id": evidence,
        "run_id": name,
        "published_at": f"2026-01-{day:02d}T00:00:00+00:00",
        "object_prefix": f"browser/releases/{name}/public",
        "slug": f"2026-01-{day:02d}-0000000{day}",
    }


class RemotePruneTest(unittest.TestCase):
    def test_remote_prune_keeps_the_active_and_listed_releases(self) -> None:
        store = fake_store()
        active_prefix = "browser/releases/current/release"
        active = {
            "run_id": "current",
            "release_id": "current:public",
            "evidence_release_id": "current:evidence",
            "object_prefix": active_prefix,
            "active_manifest": f"{active_prefix}/manifest.json",
        }
        active_bytes = json.dumps(active).encode()
        put(store, "browser/active.json", active_bytes)
        put(store, f"{active_prefix}/manifest.json", b"current")
        put(store, "browser/releases/previous/release/manifest.json", b"previous")
        put(store, "browser/releases/old/release/manifest.json", b"old")

        result, pointer, stale = pruning.prune_remote_releases(
            label="browser_r2",
            store=store,
            settings=settings("browser"),
            active_key="browser/active.json",
            releases_prefix="browser/releases/",
            keep_prefixes={"browser/releases/previous/release"},
            execute=True,
        )

        self.assertEqual(pointer["run_id"], "current")
        self.assertEqual(result.removed_count, 1)
        self.assertEqual([row["Key"] for row in stale], ["browser/releases/old/release/manifest.json"])
        self.assertIn("browser/releases/previous/release/manifest.json", store.objects)
        self.assertIn(f"{active_prefix}/manifest.json", store.objects)
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

    def test_archive_prune_removes_copies_of_dropped_releases(self) -> None:
        store = fake_store()
        entries = [
            release_entry("a1", "a", 1),
            release_entry("a2", "a", 2),
            release_entry("b1", "b", 3),
            release_entry("c1", "c", 4),
        ]
        archive.write_archive_index(store, "browser", entries=entries, current_release_id="c1:public")
        for entry in entries:
            put(store, f"browser/archive/{entry['slug']}/index.html", b"<html></html>")
        put(store, "browser/archive/2026-01-09-00000009/index.html", b"orphan")
        index = archive.read_archive_index(store, "browser")
        plan = archive.plan_archive_retention(index["releases"], "c1:public")

        result = pruning.prune_browser_archive(
            store=store,
            settings=settings("browser"),
            browser_prefix="browser",
            active={"run_id": "c1", "archive": {"slug": "2026-01-04-00000004"}},
            plan=plan,
            index=index,
            execute=True,
        )

        self.assertEqual(result.removed_count, 2)
        remaining = sorted(key for key in store.objects if key.endswith("index.html"))
        self.assertEqual(
            remaining,
            [
                "browser/archive/2026-01-02-00000002/index.html",
                "browser/archive/2026-01-03-00000003/index.html",
                "browser/archive/2026-01-04-00000004/index.html",
            ],
        )
        rewritten = archive.read_archive_index(store, "browser")
        self.assertEqual(
            [entry["release_id"] for entry in rewritten["releases"]],
            ["c1:public", "b1:public", "a2:public"],
        )

    def test_archive_prune_refuses_without_an_index(self) -> None:
        store = fake_store()
        put(store, "browser/archive/2026-01-01-00000001/index.html", b"<html></html>")
        archived = pruning.list_archived_objects(store, settings=settings("browser"), browser_prefix="browser")

        with self.assertRaisesRegex(RuntimeError, "archive index is empty or missing"):
            pruning.require_archive_index(archived, archive.empty_archive_index())


class LocalPruneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.roots = {
            "graph": self.root / "data/processed/graph_payload_runs",
            "kg": self.root / "data/processed/kg_routed_runs",
            "query_api": self.root / "data/processed/query_api_runs",
            "extraction": self.root / "data/processed/extraction/routed_runs",
        }
        self.staging = self.root / "data/processed/release_staging"
        self.graph_pointer = self.root / "graph_active.json"
        self.extraction_pointer = self.root / "extraction_active.json"
        self.history = self.root / "release_history.jsonl"
        self.promoted_at = 1_800_000_000.0
        for patch in (
            mock.patch.object(pruning, "ROOT", self.root),
            mock.patch.object(pruning, "ACTIVE_GRAPH_POINTER", self.graph_pointer),
            mock.patch.object(pruning, "ACTIVE_EXTRACTION_POINTER", self.extraction_pointer),
            mock.patch.object(pruning, "LOCAL_RELEASE_ROOTS", self.roots),
            mock.patch.object(pruning, "LOCAL_RELEASE_STAGING", self.staging),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.write_active_release("current")

    def write_active_release(self, run_id: str) -> None:
        self.graph_pointer.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "release_id": f"{run_id}:evidence",
                    "active_manifest": f"data/processed/graph_payload_runs/{run_id}/graph_payload_manifest.json",
                    "kg_dir": f"data/processed/kg_routed_runs/{run_id}",
                }
            ),
            encoding="utf-8",
        )
        self.extraction_pointer.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "release_id": f"{run_id}:evidence",
                    "updated_at_utc": "2027-01-15T08:00:00+00:00",
                    "outputs_jsonl": f"data/processed/extraction/routed_runs/{run_id}/route_extraction_outputs.jsonl",
                    "evidence_rows_json": f"data/processed/extraction/routed_runs/{run_id}/routed_evidence_rows.json",
                }
            ),
            encoding="utf-8",
        )
        (self.roots["graph"] / run_id).mkdir(parents=True)
        (self.roots["graph"] / run_id / "graph_payload_manifest.json").write_text("{}", encoding="utf-8")
        (self.roots["kg"] / run_id).mkdir(parents=True)
        (self.roots["query_api"] / run_id).mkdir(parents=True)
        (self.roots["query_api"] / run_id / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "release_id": f"{run_id}:evidence",
                    "evidence_release_id": f"{run_id}:evidence",
                }
            ),
            encoding="utf-8",
        )
        (self.roots["extraction"] / run_id).mkdir(parents=True)
        (self.roots["extraction"] / run_id / "route_extraction_outputs.jsonl").touch()
        (self.roots["extraction"] / run_id / "routed_evidence_rows.json").touch()

    def make_run(self, run_id: str, *, modified: float, keep: bool = False) -> None:
        for root_name in ("kg", "extraction"):
            folder = self.roots[root_name] / run_id
            folder.mkdir(parents=True)
            data = folder / "data.json"
            data.write_text("{}", encoding="utf-8")
            if keep:
                (folder / pruning.KEEP_MARKER).touch()
            for path in (data, *(folder.iterdir()), folder):
                os.utime(path, (modified, modified))

    def record(self, kind: str, run_id: str, promoted_at: float) -> None:
        stamp = dt.datetime.fromtimestamp(promoted_at, dt.timezone.utc).isoformat()
        append_release_history(
            {
                "kind": kind,
                "run_id": run_id,
                "evidence_release_id": f"{run_id}:evidence",
                "public_release_id": "",
                "promoted_at": stamp,
                "recorded_at": stamp,
            },
            self.history,
        )

    def test_local_plan_keeps_releases_in_use_and_recent_work(self) -> None:
        promoted = self.promoted_at
        self.record("promotion", "older", promoted - 60 * DAY)
        self.record("seed", "previous", promoted - 30 * DAY)
        self.record("promotion", "current", promoted)
        self.make_run("older", modified=promoted - 60 * DAY)
        self.make_run("previous", modified=promoted - 30 * DAY)
        self.make_run("candidate_new", modified=promoted + DAY)
        self.make_run("candidate_recent", modified=promoted - DAY)
        self.make_run("candidate_old", modified=promoted - 20 * DAY)
        self.make_run("protected", modified=promoted - 90 * DAY, keep=True)
        self.staging.mkdir(parents=True)
        (self.staging / "leftover").mkdir()

        run_id, kept, removed = pruning.plan_local_retention(
            history_path=self.history,
            now=promoted + 2 * DAY,
        )

        self.assertEqual(run_id, "current")
        self.assertEqual(
            {decision.name: decision.reason for decision in kept},
            {
                "candidate_new": "never published; changed after the active release was promoted",
                "candidate_recent": "never published; changed in the last 7 days",
                "current": "active release",
                "previous": "release published before the active one",
                "protected": "protected by a .keep file",
            },
        )
        self.assertEqual(
            {decision.name for decision in removed},
            {"older", "candidate_old", "release_staging/leftover"},
        )

        result = pruning.prune_local_release_history(
            execute=True,
            history_path=self.history,
            now=promoted + 2 * DAY,
        )
        self.assertTrue(result.executed)
        self.assertFalse((self.roots["kg"] / "older").exists())
        self.assertFalse((self.roots["kg"] / "candidate_old").exists())
        self.assertTrue((self.roots["kg"] / "previous").exists())
        self.assertTrue((self.roots["kg"] / "current").exists())

    def test_without_history_unpublished_runs_newer_than_the_active_release_are_kept(self) -> None:
        promoted = archive.parse_timestamp("2027-01-15T08:00:00+00:00").timestamp()
        self.make_run("luna_candidate", modified=promoted + 10 * DAY)
        self.make_run("stale", modified=promoted - 40 * DAY)

        _run_id, kept, removed = pruning.plan_local_retention(
            history_path=self.history,
            now=promoted + 20 * DAY,
            extra_keep={"stale": "previous release in the R2 archive"},
        )

        self.assertIn("luna_candidate", {decision.name for decision in kept})
        self.assertIn("stale", {decision.name for decision in kept})
        self.assertEqual(removed, [])

    def test_runs_with_raw_model_outputs_are_never_pruned(self) -> None:
        promoted = self.promoted_at
        self.record("promotion", "replaced", promoted - 60 * DAY)
        self.record("promotion", "previous", promoted - 30 * DAY)
        self.record("promotion", "current", promoted)
        for run_id in ("replaced", "batch_run", "raw_run", "derived_only"):
            self.make_run(run_id, modified=promoted - 60 * DAY)
        for run_id in ("replaced", "batch_run"):
            batches = self.roots["extraction"] / run_id / "async_batches"
            batches.mkdir()
            (batches / "batch_001_results.jsonl").write_text("{}\n", encoding="utf-8")
        (self.roots["extraction"] / "raw_run" / "route_extraction_raw.jsonl").write_text("{}\n", encoding="utf-8")

        _run_id, kept, removed = pruning.plan_local_retention(
            history_path=self.history,
            now=promoted + 30 * DAY,
        )

        reasons = {decision.name: decision.reason for decision in kept}
        for run_id in ("replaced", "batch_run", "raw_run"):
            self.assertEqual(reasons[run_id], "holds raw model requests or responses")
        self.assertEqual({decision.name for decision in removed}, {"derived_only"})

    def test_local_prune_refuses_cross_run_extraction_dependencies(self) -> None:
        pointer = json.loads(self.extraction_pointer.read_text(encoding="utf-8"))
        pointer["outputs_jsonl"] = "data/processed/extraction/routed_runs/older/route_extraction_outputs.jsonl"
        self.extraction_pointer.write_text(json.dumps(pointer), encoding="utf-8")
        (self.roots["extraction"] / "older").mkdir(parents=True)
        (self.roots["extraction"] / "older/route_extraction_outputs.jsonl").touch()

        with self.assertRaisesRegex(ValueError, "not self-contained"):
            pruning.validate_local_active_release()


if __name__ == "__main__":
    unittest.main()
