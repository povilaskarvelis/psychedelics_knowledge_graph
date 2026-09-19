from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings
from .models import PaperFilters, PaperQuery, RelationshipFilters, RelationshipQuery
from .repository import QueryService


MCP_INSTRUCTIONS = """
Search the curated public Psychedelics Knowledge Graph catalogue. The public
contract contains papers, concepts, OpenAlex/ORCID-backed authors, and deduplicated
paper-level relationships. It intentionally excludes granular findings,
statistics, quotes, result direction, and internal curation data. Use
list_available_filters to discover controlled values. Public author identities
are backed by OpenAlex or ORCID; unresolved name-only records are excluded, so
returned author lists may be incomplete. Relationships indicate literature
coverage, not proof of benefit, harm, causation, or effectiveness. Counts are
reports, not independent studies; keep primary studies, reviews, and
meta-analyses separate. Missing metadata or relationships do not establish a
negative finding or absence of research.
Filter lists use OR; separate fields use AND. concept_ids matches ANY concept
at either endpoint. Use subject_ids AND object_ids to search a compound–outcome
pair; relationship filters must match the same relationship. Unsupported
arguments are rejected. Paper query text searches title, DOI, journal, and
credited author names, not abstracts or quotations.
Follow meta.next_cursor with the same tool and filters. Restart without a cursor
when filters change, a cursor is obsolete, or the release changes. If get_paper
returns relationships_truncated=true, use find_relationships with its paper_id
and paginate from the beginning to retrieve the complete relationship list.
Website presets define category membership, not the overview's parent grouping
or display thresholds. Unknown metadata remains unknown.
""".strip()


class StrictFastMCP(FastMCP):
    """Reject extra tool arguments before FastMCP's permissive model drops them."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema = {**tool.inputSchema, "additionalProperties": False}
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        if tool is not None:
            unknown = sorted(set(arguments) - set(tool.inputSchema.get("properties", {})))
            if unknown:
                raise ToolError(
                    f"Unsupported arguments for {name}: {', '.join(unknown)}. "
                    "Use the arguments declared in the tool schema."
                )
        return await super().call_tool(name, arguments)


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
    mcp = StrictFastMCP(
        name="Psychedelics Knowledge Graph",
        instructions=MCP_INSTRUCTIONS,
        website_url="https://psychedelicskg.com/",
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )

    @mcp.tool()
    def get_release_info() -> dict[str, Any]:
        """Get the current data version, table counts, scope, and limitations."""
        return service.meta()

    @mcp.tool()
    def list_available_filters() -> dict[str, Any]:
        """List valid paper, relationship, endpoint-kind, and website-view filters."""
        return service.facets()

    @mcp.tool()
    def search_concepts(
        query: str,
        concept_kinds: list[str] | None = None,
        domains: list[str] | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        """Resolve concepts; kind and domain filters use observed public relationships."""
        return service.search_concepts(
            query,
            concept_kinds=concept_kinds or [],
            domains=domains or [],
            limit=limit,
        )

    @mcp.tool()
    def get_concept(concept_id: str) -> dict[str, Any]:
        """Get one standardized concept with aliases, category, hierarchy, and paper count."""
        return service.get_concept(concept_id)

    @mcp.tool()
    def search_authors(query: str, limit: int = 15) -> dict[str, Any]:
        """Search OpenAlex/ORCID-backed authors by preferred name or known name variant."""
        return service.search_authors(query, limit=limit)

    @mcp.tool()
    def get_author_papers(
        author_id: str,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Get papers across all paper types linked to one ORCID/OpenAlex author identity."""
        return service.get_author_papers(author_id, limit=limit, cursor=cursor)

    @mcp.tool()
    def search_papers(
        query: str | None = None,
        paper_ids: list[str] | None = None,
        dois: list[str] | None = None,
        paper_types: list[str] | None = None,
        paper_subtypes: list[str] | None = None,
        author_ids: list[str] | None = None,
        author_names: list[str] | None = None,
        concept_ids: list[str] | None = None,
        subject_ids: list[str] | None = None,
        object_ids: list[str] | None = None,
        subject_labels: list[str] | None = None,
        object_labels: list[str] | None = None,
        domains: list[str] | None = None,
        relation_types: list[str] | None = None,
        subject_kinds: list[str] | None = None,
        object_kinds: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search papers: OR within lists, AND across fields; subject/object IDs match the same relationship."""
        return service.query_papers(
            PaperQuery(
                filters=PaperFilters(
                    query=query,
                    paper_ids=paper_ids or [],
                    dois=dois or [],
                    paper_types=paper_types or [],
                    paper_subtypes=paper_subtypes or [],
                    author_ids=author_ids or [],
                    author_names=author_names or [],
                    concept_ids=concept_ids or [],
                    subject_ids=subject_ids or [],
                    object_ids=object_ids or [],
                    subject_labels=subject_labels or [],
                    object_labels=object_labels or [],
                    domains=domains or [],
                    relation_types=relation_types or [],
                    subject_kinds=subject_kinds or [],
                    object_kinds=object_kinds or [],
                    year_from=year_from,
                    year_to=year_to,
                ),
                limit=limit,
                cursor=cursor,
            )
        )

    @mcp.tool()
    def get_paper(
        paper_id_or_doi: str,
        include_relationships: bool = True,
        relationship_limit: int = 50,
    ) -> dict[str, Any]:
        """Get one paper, its credited authors, and its public relationships."""
        return service.get_paper(
            paper_id_or_doi,
            include_relationships=include_relationships,
            relationship_limit=relationship_limit,
        )

    @mcp.tool()
    def find_relationships(
        paper_ids: list[str] | None = None,
        dois: list[str] | None = None,
        paper_types: list[str] | None = None,
        paper_subtypes: list[str] | None = None,
        author_ids: list[str] | None = None,
        author_names: list[str] | None = None,
        concept_ids: list[str] | None = None,
        subject_ids: list[str] | None = None,
        object_ids: list[str] | None = None,
        subject_labels: list[str] | None = None,
        object_labels: list[str] | None = None,
        domains: list[str] | None = None,
        relation_types: list[str] | None = None,
        subject_kinds: list[str] | None = None,
        object_kinds: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search deduplicated paper-level concept relationships."""
        return service.query_relationships(
            RelationshipQuery(
                filters=RelationshipFilters(
                    paper_ids=paper_ids or [],
                    dois=dois or [],
                    paper_types=paper_types or [],
                    paper_subtypes=paper_subtypes or [],
                    author_ids=author_ids or [],
                    author_names=author_names or [],
                    concept_ids=concept_ids or [],
                    subject_ids=subject_ids or [],
                    object_ids=object_ids or [],
                    subject_labels=subject_labels or [],
                    object_labels=object_labels or [],
                    domains=domains or [],
                    relation_types=relation_types or [],
                    subject_kinds=subject_kinds or [],
                    object_kinds=object_kinds or [],
                    year_from=year_from,
                    year_to=year_to,
                ),
                limit=limit,
                cursor=cursor,
            )
        )

    @mcp.resource("psychedelics-kg://release/current", mime_type="application/json")
    def release_resource() -> str:
        """Current data version, scope, and record counts."""
        return json.dumps(service.meta(), ensure_ascii=False, sort_keys=True)

    @mcp.resource("psychedelics-kg://schema/public-query", mime_type="application/json")
    def schema_resource() -> str:
        """Public catalogue tables, fields, keys, and definitions."""
        return json.dumps(service.schema(), ensure_ascii=False, sort_keys=True)

    return mcp
