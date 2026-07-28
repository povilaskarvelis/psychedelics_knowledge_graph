from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

from .config import Settings
from .mcp_server import create_mcp_server
from .models import PaperQuery, RelationshipQuery
from .repository import (
    InvalidQuery,
    QueryArtifactUnavailable,
    QueryNotFound,
    QueryService,
    ReleaseChanged,
)
from .r2_sync import sync_from_settings


LOGGER = logging.getLogger("uvicorn.error")
MAX_REQUEST_BODY_BYTES = 256 * 1024


def create_app(
    service: QueryService | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or QueryService.from_settings(settings)
    mcp = create_mcp_server(service, settings)

    def load_remote_data(target_app: FastAPI) -> None:
        LOGGER.info("Starting R2 data synchronization")
        try:
            result = sync_from_settings(settings)
        except Exception as exc:
            target_app.state.data_status = "error"
            target_app.state.data_error = type(exc).__name__
            LOGGER.exception("R2 data synchronization failed")
            return
        target_app.state.data_status = "ready"
        target_app.state.data_error = ""
        if result is not None:
            LOGGER.info(
                "R2 data synchronization complete: release=%s source=%s",
                result["release_id"],
                "downloaded" if result["downloaded"] else "cached",
            )

    @contextlib.asynccontextmanager
    async def lifespan(target_app: FastAPI):
        if settings.r2 is not None:
            threading.Thread(
                target=load_remote_data,
                args=(target_app,),
                name="r2-data-sync",
                daemon=True,
            ).start()
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="Psychedelics Knowledge Graph API",
        version="1.0.0",
        summary="Programmatic access to Psychedelics Knowledge Graph.",
        description=(
            "Search papers, concepts, externally identified authors, and deduplicated "
            "paper-level relationships. Primary studies, meta-analyses, and reviews "
            "are classified separately. Granular extracted findings, statistics, "
            "quotes, and internal curation fields are intentionally not public."
        ),
        servers=[
            {
                "url": "/",
                "description": "Current service origin",
            }
        ],
        openapi_external_docs={
            "description": "API guide",
            "url": "https://psychedelicskg.com/api/",
        },
        lifespan=lifespan,
    )
    app.state.query_service = service
    app.state.mcp = mcp
    if settings.r2 is not None:
        app.state.data_status = "loading"
    else:
        try:
            service.health()
        except QueryArtifactUnavailable:
            app.state.data_status = "error"
        else:
            app.state.data_status = "ready"
    app.state.data_error = ""

    @app.middleware("http")
    async def limit_request_body(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            raw_length = request.headers.get("content-length", "").strip()
            try:
                content_length = int(raw_length) if raw_length else 0
            except ValueError:
                content_length = 0
            if content_length > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "request_too_large",
                        "detail": f"Request bodies are limited to {MAX_REQUEST_BODY_BYTES} bytes.",
                    },
                )
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "request_too_large",
                            "detail": f"Request bodies are limited to {MAX_REQUEST_BODY_BYTES} bytes.",
                        },
                    )
                body.extend(chunk)
            request._body = bytes(body)
        return await call_next(request)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "MCP-Protocol-Version"],
            expose_headers=["ETag", "X-Release-ID", "Mcp-Session-Id"],
        )

    @app.exception_handler(QueryArtifactUnavailable)
    async def artifact_unavailable(
        _request: Request, exc: QueryArtifactUnavailable
    ) -> JSONResponse:
        data_status = app.state.data_status
        if data_status == "loading":
            detail = "The research database is still loading. Retry shortly."
        elif data_status == "error":
            detail = "The research database could not be loaded; see service logs."
        else:
            detail = str(exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "artifact_unavailable",
                "data_status": data_status,
                "detail": detail,
            },
            headers={"Retry-After": "10"} if data_status == "loading" else None,
        )

    @app.exception_handler(QueryNotFound)
    async def not_found(_request: Request, exc: QueryNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"error": "not_found", "detail": str(exc)}
        )

    @app.exception_handler(ReleaseChanged)
    async def release_changed(_request: Request, exc: ReleaseChanged) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "release_changed", "detail": str(exc)}
        )

    @app.exception_handler(InvalidQuery)
    async def invalid_query(_request: Request, exc: InvalidQuery) -> JSONResponse:
        return JSONResponse(
            status_code=400, content={"error": "invalid_query", "detail": str(exc)}
        )

    def service_index() -> dict[str, Any]:
        return {
            "name": "Psychedelics Knowledge Graph API",
            "api": "/api/v1",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "mcp": "/mcp",
            "data_status": app.state.data_status,
            "readiness": "/readyz",
            "website_documentation": "https://psychedelicskg.com/api/",
            "agent_guide": "https://psychedelicskg.com/api/agent-guide.md",
            "endpoints": {
                "filters": "/api/v1/facets",
                "concept_search": "/api/v1/concepts/search",
                "author_search": "/api/v1/authors/search",
                "paper_search": "/api/v1/papers/query",
                "relationship_search": "/api/v1/relationships/query",
            },
        }

    @app.get("/", tags=["service"])
    def root() -> dict[str, Any]:
        return service_index()

    @app.get("/api/v1", tags=["service"])
    def api_index() -> dict[str, Any]:
        return service_index()

    @app.get("/llms.txt", include_in_schema=False)
    def llms_index() -> RedirectResponse:
        return RedirectResponse("https://psychedelicskg.com/llms.txt", status_code=307)

    @app.get("/healthz", tags=["service"])
    def health() -> dict[str, Any]:
        """Confirm that the web process can accept requests."""
        return {
            "status": "ok",
            "data_status": app.state.data_status,
        }

    @app.get("/readyz", tags=["service"])
    def readiness() -> Response:
        """Confirm that the research database is ready for queries."""
        try:
            detail = service.health()
        except QueryArtifactUnavailable:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "data_status": app.state.data_status,
                    "detail": (
                        "The research database is still loading."
                        if app.state.data_status == "loading"
                        else "The research database could not be loaded; see service logs."
                    ),
                },
            )
        return JSONResponse(
            content={
                **detail,
                "status": "ready",
                "data_status": app.state.data_status,
            }
        )

    @app.get("/api/v1/meta", tags=["release"])
    def meta() -> dict[str, Any]:
        return service.meta()

    @app.get("/api/v1/schema", tags=["release"])
    def schema() -> dict[str, Any]:
        return service.schema()

    @app.get("/api/v1/facets", tags=["catalogue"])
    def facets() -> dict[str, Any]:
        return service.facets()

    @app.get("/api/v1/concepts/search", tags=["concepts"])
    def search_concepts(
        q: str = Query(min_length=1, max_length=200),
        concept_kind: list[str] | None = Query(
            default=None,
            description="Match kinds observed at either endpoint of public relationships.",
        ),
        domain: list[str] | None = Query(
            default=None,
            description="Match domains observed on public relationships involving the concept.",
        ),
        limit: int = Query(default=15, ge=1, le=50),
    ) -> dict[str, Any]:
        return service.search_concepts(
            q,
            concept_kinds=concept_kind or [],
            domains=domain or [],
            limit=limit,
        )

    @app.get("/api/v1/concepts/{concept_id}", tags=["concepts"])
    def get_concept(concept_id: str) -> dict[str, Any]:
        return service.get_concept(concept_id)

    @app.get("/api/v1/authors/search", tags=["authors"])
    def search_authors(
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(default=15, ge=1, le=50),
    ) -> dict[str, Any]:
        return service.search_authors(q, limit=limit)

    @app.get("/api/v1/authors/{author_id}", tags=["authors"])
    def get_author(author_id: str) -> dict[str, Any]:
        return service.get_author(author_id)

    @app.get("/api/v1/authors/{author_id}/papers", tags=["authors", "papers"])
    def get_author_papers(
        author_id: str,
        limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=2048),
    ) -> dict[str, Any]:
        return service.get_author_papers(author_id, limit=limit, cursor=cursor)

    @app.post("/api/v1/papers/query", tags=["papers"])
    def query_papers(request: PaperQuery) -> dict[str, Any]:
        return service.query_papers(request)

    @app.get("/api/v1/papers/{paper_id_or_doi:path}", tags=["papers"])
    def get_paper(
        paper_id_or_doi: str,
        include_relationships: bool = True,
        relationship_limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return service.get_paper(
            paper_id_or_doi,
            include_relationships=include_relationships,
            relationship_limit=relationship_limit,
        )

    @app.post("/api/v1/relationships/query", tags=["relationships"])
    def query_relationships(request: RelationshipQuery) -> dict[str, Any]:
        return service.query_relationships(request)

    # The MCP app contains its own /mcp route. Mounting it last leaves REST and
    # OpenAPI routes in the parent application while sharing one process.
    app.mount("/", mcp.streamable_http_app())
    return app


settings = Settings.from_env()
app = create_app(settings=settings)
