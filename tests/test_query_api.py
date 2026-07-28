import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.query_api.app import create_app
from services.query_api.config import Settings
from services.query_api.mcp_server import create_mcp_server
from services.query_api.models import (
    PaperFilters,
    PaperQuery,
    RelationshipFilters,
    RelationshipQuery,
)
from services.query_api.repository import (
    InvalidQuery,
    QueryService,
    ReleaseChanged,
    ReleaseResolver,
    encode_cursor,
)
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

    def test_catalogue_search_filters_and_relationships(self) -> None:
        self.assertEqual(self.service.meta()["row_counts"]["papers"], 3)
        self.assertNotIn("findings", self.service.meta()["row_counts"])

        facets = self.service.facets()
        self.assertEqual(
            {row["value"] for row in facets["paper_types"]},
            {"primary_study", "review"},
        )
        self.assertIn("target", {row["value"] for row in facets["concept_kinds"]})
        self.assertIn("target", {row["value"] for row in facets["object_kinds"]})
        target_view = next(
            view for view in facets["graph_views"] if view["value"] == "target_system"
        )
        self.assertEqual(target_view["filters"]["object_kinds"], ["target", "system_family"])

        concepts = self.service.search_concepts("depression")
        self.assertEqual(
            concepts["results"][0]["concept_id"],
            "clinical_entity:major_depressive_disorder",
        )
        self.assertIn("MDD", concepts["results"][0]["aliases_json"])

        targets = self.service.search_concepts(
            "NMDA",
            concept_kinds=["target"],
            domains=["molecular_target"],
        )
        self.assertEqual(targets["results"][0]["concept_id"], "target:nmda_receptor")
        self.assertEqual(targets["results"][0]["concept_kind"], "biomarker_readout")
        self.assertEqual(targets["results"][0]["observed_kinds"], ["target"])
        self.assertEqual(targets["results"][0]["observed_domains"], ["molecular_target"])
        self.assertEqual(
            self.service.search_concepts("NMDA", concept_kinds=["biomarker_readout"])[
                "results"
            ],
            [],
        )
        self.assertEqual(
            self.service.search_concepts(
                "NMDA",
                concept_kinds=["target"],
                domains=["clinical_outcome"],
            )["results"],
            [],
        )
        target = self.service.get_concept("target:nmda_receptor")["data"]
        self.assertEqual(target["observed_kinds"], ["target"])
        self.assertEqual(target["observed_domains"], ["molecular_target"])

        authors = self.service.search_authors("Ada")
        self.assertEqual(authors["results"][0]["author_name"], "Ada Example")
        author_id = authors["results"][0]["author_id"]
        author_papers = self.service.get_author_papers(author_id)
        self.assertEqual(author_papers["meta"]["total"], 1)
        self.assertEqual(
            author_papers["results"][0]["paper_id"], "paper:10.1000/primary"
        )

        papers = self.service.query_papers(
            PaperQuery(
                filters=PaperFilters(
                    paper_types=["primary_study"],
                    domains=["clinical_outcome"],
                    concept_ids=["compound:psilocybin"],
                )
            )
        )
        self.assertEqual(papers["meta"]["total"], 1)
        self.assertEqual(papers["results"][0]["doi"], "10.1000/primary")
        self.assertEqual(papers["results"][0]["authors"][0]["author_name"], "Ada Example")

        target_papers = self.service.query_papers(
            PaperQuery(
                filters=PaperFilters(
                    subject_kinds=["atomic_compound"],
                    object_kinds=["target"],
                )
            )
        )
        self.assertEqual(target_papers["meta"]["total"], 1)
        self.assertEqual(target_papers["results"][0]["doi"], "10.1000/target")

        relationships = self.service.query_relationships(
            RelationshipQuery(
                filters=RelationshipFilters(
                    concept_ids=["compound:psilocybin"],
                    domains=["clinical_outcome"],
                )
            )
        )
        self.assertEqual(relationships["meta"]["total"], 1)
        self.assertEqual(
            relationships["results"][0]["object_id"],
            "clinical_entity:major_depressive_disorder",
        )
        target_relationships = self.service.query_relationships(
            RelationshipQuery(
                filters=RelationshipFilters(
                    subject_kinds=["atomic_compound"],
                    object_kinds=["target"],
                    object_labels=["NMDA receptor"],
                )
            )
        )
        self.assertEqual(target_relationships["meta"]["total"], 1)
        self.assertEqual(
            target_relationships["results"][0]["object_id"],
            "target:nmda_receptor",
        )
        self.assertEqual(
            self.service.query_relationships(
                RelationshipQuery(
                    filters=RelationshipFilters(object_kinds=["biomarker_readout"])
                )
            )["meta"]["total"],
            0,
        )

    def test_cursor_is_bound_to_release(self) -> None:
        first = self.service.query_papers(PaperQuery(limit=1))
        pointer = self.resolver.active_pointer
        pointer.write_text(
            json.dumps({"run_id": "test_run", "release_id": "test_run:r2"}),
            encoding="utf-8",
        )
        with self.assertRaises(ReleaseChanged):
            self.service.query_papers(
                PaperQuery(limit=1, cursor=first["meta"]["next_cursor"])
            )

    def test_cursor_rejects_impractically_large_offsets(self) -> None:
        cursor = encode_cursor(release_id="test_run:r1", offset=1_000_001)
        with self.assertRaises(InvalidQuery):
            self.service.query_papers(PaperQuery(cursor=cursor))

    def test_query_models_bound_filter_and_cursor_sizes(self) -> None:
        PaperFilters(paper_ids=["paper:test"] * 100)
        with self.assertRaises(ValidationError):
            PaperFilters(paper_ids=["paper:test"] * 101)
        with self.assertRaises(ValidationError):
            PaperFilters(paper_ids=["x" * 501])
        with self.assertRaises(ValidationError):
            PaperQuery(cursor="x" * 2049)
        with self.assertRaises(InvalidQuery):
            self.service.search_concepts("test", concept_kinds=["kind"] * 101)

    def test_paper_query_and_http_contract(self) -> None:
        paper = self.service.get_paper("10.1000/primary")
        self.assertEqual(paper["data"]["paper_id"], "paper:10.1000/primary")
        self.assertEqual(paper["relationships"][0]["relation_type"], "studied_for_condition")
        self.assertNotIn("findings", paper)

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
                "https://psychedelicskg.com/api/agent-guide.md",
            )
            self.assertEqual(service_index.json()["data_status"], "ready")
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/readyz").json()["status"], "ready")

            response = client.post(
                "/api/v1/papers/query",
                json={
                    "filters": {"paper_types": ["review"]},
                    "limit": 10,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["meta"]["total"], 1)

            relationship_response = client.post(
                "/api/v1/relationships/query",
                json={
                    "filters": {
                        "subject_kinds": ["atomic_compound"],
                        "object_kinds": ["target"],
                    },
                    "limit": 10,
                },
            )
            self.assertEqual(relationship_response.status_code, 200)
            self.assertEqual(relationship_response.json()["meta"]["total"], 1)

            too_large = client.post(
                "/api/v1/papers/query",
                content=b"x" * (256 * 1024 + 1),
                headers={"content-type": "application/json"},
            )
            self.assertEqual(too_large.status_code, 413)

            openapi = client.get("/openapi.json").json()
            self.assertIn("/api/v1/papers/query", openapi["paths"])
            self.assertIn("/api/v1/relationships/query", openapi["paths"])
            self.assertNotIn("/api/v1/findings/query", openapi["paths"])
            self.assertFalse(
                any(path.startswith("/api/v1/downloads") for path in openapi["paths"])
            )
            self.assertEqual(openapi["servers"][0]["url"], "/")
            self.assertEqual(
                openapi["externalDocs"]["url"],
                "https://psychedelicskg.com/api/",
            )
            llms = client.get("/llms.txt", follow_redirects=False)
            self.assertEqual(llms.status_code, 307)
            self.assertEqual(
                llms.headers["location"], "https://psychedelicskg.com/llms.txt"
            )
            self.assertEqual(
                client.get("/api/v1/downloads/tables/papers").status_code,
                404,
            )
            self.assertEqual(client.get("/api/v1/downloads/database").status_code, 404)

    def test_docs_remain_available_while_data_loads(self) -> None:
        missing_root = self.root / "missing"
        settings = Settings(
            data_dir=missing_root,
            active_pointer=missing_root / "graph_payload_active.json",
            query_runs_dir=missing_root / "query_api_runs",
            public_base_url="https://api.example.test",
            cors_origins=(),
            mcp_allowed_hosts=(),
            mcp_allowed_origins=(),
        )
        service = QueryService.from_settings(settings)
        app = create_app(service, settings=settings)
        app.state.data_status = "loading"

        with TestClient(app) as client:
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertEqual(client.get("/healthz").json()["data_status"], "loading")
            readiness = client.get("/readyz")
            self.assertEqual(readiness.status_code, 503)
            query = client.post(
                "/api/v1/papers/query",
                json={"filters": {}, "limit": 10},
            )
            self.assertEqual(query.status_code, 503)
            self.assertEqual(query.headers["retry-after"], "10")


class QueryMcpTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_exposes_narrow_read_only_tools(self) -> None:
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
                    "list_available_filters",
                    "search_concepts",
                    "get_concept",
                    "search_authors",
                    "get_author_papers",
                    "search_papers",
                    "get_paper",
                    "find_relationships",
                },
            )
            _content, structured = await mcp.call_tool(
                "search_papers",
                {"paper_types": ["review"], "limit": 10},
            )
            self.assertEqual(structured["meta"]["total"], 1)
            _content, structured = await mcp.call_tool(
                "find_relationships",
                {
                    "subject_kinds": ["atomic_compound"],
                    "object_kinds": ["target"],
                    "limit": 10,
                },
            )
            self.assertEqual(structured["meta"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
