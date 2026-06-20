import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline.extract.export_packet_profile_queues import (
    build_report,
    canonical_section_selection_strategy,
    queue_rows,
    write_queue_files,
)


def make_args(**overrides: object) -> SimpleNamespace:
    args = {
        "only_retained": True,
        "route_action": [],
        "packet_profile": [],
        "prompt_profile": [],
        "schema_profile": [],
        "domain_route": [],
    }
    args.update(overrides)
    return SimpleNamespace(**args)


def route_row(**overrides: object) -> dict:
    row = {
        "route_id": "route-primary-clinical",
        "doi": "10.1000/primary",
        "retained_for_extraction_candidate": True,
        "study_title": "Primary psilocybin study",
        "study_year": "2025",
        "source_family": "primary_or_unclear",
        "source_type": "primary_or_unclear",
        "domain_route": "clinical_outcome",
        "access_tier": "full_text_available",
        "route_action": "extract_from_full_text",
        "prompt_profile": "primary_clinical",
        "schema_profile": "primary_evidence_schema",
    }
    row.update(overrides)
    return row


class ExportPacketProfileQueuesTest(unittest.TestCase):
    def test_queue_rows_groups_dois_by_expected_section_selection_strategy(self) -> None:
        rows = queue_rows(
            [
                route_row(),
                route_row(
                    route_id="route-primary-safety",
                    domain_route="safety_tolerability",
                    prompt_profile="primary_safety",
                ),
                route_row(
                    route_id="route-meta",
                    doi="10.1000/meta",
                    source_family="secondary_literature",
                    source_type="meta_analysis",
                    domain_route="clinical_outcome",
                    prompt_profile="secondary_meta_analysis",
                    schema_profile="synthesis_evidence_schema",
                ),
                route_row(
                    route_id="route-review",
                    doi="10.1000/review",
                    source_family="secondary_literature",
                    source_type="review",
                    domain_route="general_topic_coverage",
                    prompt_profile="secondary_narrative_review",
                    schema_profile="review_coverage_schema",
                ),
                route_row(
                    route_id="route-abstract",
                    doi="10.1000/abstract",
                    access_tier="abstract_only",
                    route_action="extract_from_abstract_only",
                ),
                route_row(
                    route_id="route-terminal",
                    doi="10.1000/context",
                    domain_route="context_only",
                    prompt_profile="context_only_or_skip",
                    schema_profile="context_only_schema",
                ),
            ],
            make_args(),
        )

        groups = {(row["section_selection_strategy"], row["doi"]): row for row in rows}
        self.assertIn(("primary_study", "10.1000/primary"), groups)
        self.assertIn(("meta_analysis", "10.1000/meta"), groups)
        self.assertIn(("review", "10.1000/review"), groups)
        self.assertNotIn(("primary_study", "10.1000/abstract"), groups)
        self.assertEqual(len(groups), 3)
        self.assertIn("route-primary-clinical", groups[("primary_study", "10.1000/primary")]["route_ids"])
        self.assertIn("route-primary-safety", groups[("primary_study", "10.1000/primary")]["route_ids"])

    def test_write_queue_files_and_report_use_strategy_names(self) -> None:
        rows = queue_rows([route_row()], make_args(packet_profile=["primary_empirical"]))
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            outputs = write_queue_files(rows, out_dir)
            report = build_report(rows, route_table=Path("/tmp/routes.parquet"), out_dir=out_dir, queue_outputs=outputs)

            primary_queue = out_dir / "primary_study.txt"

            self.assertTrue(primary_queue.exists())
            self.assertIn("10.1000/primary", primary_queue.read_text(encoding="utf-8"))
            self.assertEqual(report["by_section_selection_strategy"], {"primary_study": 1})
            self.assertEqual(report["by_packet_profile"], {"primary_empirical": 1})
            self.assertEqual(outputs["primary_study"]["doi_file"], str(primary_queue))
            self.assertNotIn("build_command", outputs["primary_study"])

    def test_standard_section_selection_strategy_aliases_map_to_internal_ids(self) -> None:
        self.assertEqual(canonical_section_selection_strategy("primary_study"), "primary_empirical")
        self.assertEqual(canonical_section_selection_strategy("meta_analysis"), "secondary_synthesis")
        self.assertEqual(canonical_section_selection_strategy("review"), "review_coverage")


if __name__ == "__main__":
    unittest.main()
