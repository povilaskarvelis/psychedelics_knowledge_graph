import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pipeline.publish.publish_query_api_r2 import publish_active_query_release
from services.query_api.app import create_app
from services.query_api.config import R2Settings, Settings
from services.query_api.models import PaperQuery
from services.query_api.r2_sync import R2ReleaseSynchronizer, validate_remote_active
from services.query_api.repository import QueryService, ReleaseResolver
from tests.query_api_fixtures import build_active_query_release
from tests.r2_fixtures import FakeObjectStore
from tests.test_publish_query_api_r2 import r2_settings


class QueryApiR2SyncTest(unittest.TestCase):
    def test_syncs_private_query_runtime_without_bulk_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            pointer, query_runs = build_active_query_release(source)
            store = FakeObjectStore()
            r2 = r2_settings()
            publish_active_query_release(
                store=store,
                settings=r2,
                active_pointer_path=pointer,
                query_runs_dir=query_runs,
            )

            data_dir = root / "runtime-data"
            settings = Settings(
                data_dir=data_dir,
                active_pointer=data_dir / "processed/graph_payload_active.json",
                query_runs_dir=data_dir / "processed/query_api_runs",
                public_base_url="https://api.example.test",
                cors_origins=(),
                mcp_allowed_hosts=(),
                mcp_allowed_origins=(),
                r2=r2,
            )
            result = R2ReleaseSynchronizer(
                service_settings=settings,
                r2_settings=r2,
                store=store,
            ).sync()

            self.assertTrue(result["downloaded"])
            self.assertEqual(result["release_id"], "test_run:r1")
            local_pointer = json.loads(
                settings.active_pointer.read_text(encoding="utf-8")
            )
            self.assertEqual(local_pointer["release_id"], "test_run:r1")
            artifact = settings.query_runs_dir / "test_run"
            self.assertTrue((artifact / "public_api.duckdb").is_file())
            self.assertFalse((artifact / "tables").exists())

            service = QueryService(
                resolver=ReleaseResolver(
                    active_pointer=settings.active_pointer,
                    query_runs_dir=settings.query_runs_dir,
                ),
                public_base_url=settings.public_base_url,
            )
            query = service.query_papers(PaperQuery(limit=10))
            self.assertEqual(query["meta"]["total"], 3)
            app = create_app(service, settings=settings)
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/downloads/tables/papers",
                    follow_redirects=False,
                )
            self.assertEqual(response.status_code, 404)

            second = R2ReleaseSynchronizer(
                service_settings=settings,
                r2_settings=r2,
                store=store,
            ).sync()
            self.assertFalse(second["downloaded"])

    def test_download_checksum_failure_leaves_pointer_unmodified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            pointer, query_runs = build_active_query_release(source)
            store = FakeObjectStore()
            r2 = r2_settings()
            active = publish_active_query_release(
                store=store,
                settings=r2,
                active_pointer_path=pointer,
                query_runs_dir=query_runs,
            )
            database_key = active["files"]["database"]["key"]
            store.objects[database_key] += b"corrupt"

            data_dir = root / "runtime-data"
            settings = Settings(
                data_dir=data_dir,
                active_pointer=data_dir / "processed/graph_payload_active.json",
                query_runs_dir=data_dir / "processed/query_api_runs",
                public_base_url="",
                cors_origins=(),
                mcp_allowed_hosts=(),
                mcp_allowed_origins=(),
                r2=r2,
            )
            with self.assertRaisesRegex(RuntimeError, "failed verification"):
                R2ReleaseSynchronizer(
                    service_settings=settings,
                    r2_settings=r2,
                    store=store,
                ).sync()
            self.assertFalse(settings.active_pointer.exists())

    def test_r2_environment_supports_default_and_eu_endpoints(self) -> None:
        env = {
            "PKG_API_R2_ACCOUNT_ID": "abc",
            "PKG_API_R2_BUCKET": "bucket",
            "PKG_API_R2_ACCESS_KEY_ID": "key",
            "PKG_API_R2_SECRET_ACCESS_KEY": "secret",
            "PKG_API_R2_JURISDICTION": "eu",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = R2Settings.from_env(
                required=True,
                env_prefix="PKG_API_R2",
                default_object_prefix="query-api",
            )
        assert settings is not None
        self.assertEqual(
            settings.endpoint_url, "https://abc.eu.r2.cloudflarestorage.com"
        )
        self.assertEqual(settings.active_key, "query-api/active/catalogue-v2.json")
        self.assertEqual(settings.legacy_active_key, "query-api/active.json")

    def test_service_does_not_use_public_browser_bucket_credentials(self) -> None:
        browser_only_env = {
            "PKG_R2_ACCOUNT_ID": "public-account",
            "PKG_R2_BUCKET": "public-browser-bucket",
            "PKG_R2_ACCESS_KEY_ID": "public-key",
            "PKG_R2_SECRET_ACCESS_KEY": "public-secret",
        }
        with patch.dict(os.environ, browser_only_env, clear=True):
            settings = Settings.from_env()
        self.assertIsNone(settings.r2)

    def test_remote_pointer_rejects_path_traversal_run_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe run_id"):
            validate_remote_active(
                {
                    "schema_version": "psychedelics_kg_r2_active_release_v1",
                    "run_id": "../escape",
                    "release_id": "release",
                    "evidence_release_id": "evidence-release",
                    "contract_key": "catalogue-v2",
                    "query_manifest_schema": "psychedelics_kg_public_catalogue_manifest_v2",
                    "manifest": {
                        "key": "query-api/releases/manifest.json",
                        "path": "manifest.json",
                        "bytes": 1,
                        "sha256": "0" * 64,
                    },
                    "files": {},
                }
            )


if __name__ == "__main__":
    unittest.main()
