import argparse
from pathlib import Path

from pipeline.extract.run_review_relationship_extraction import (
    ABSTRACT_PROMPT,
    BUNDLE_SCHEMA,
    FULL_TEXT_PROMPT,
    archive_run_inputs,
    bundle_semantic_errors,
    inject_fixed_fields,
)


def test_archive_run_inputs_preserves_exact_prompts_schema_and_tasks(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('{"task_id":"one"}\n', encoding="utf-8")
    args = argparse.Namespace(
        run_id="snapshot-test",
        model="test-model",
        thinking_budget=0,
        max_output_tokens=50,
        full_text_prompt=FULL_TEXT_PROMPT,
        abstract_prompt=ABSTRACT_PROMPT,
        bundle_schema=BUNDLE_SCHEMA,
        overwrite=False,
    )

    manifest = archive_run_inputs(tmp_path / "run", tasks, args)

    assert len(manifest["artifacts"]) == 4
    assert (tmp_path / "run/input_snapshot/prompts/full_text_extraction.md").read_text() == FULL_TEXT_PROMPT.read_text()
    assert (tmp_path / "run/input_snapshot/prompts/abstract_extraction.md").read_text() == ABSTRACT_PROMPT.read_text()
    assert (tmp_path / "run/input_snapshot/schemas/review_relationships_v2.bundle.schema.json").read_text() == BUNDLE_SCHEMA.read_text()
    assert (tmp_path / "run/input_snapshot/tasks/tasks.jsonl").read_text() == tasks.read_text()


def test_bundle_semantics_require_major_aspect_coverage() -> None:
    bundle = {
        "paper_frame": {
            "major_aspects": [
                {"aspect_id": "efficacy", "importance": "paper_defining"},
                {"aspect_id": "safety", "importance": "major_supporting"},
            ]
        },
        "relationships": [
            {
                "item_id": "rel_efficacy",
                "source_item_ids": ["rel_efficacy"],
                "covers_major_aspect_ids": ["efficacy"],
                "paper_prominence": "paper_defining",
                "graph_eligibility": "main_graph",
                "centrality_basis": ["review_conclusion"],
            }
        ],
    }

    errors = bundle_semantic_errors(bundle)

    assert "major_aspect_without_matching_relationship:safety:major_supporting" in errors
    assert "major_aspect_without_matching_relationship:efficacy:paper_defining" not in errors


def test_bundle_semantics_keep_detail_out_of_main_graph() -> None:
    bundle = {
        "paper_frame": {"major_aspects": [{"aspect_id": "main", "importance": "paper_defining"}]},
        "relationships": [
            {
                "item_id": "main",
                "source_item_ids": ["main"],
                "covers_major_aspect_ids": ["main"],
                "paper_prominence": "paper_defining",
                "graph_eligibility": "main_graph",
                "centrality_basis": ["stated_objective"],
            },
            {
                "item_id": "detail",
                "source_item_ids": ["detail"],
                "covers_major_aspect_ids": [],
                "paper_prominence": "secondary_context",
                "graph_eligibility": "main_graph",
                "centrality_basis": ["dedicated_section"],
            },
        ],
    }

    assert "main_graph_not_central:detail" in bundle_semantic_errors(bundle)


def test_bundle_semantics_check_source_item_identity() -> None:
    bundle = {
        "paper_frame": {"major_aspects": [{"aspect_id": "main", "importance": "paper_defining"}]},
        "relationships": [
            {
                "item_id": "rel_1",
                "source_item_ids": ["different"],
                "covers_major_aspect_ids": ["main"],
                "paper_prominence": "paper_defining",
                "graph_eligibility": "main_graph",
                "centrality_basis": ["review_conclusion"],
            }
        ],
    }

    assert "source_item_ids_do_not_match_item_id:rel_1" in bundle_semantic_errors(bundle)


def test_fixed_fields_keep_source_depth_authoritative() -> None:
    result = {
        "schema_version": "wrong",
        "source_depth": "abstract_only",
        "paper_frame": {"source_completeness": "abstract_only"},
    }
    fixed = inject_fixed_fields(result, {"text_depth": "article_text"})
    assert fixed["schema_version"] == "review_relationship_bundle_v2"
    assert fixed["source_depth"] == "article_text"
    assert fixed["paper_frame"]["source_completeness"] == "article_text"
