import os

import uvicorn

from .config import Settings
from .r2_sync import sync_from_settings


if __name__ == "__main__":
    settings = Settings.from_env()
    result = sync_from_settings(settings)
    if result is not None:
        print(
            f"Synchronized R2 release {result['release_id']} "
            f"({'downloaded' if result['downloaded'] else 'cached'})",
            flush=True,
        )
    uvicorn.run(
        "services.query_api.app:app",
        host=os.environ.get("PKG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT") or os.environ.get("PKG_PORT") or "8000"),
        reload=False,
    )
