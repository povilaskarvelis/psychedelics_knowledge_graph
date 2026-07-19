import unittest

from services.query_api.config import R2Settings
from services.query_api.r2_store import R2ObjectStore


class R2ObjectStoreTest(unittest.TestCase):
    def settings(self) -> R2Settings:
        return R2Settings(
            account_id="account",
            bucket="bucket",
            access_key_id="access",
            secret_access_key="secret",
            endpoint_url="https://account.r2.cloudflarestorage.com",
        )

    def test_runtime_store_has_no_public_download_url(self) -> None:
        store = R2ObjectStore(self.settings(), client=object())
        self.assertFalse(hasattr(store, "download_url"))


if __name__ == "__main__":
    unittest.main()
