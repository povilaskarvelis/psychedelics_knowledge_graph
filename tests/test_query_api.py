import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from services.query_api.app import create_app
from services.query_api.config import Settings
from services.query_api.mcp_server import create_mcp_server
from services.query_api.models import (
    AggregateQuery,
    FindingFilters,
    FindingQuery,
    NeighborQuery,
)
from services.query_api.repository import QueryService, ReleaseChanged, ReleaseResolver
from tests.query_api_fixtures import build_active_query_release


class QueryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        pointer, query_runs = build_active_query_release(self.root)
        self.resolver = ReleaseResolver(
            active_pointer=pointer, query_runs_dir=query_runs
        )
        self.service = QueryService(
            self.resolver, public_base_url="https://api.example.test"
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_release_search_query_and_aggregate(self) -> None:
        self.assertEqual(self.service.meta()["row_counts"]["findings"], 3)
        search = self.service.search_entities("depression")
        self.assertEqual(
            search["results"][0]["entity_id"],
            "clinical_entity:major_depressive_disorder",
        )
        self.assertIn("MDD", search["results"][0]["aliases_json"])

        primary = self.service.query_findings(
            FindingQuery(
                filters=FindingFilters(
                    compounds=["Psilocybin"],
                    domains=["clinical_outcome"],
                ),
                limit=1,
            )
        )
        self.assertEqual(primary["meta"]["total"], 1)
        self.assertEqual(primary["results"][0]["finding_id"], "finding:primary")

        all_findings = self.service.query_findings(
            FindingQuery(
                filters=FindingFilters(compounds=["Psilocybin"]),
                scope="all_normalized",
                limit=10,
            )
        )
        self.assertEqual(all_findings["meta"]["total"], 2)
        self.assertEqual(
            {row["literature_source"] for row in all_findings["results"]},
            {"primary", "reviews"},
        )

        aggregate = self.service.aggregate(
            AggregateQuery(
                filters=FindingFilters(compounds=["Psilocybin"]),
                scope="all_normalized",
                group_by=["literature_source"],
            )
        )
        self.assertEqual(
            {
                row["literature_source"]: row["study_count"]
                for row in aggregate["results"]
            },
            {"primary": 1, "reviews": 1},
        )

    def test_cursor_is_bound_to_release(self) -> None:
        first = self.service.query_findings(
            FindingQuery(scope="all_normalized", limit=1)
        )
        pointer = self.resolver.active_pointer
        pointer.write_text(
            json.dumps({"run_id": "test_run", "release_id": "test_run:r2"}),
            encoding="utf-8",
        )
        with self.assertRaises(ReleaseChanged):
            self.service.query_findings(
                FindingQuery(
                    scope="all_normalized",
                    limit=1,
                    cursor=first["meta"]["next_cursor"],
                )
            )

    def test_paper_neighborhood_download_and_http_contract(self) -> None:
        paper = self.service.get_paper("10.1000/primary")
        self.assertEqual(paper["data"]["paper_id"], "paper:10.1000/primary")
        self.assertEqual(paper["findings"][0]["finding_id"], "finding:primary")

        neighbors = self.service.neighbors(
            "compound:psilocybin",
            NeighborQuery(scope="all_normalized"),
        )
        self.assertEqual(len(neighbors["results"]), 2)

        settings = Settings(
            data_dir=self.root,
            active_pointer=self.resolver.active_pointer,
            query_runs_dir=self.resolver.query_runs_dir,
            public_base_url="https://api.example.test",
            cors_origins=(),
            mcp_allowed_hosts=(),
            mcp_allowed_origins=(),
        )
        app = create_app(self.service, settings=settings)
        with TestClient(app) as client:
            service_index = client.get("/api/v1")
            self.assertEqual(service_index.status_code, 200)
            self.assertEqual(
                service_index.json()["agent_guide"],
                "https://psychedelicskg.com/developers/agent-guide.md",
            )
            response = client.post(
                "/api/v1/findings/query",
                json={
                    "filters": {"compounds": ["Psilocybin"]},
                    "scope": "all_normalized",
                    "limit": 10,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["meta"]["total"], 2)
            openapi = client.get("/openapi.json").json()
            self.assertIn("/api/v1/findings/query", openapi["paths"])
            self.assertEqual(openapi["servers"][0]["url"], "/")
            self.assertEqual(
                openapi["externalDocs"]["url"],
                "https://psychedelicskg.com/developers/",
            )
            llms = client.get("/llms.txt", follow_redirects=False)
            self.assertEqual(llms.status_code, 307)
            self.assertEqual(llms.headers["location"], "https://psychedelicskg.com/llms.txt")
            download = client.get("/api/v1/downloads/tables/findings")
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.headers["x-release-id"], "test_run:r1")


class QueryMcpTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_exposes_structured_read_only_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, query_runs = build_active_query_release(root)
            service = QueryService(
                ReleaseResolver(active_pointer=pointer, query_runs_dir=query_runs)
            )
            mcp = create_mcp_server(service)
            tools = {tool.name for tool in await mcp.list_tools()}
            self.assertEqual(
                tools,
                {
                    "get_release_info",
                    "search_entities",
                    "get_entity",
                    "find_evidence",
                    "get_finding",
                    "get_paper",
                    "aggregate_evidence",
                    "get_neighborhood",
                },
            )
            _content, structured = await mcp.call_tool(
                "find_evidence",
                {
                    "compounds": ["Psilocybin"],
                    "scope": "all_normalized",
                    "limit": 10,
                },
            )
            self.assertEqual(structured["meta"]["total"], 2)


if __name__ == "__main__":
    unittest.main()
