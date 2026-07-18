from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings
from .models import AggregateQuery, FindingFilters, FindingQuery, NeighborQuery
from .repository import QueryService


MCP_INSTRUCTIONS = """
Query the public Psychedelics Knowledge Graph without merging distinct evidence layers.
Primary studies, meta-analyses, and reviews are separate literature_source values.
The default main_graph scope returns findings admitted to the overview graph;
all_normalized also includes findings retained as paper detail. Finding counts are not
independent study counts, so prefer study_count for evidence-volume comparisons. Return
DOIs, evidence locators, and result direction when supporting an answer.
""".strip()


def create_mcp_server(
    service: QueryService, settings: Settings | None = None
) -> FastMCP:
    transport_security = None
    if settings and (settings.mcp_allowed_hosts or settings.mcp_allowed_origins):
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.mcp_allowed_hosts),
            allowed_origins=list(settings.mcp_allowed_origins),
        )
    mcp = FastMCP(
        name="Psychedelics Knowledge Graph",
        instructions=MCP_INSTRUCTIONS,
        website_url="https://psychedelicskg.com/",
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )

    @mcp.tool()
    def get_release_info() -> dict[str, Any]:
        """Get the active data release, row counts, evidence semantics, and API links."""
        return service.meta()

    @mcp.tool()
    def search_entities(
        query: str,
        entity_kinds: list[str] | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        """Resolve a compound, condition, target, outcome, or alias to canonical entity IDs."""
        return service.search_entities(
            query,
            entity_kinds=entity_kinds or [],
            limit=limit,
        )

    @mcp.tool()
    def get_entity(entity_id: str) -> dict[str, Any]:
        """Get one canonical entity, aliases, parent mapping, and evidence counts."""
        return service.get_entity(entity_id)

    @mcp.tool()
    def find_evidence(
        compounds: list[str] | None = None,
        compound_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
        entity_labels: list[str] | None = None,
        entity_kinds: list[str] | None = None,
        domains: list[str] | None = None,
        evidence_types: list[str] | None = None,
        literature_sources: list[str] | None = None,
        relation_types: list[str] | None = None,
        directions: list[str] | None = None,
        text_depth: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        query: str | None = None,
        scope: str = "main_graph",
        detail_level: str = "summary",
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Find normalized evidence with bounded filters and release-safe pagination.

        Use canonical IDs from search_entities where possible. Set scope to all_normalized
        to include findings retained as paper detail. Keep literature_sources separate when
        interpreting primary studies, meta-analyses, and reviews.
        """
        request = FindingQuery(
            filters=FindingFilters(
                compounds=compounds or [],
                compound_ids=compound_ids or [],
                entity_ids=entity_ids or [],
                entity_labels=entity_labels or [],
                entity_kinds=entity_kinds or [],
                domains=domains or [],
                evidence_types=evidence_types or [],
                literature_sources=literature_sources or [],
                relation_types=relation_types or [],
                directions=directions or [],
                text_depth=text_depth or [],
                year_from=year_from,
                year_to=year_to,
                query=query,
            ),
            scope=scope,
            detail_level=detail_level,
            limit=limit,
            cursor=cursor,
        )
        return service.query_findings(request)

    @mcp.tool()
    def get_finding(finding_id: str) -> dict[str, Any]:
        """Get a complete public finding record, including provenance when available."""
        return service.get_finding(finding_id)

    @mcp.tool()
    def get_paper(
        paper_id_or_doi: str,
        include_findings: bool = True,
        finding_limit: int = 50,
    ) -> dict[str, Any]:
        """Get a paper or report by canonical paper ID or DOI and optionally its findings."""
        return service.get_paper(
            paper_id_or_doi,
            include_findings=include_findings,
            finding_limit=finding_limit,
        )

    @mcp.tool()
    def aggregate_evidence(
        group_by: list[str] | None = None,
        compounds: list[str] | None = None,
        entity_ids: list[str] | None = None,
        entity_kinds: list[str] | None = None,
        domains: list[str] | None = None,
        literature_sources: list[str] | None = None,
        directions: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        scope: str = "main_graph",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Count distinct studies, findings, and proposition groups by safe public fields."""
        request = AggregateQuery(
            filters=FindingFilters(
                compounds=compounds or [],
                entity_ids=entity_ids or [],
                entity_kinds=entity_kinds or [],
                domains=domains or [],
                literature_sources=literature_sources or [],
                directions=directions or [],
                year_from=year_from,
                year_to=year_to,
            ),
            scope=scope,
            group_by=group_by or ["compound", "entity_label"],
            limit=limit,
        )
        return service.aggregate(request)

    @mcp.tool()
    def get_neighborhood(
        entity_id: str,
        literature_sources: list[str] | None = None,
        relation_types: list[str] | None = None,
        scope: str = "main_graph",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get a bounded one-hop evidence neighborhood around a canonical entity ID."""
        return service.neighbors(
            entity_id,
            NeighborQuery(
                scope=scope,
                literature_sources=literature_sources or [],
                relation_types=relation_types or [],
                limit=limit,
            ),
        )

    @mcp.resource("psychedelics-kg://release/current", mime_type="application/json")
    def release_resource() -> str:
        """Active release metadata and evidence semantics."""
        return json.dumps(service.meta(), ensure_ascii=False, sort_keys=True)

    @mcp.resource("psychedelics-kg://schema/public-query", mime_type="application/json")
    def schema_resource() -> str:
        """Public DuckDB table schema and query semantics."""
        return json.dumps(service.schema(), ensure_ascii=False, sort_keys=True)

    return mcp
