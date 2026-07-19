import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "services.query_api.app:app",
        host=os.environ.get("PKG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT") or os.environ.get("PKG_PORT") or "8000"),
        reload=False,
    )
