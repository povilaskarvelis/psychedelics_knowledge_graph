from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .config import Settings
from .mcp_server import create_mcp_server
from .models import AggregateQuery, FindingQuery, NeighborQuery
from .repository import (
    InvalidQuery,
    QueryArtifactUnavailable,
    QueryNotFound,
    QueryService,
    ReleaseChanged,
)


def create_app(
    service: QueryService | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or QueryService.from_settings(settings)
    mcp = create_mcp_server(service, settings)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="Psychedelics Knowledge Graph API",
        version="1.0.0",
        summary="Read-only, release-aware access to normalized psychedelic research evidence.",
        description=(
            "Primary studies, meta-analyses, and reviews remain separate. The default "
            "main_graph scope returns overview-admitted findings; all_normalized also "
            "returns findings retained as paper detail. Finding rows are not independent studies."
        ),
        servers=[
            {
                "url": settings.public_base_url,
                "description": "Configured service endpoint",
            }
        ],
        openapi_external_docs={
            "description": "Data, API, and agent access guide",
            "url": "https://psychedelicskg.com/developers/",
        },
        lifespan=lifespan,
    )
    app.state.query_service = service
    app.state.mcp = mcp

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
        return JSONResponse(
            status_code=503,
            content={"error": "artifact_unavailable", "detail": str(exc)},
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
            "api": f"{settings.public_base_url}/api/v1",
            "docs": f"{settings.public_base_url}/docs",
            "openapi": f"{settings.public_base_url}/openapi.json",
            "mcp": f"{settings.public_base_url}/mcp",
            "website_documentation": "https://psychedelicskg.com/developers/",
            "agent_guide": "https://psychedelicskg.com/developers/agent-guide.md",
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
        return service.health()

    @app.get("/api/v1/meta", tags=["release"])
    def meta() -> dict[str, Any]:
        return service.meta()

    @app.get("/api/v1/schema", tags=["release"])
    def schema() -> dict[str, Any]:
        return service.schema()

    @app.get("/api/v1/entities/search", tags=["entities"])
    def search_entities(
        q: str = Query(min_length=1, max_length=200),
        entity_kind: list[str] | None = Query(default=None),
        limit: int = Query(default=15, ge=1, le=50),
    ) -> dict[str, Any]:
        return service.search_entities(q, entity_kinds=entity_kind or [], limit=limit)

    @app.get("/api/v1/entities/{entity_id}", tags=["entities"])
    def get_entity(entity_id: str) -> dict[str, Any]:
        return service.get_entity(entity_id)

    @app.post("/api/v1/entities/{entity_id}/neighbors", tags=["entities"])
    def neighbors(entity_id: str, request: NeighborQuery) -> dict[str, Any]:
        return service.neighbors(entity_id, request)

    @app.post("/api/v1/findings/query", tags=["findings"])
    def query_findings(request: FindingQuery) -> dict[str, Any]:
        return service.query_findings(request)

    @app.get("/api/v1/findings/{finding_id}", tags=["findings"])
    def get_finding(finding_id: str) -> dict[str, Any]:
        return service.get_finding(finding_id)

    @app.get("/api/v1/papers/{paper_id_or_doi:path}", tags=["papers"])
    def get_paper(
        paper_id_or_doi: str,
        include_findings: bool = True,
        finding_limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return service.get_paper(
            paper_id_or_doi,
            include_findings=include_findings,
            finding_limit=finding_limit,
        )

    @app.post("/api/v1/aggregate", tags=["findings"])
    def aggregate(request: AggregateQuery) -> dict[str, Any]:
        return service.aggregate(request)

    def download(logical_name: str) -> Response:
        target = service.download_target(logical_name)
        headers = {
            "ETag": f'"{target.entry["sha256"]}"',
            "X-Release-ID": target.info.release_id,
            "Cache-Control": "public, max-age=3600",
        }
        if target.url:
            return RedirectResponse(target.url, status_code=307, headers=headers)
        assert target.path is not None
        return FileResponse(
            target.path,
            filename=Path(target.path).name,
            headers=headers,
        )

    @app.get("/api/v1/downloads/database", tags=["downloads"])
    def download_database() -> Response:
        return download("database")

    @app.get("/api/v1/downloads/schema", tags=["downloads"])
    def download_schema() -> Response:
        return download("schema")

    @app.get("/api/v1/downloads/tables/{table_name}", tags=["downloads"])
    def download_table(table_name: str) -> Response:
        return download(f"table:{table_name}")

    # The MCP app contains its own /mcp route. Mounting it last leaves REST and
    # OpenAPI routes in the parent application while sharing one process.
    app.mount("/", mcp.streamable_http_app())
    return app


settings = Settings.from_env()
app = create_app(settings=settings)
