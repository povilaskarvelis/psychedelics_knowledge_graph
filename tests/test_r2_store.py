import unittest

from services.query_api.config import R2Settings
from services.query_api.r2_store import R2ObjectStore


class R2ObjectStoreTest(unittest.TestCase):
    def settings(self, *, public_base_url: str = "") -> R2Settings:
        return R2Settings(
            account_id="account",
            bucket="bucket",
            access_key_id="access",
            secret_access_key="secret",
            endpoint_url="https://account.r2.cloudflarestorage.com",
            public_base_url=public_base_url,
        )

    def test_public_url_preserves_key_path_and_encodes_components(self) -> None:
        store = R2ObjectStore(
            self.settings(public_base_url="https://data.example.test")
        )
        self.assertEqual(
            store.download_url("query-api/releases/a file/findings.parquet"),
            "https://data.example.test/query-api/releases/a%20file/findings.parquet",
        )

    def test_private_bucket_uses_short_lived_sigv4_url(self) -> None:
        store = R2ObjectStore(self.settings())
        url = store.download_url("query-api/releases/release/public_api.duckdb")
        self.assertIn("account.r2.cloudflarestorage.com", url)
        self.assertIn("bucket/query-api/releases/release/public_api.duckdb", url)
        self.assertIn("X-Amz-Signature=", url)


if __name__ == "__main__":
    unittest.main()
