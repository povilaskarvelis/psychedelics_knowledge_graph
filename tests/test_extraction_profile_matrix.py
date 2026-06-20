import json

from pipeline.extract.extraction_profile_matrix import (
    PAPER_TYPE_PROMPT_PATHS,
    PRIMARY_PROMPT_BY_DOMAIN,
    PAPER_TYPE_PRIMARY,
    TEXT_DEPTH_ABSTRACT,
    TEXT_DEPTH_ARTICLE,
    primary_spec_for_domain,
    primary_spec_for_prompt,
    spec_for_route,
    text_depth_from_access,
)


def test_primary_matrix_has_prompt_schema_and_depth_files_for_each_domain() -> None:
    for domain, prompt_profile in PRIMARY_PROMPT_BY_DOMAIN.items():
        article_spec = primary_spec_for_domain(domain, text_depth=TEXT_DEPTH_ARTICLE)
        abstract_spec = primary_spec_for_domain(domain, text_depth=TEXT_DEPTH_ABSTRACT)
        prompt_spec = primary_spec_for_prompt(prompt_profile)

        assert article_spec.prompt_path.exists()
        assert article_spec.schema_path.exists()
        assert article_spec.prompt_path == PAPER_TYPE_PROMPT_PATHS[(PAPER_TYPE_PRIMARY, TEXT_DEPTH_ARTICLE)]
        assert abstract_spec.prompt_path == PAPER_TYPE_PROMPT_PATHS[(PAPER_TYPE_PRIMARY, TEXT_DEPTH_ABSTRACT)]
        assert article_spec.depth_prompt_path is None
        assert abstract_spec.depth_prompt_path is None
        assert prompt_spec.domain_route == domain

        schema = json.loads(article_spec.schema_path.read_text(encoding="utf-8"))
        assert schema["properties"]["domain_route"]["const"] == domain
        assert schema["properties"]["paper_type"]["enum"] == ["primary_study"]
        assert schema["properties"]["text_depth"]["enum"] == ["article_text", "abstract_only"]


def test_spec_for_route_resolves_primary_meta_review_and_no_extraction() -> None:
    primary = spec_for_route(domain_route="molecular_target", paper_type="primary_study", text_depth="abstract_only")
    meta = spec_for_route(domain_route="clinical_outcome", paper_type="meta_analysis", text_depth="article_text")
    review = spec_for_route(domain_route="brain_system", paper_type="review", text_depth="abstract_only")
    skipped = spec_for_route(domain_route="context_only", paper_type="context", text_depth="abstract_only")

    assert primary.prompt_profile == "primary_molecular_target"
    assert primary.schema_path.name == "molecular_target.schema.json"
    assert primary.prompt_path.name == "primary_abstract_only.md"
    assert primary.depth_prompt_path is None
    assert meta.schema_profile == "synthesis_evidence_schema"
    assert meta.prompt_path.name == "meta_analysis_article_text.md"
    assert review.schema_profile == "review_coverage_schema"
    assert review.prompt_path.name == "review_abstract_only.md"
    assert skipped.extract is False


def test_legacy_full_text_access_labels_map_to_article_text() -> None:
    assert text_depth_from_access("full_text_seen") == TEXT_DEPTH_ARTICLE
    assert text_depth_from_access("full_text_available") == TEXT_DEPTH_ARTICLE
    assert text_depth_from_access("full_text") == TEXT_DEPTH_ARTICLE
