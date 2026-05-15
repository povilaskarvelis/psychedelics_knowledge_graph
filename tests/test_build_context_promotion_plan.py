import unittest

from pipeline.validate.build_context_promotion_plan import build_promotion_plan


def context(
    *,
    doi: str,
    compound: str = "Psilocybin",
    entity: str = "Major depressive disorder",
    dataset: str = "disorder",
    layer: str = "candidate_context",
    sources: list[str] | None = None,
    flags: dict | None = None,
) -> dict:
    base_flags = {
        "has_seed_or_discovery_context": False,
        "has_paper_library_context": False,
        "has_triage_matched_context": False,
        "has_triage_synthesized_context": False,
        "has_llm_verified_context": False,
        "has_claim_stub": False,
        "has_curated_claim": False,
        "has_exploratory_claim": False,
        "has_known_study_context": False,
        "possible_acronym_collision": False,
        "needs_revalidation": True,
    }
    if flags:
        base_flags.update(flags)
    return {
        "context_id": f"{dataset}|{doi}|{compound.lower()}|{entity.lower()}",
        "dataset": dataset,
        "doi": doi,
        "compound": compound,
        "entity": entity,
        "entity_type": "indication" if dataset == "disorder" else "target",
        "context_sources": sources or [],
        "provenance": [
            {
                "source_artifact": "data/processed/example.json",
                "context_source": source,
            }
            for source in sources or []
        ],
        "flags": base_flags,
        "verification_layer": layer,
        "revalidation_status": "verified_existing" if layer == "verified_evidence" else "needs_revalidation",
    }


class BuildContextPromotionPlanTest(unittest.TestCase):
    def test_classifies_contexts_into_next_action_queues(self) -> None:
        contexts = [
            context(
                doi="10.example/verified",
                layer="verified_evidence",
                sources=["curated_claim"],
                flags={"has_curated_claim": True, "needs_revalidation": False},
            ),
            context(
                doi="10.example/stub",
                sources=["claim_stub"],
                flags={"has_claim_stub": True},
            ),
            context(
                doi="10.example/screened-pdf",
                layer="screened_context",
                sources=["llm_verified_context"],
                flags={"has_llm_verified_context": True},
            ),
            context(
                doi="10.example/noise",
                compound="DMT",
                sources=["curated_claim"],
                flags={"has_curated_claim": True, "possible_acronym_collision": True},
            ),
        ]
        papers = [
            {
                "doi": "10.example/screened-pdf",
                "study_title": "A supported full text paper",
                "flags": {"has_local_pdf": True},
                "metadata": {"library_status": "downloaded"},
            }
        ]

        plan = build_promotion_plan(contexts, papers)
        stages = {row["doi"]: row["promotion_stage"] for row in plan["records"]}
        public_ready = {row["doi"]: row["public_kg_ready"] for row in plan["records"]}

        self.assertEqual(stages["10.example/verified"], "verified_evidence")
        self.assertEqual(stages["10.example/stub"], "curation_review")
        self.assertEqual(stages["10.example/screened-pdf"], "full_text_extraction_ready")
        self.assertEqual(stages["10.example/noise"], "noise_review")
        self.assertTrue(public_ready["10.example/verified"])
        self.assertFalse(public_ready["10.example/noise"])

        self.assertEqual(plan["summary"]["public_kg_ready_contexts"], 1)
        self.assertEqual(plan["summary"]["contexts_requiring_work"], 3)
        self.assertEqual(plan["summary"]["promotion_stage_counts"]["curation_review"], 1)

    def test_edge_rollup_tracks_best_available_edge_status(self) -> None:
        contexts = [
            context(
                doi="10.example/screened",
                layer="screened_context",
                sources=["llm_verified_context"],
                flags={"has_llm_verified_context": True},
            ),
            context(
                doi="10.example/candidate",
                sources=["queue_discovered_context"],
                flags={"has_seed_or_discovery_context": True},
            ),
        ]

        plan = build_promotion_plan(contexts, papers=[])

        self.assertEqual(plan["summary"]["edge_count"], 1)
        edge = plan["edge_rollup"][0]
        self.assertEqual(edge["edge_status"], "screened_edge_candidate")
        self.assertEqual(edge["context_count"], 2)
        self.assertEqual(edge["screened_contexts"], 1)
        self.assertEqual(edge["candidate_contexts"], 1)


if __name__ == "__main__":
    unittest.main()
