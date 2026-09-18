import pandas as pd
import pytest
import json

from pipeline.validate.audit_author_identities import audit, name_parts


def test_unicode_hyphens_and_diacritics_are_review_candidates():
    assert name_parts('Robin L. Carhart‐Harris') == ['robin', 'l', 'carhart-harris']
    assert name_parts('José Example') == ['jose', 'example']


def test_audit_flags_splits_and_possible_false_merges_without_changing_tables(tmp_path):
    kg = tmp_path / 'kg'
    kg.mkdir()
    authors = pd.DataFrame([
        dict(author_id='a', display_name='Robin Carhart-Harris', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
        dict(author_id='b', display_name='Robin L. Carhart‐Harris', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
    ])
    links = pd.DataFrame([
        dict(paper_id='p', author_id='a', display_name='Robin Carhart-Harris', author_position=1, identity_confidence='orcid', openalex_author_id='A1'),
        dict(paper_id='p', author_id='a', display_name='Different Person', author_position=2, identity_confidence='orcid', openalex_author_id='A2'),
        dict(paper_id='q', author_id='b', display_name='Robin L. Carhart‐Harris', author_position=1, identity_confidence='openalex_author_id', openalex_author_id='A3'),
    ])
    authors.to_parquet(kg / 'authors.parquet')
    links.to_parquet(kg / 'paper_authors.parquet')
    pd.DataFrame({'paper_id': ['p', 'q']}).to_parquet(kg / 'papers.parquet')
    before = (kg / 'paper_authors.parquet').read_bytes()
    report = audit(kg, tmp_path / 'audit')
    assert report['candidate_name_groups'] == 1
    assert report['candidate_identities'] == 2
    assert report['papers_with_repeated_authors'] == 1
    assert report['repeated_identity_groups_with_different_names'] == 1
    assert report['duplicate_position_rows'] == 0
    assert (kg / 'paper_authors.parquet').read_bytes() == before


def test_baseline_audit_isolates_new_shared_coauthor_collision(tmp_path):
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    baseline.mkdir()
    candidate.mkdir()
    base_authors = pd.DataFrame([
        dict(author_id='established', display_name='Jeremy P. Harris', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
        dict(author_id='colleague-1', display_name='First Colleague', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
        dict(author_id='colleague-2', display_name='Second Colleague', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
    ])
    base_links = pd.DataFrame([
        dict(paper_id='old', author_id='established', display_name='Jeremy P. Harris', author_position=1, identity_confidence='openalex_author_id', openalex_author_id='A1'),
        dict(paper_id='old', author_id='colleague-1', display_name='First Colleague', author_position=2, identity_confidence='openalex_author_id', openalex_author_id='C1'),
        dict(paper_id='old', author_id='colleague-2', display_name='Second Colleague', author_position=3, identity_confidence='openalex_author_id', openalex_author_id='C2'),
    ])
    base_papers = pd.DataFrame([dict(paper_id='old', title='Old paper')])
    base_authors.to_parquet(baseline / 'authors.parquet')
    base_links.to_parquet(baseline / 'paper_authors.parquet')
    base_papers.to_parquet(baseline / 'papers.parquet')

    candidate_authors = pd.concat([
        base_authors,
        pd.DataFrame([dict(author_id='split', display_name='Jeremy P. Harris', orcid='', paper_count=1, identity_confidence='openalex_author_id')]),
    ], ignore_index=True)
    candidate_links = pd.concat([
        base_links,
        pd.DataFrame([
            dict(paper_id='new', author_id='split', display_name='Jeremy P. Harris', author_position=1, identity_confidence='openalex_author_id', openalex_author_id='A2'),
            dict(paper_id='new', author_id='colleague-1', display_name='First Colleague', author_position=2, identity_confidence='openalex_author_id', openalex_author_id='C1'),
            dict(paper_id='new', author_id='colleague-2', display_name='Second Colleague', author_position=3, identity_confidence='openalex_author_id', openalex_author_id='C2'),
        ]),
    ], ignore_index=True)
    candidate_papers = pd.concat([
        base_papers,
        pd.DataFrame([dict(paper_id='new', title='New paper')]),
    ], ignore_index=True)
    candidate_authors.to_parquet(candidate / 'authors.parquet')
    candidate_links.to_parquet(candidate / 'paper_authors.parquet')
    candidate_papers.to_parquet(candidate / 'papers.parquet')

    report = audit(candidate, tmp_path / 'audit', baseline_dir=baseline)
    assert report['new_exact_name_collision_groups'] == 1
    assert report['new_priority_identity_review_groups'] == 1
    queue = pd.read_json(tmp_path / 'audit' / 'new_priority_name_candidates.json')
    assert queue.iloc[0]['canonical_name'] == 'jeremy p harris'
    assert queue.iloc[0]['max_shared_coauthors'] == 2


def test_baseline_audit_suppresses_reviewed_distinct_people(tmp_path):
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    baseline.mkdir()
    candidate.mkdir()
    base_authors = pd.DataFrame([
        dict(author_id='old', display_name='Wei Zhang', orcid='0000-0001-1111-1111', paper_count=1, identity_confidence='orcid'),
        dict(author_id='colleague-1', display_name='First Colleague', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
        dict(author_id='colleague-2', display_name='Second Colleague', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
    ])
    base_links = pd.DataFrame([
        dict(paper_id='old-paper', author_id='old', display_name='Wei Zhang', author_position=1, identity_confidence='orcid', openalex_author_id='A1'),
        dict(paper_id='old-paper', author_id='colleague-1', display_name='First Colleague', author_position=2, identity_confidence='openalex_author_id', openalex_author_id='C1'),
        dict(paper_id='old-paper', author_id='colleague-2', display_name='Second Colleague', author_position=3, identity_confidence='openalex_author_id', openalex_author_id='C2'),
    ])
    base_authors.to_parquet(baseline / 'authors.parquet')
    base_links.to_parquet(baseline / 'paper_authors.parquet')
    pd.DataFrame([dict(paper_id='old-paper', title='Old')]).to_parquet(baseline / 'papers.parquet')
    pd.concat([base_authors, pd.DataFrame([
        dict(author_id='new', display_name='Wei Zhang', orcid='0000-0002-2222-2222', paper_count=1, identity_confidence='orcid'),
    ])], ignore_index=True).to_parquet(candidate / 'authors.parquet')
    pd.concat([base_links, pd.DataFrame([
        dict(paper_id='new-paper', author_id='new', display_name='Wei Zhang', author_position=1, identity_confidence='orcid', openalex_author_id='A2'),
        dict(paper_id='new-paper', author_id='colleague-1', display_name='First Colleague', author_position=2, identity_confidence='openalex_author_id', openalex_author_id='C1'),
        dict(paper_id='new-paper', author_id='colleague-2', display_name='Second Colleague', author_position=3, identity_confidence='openalex_author_id', openalex_author_id='C2'),
    ])], ignore_index=True).to_parquet(candidate / 'paper_authors.parquet')
    pd.DataFrame([
        dict(paper_id='old-paper', title='Old'), dict(paper_id='new-paper', title='New'),
    ]).to_parquet(candidate / 'papers.parquet')
    overrides = tmp_path / 'overrides.json'
    overrides.write_text(json.dumps({'distinct_identity_reviews': [{
        'review_id': 'different-wei-zhang',
        'canonical_name': 'Wei Zhang',
        'identity_ids': ['old', 'new'],
        'decision': 'different_people',
        'reason': 'Institutional profiles show different departments and publication histories.',
        'sources': ['https://example.org/evidence'],
        'reviewed_at': '2026-09-17',
        'reviewed_by': 'test',
    }]}))

    report = audit(
        candidate, tmp_path / 'audit', baseline_dir=baseline, identity_overrides=overrides
    )

    assert report['new_exact_name_collision_groups'] == 0
    assert report['new_priority_identity_review_groups'] == 0
    assert report['reviewed_distinct_name_groups'] == 1


def test_baseline_audit_can_fail_on_new_structural_authorship_error(tmp_path):
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    baseline.mkdir()
    candidate.mkdir()
    authors = pd.DataFrame([
        dict(author_id='a', display_name='Ada Example', orcid='', paper_count=1, identity_confidence='openalex_author_id'),
    ])
    base_links = pd.DataFrame([
        dict(paper_id='old', author_id='a', display_name='Ada Example', author_position=1, identity_confidence='openalex_author_id', openalex_author_id='A1'),
    ])
    authors.to_parquet(baseline / 'authors.parquet')
    base_links.to_parquet(baseline / 'paper_authors.parquet')
    pd.DataFrame([dict(paper_id='old', title='Old')]).to_parquet(baseline / 'papers.parquet')
    authors.to_parquet(candidate / 'authors.parquet')
    pd.concat([
        base_links,
        pd.DataFrame([dict(paper_id='new', author_id='a', display_name='Ada Example', author_position=1, identity_confidence='openalex_author_id', openalex_author_id='A1')]),
    ]).to_parquet(candidate / 'paper_authors.parquet')
    pd.DataFrame([dict(paper_id='old', title='Old')]).to_parquet(candidate / 'papers.parquet')

    with pytest.raises(ValueError, match='structural errors'):
        audit(
            candidate,
            tmp_path / 'audit',
            baseline_dir=baseline,
            fail_on_new_integrity_errors=True,
        )


def test_repeated_publication_byline_is_reviewed_without_failing_build(tmp_path):
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    baseline.mkdir()
    candidate.mkdir()
    authors = pd.DataFrame([
        dict(author_id='a', display_name='Ada Example', orcid='', paper_count=1, identity_confidence='name_only'),
    ])
    papers = pd.DataFrame([dict(paper_id='p', title='Publisher repeats panel member')])
    empty_links = pd.DataFrame(columns=[
        'paper_id', 'author_id', 'display_name', 'author_position',
        'identity_confidence', 'openalex_author_id',
    ])
    repeated_links = pd.DataFrame([
        dict(paper_id='p', author_id='a', display_name='Ada Example', author_position=1, identity_confidence='name_only', openalex_author_id=''),
        dict(paper_id='p', author_id='a', display_name='Ada Example', author_position=2, identity_confidence='name_only', openalex_author_id=''),
    ])
    authors.to_parquet(baseline / 'authors.parquet')
    empty_links.to_parquet(baseline / 'paper_authors.parquet')
    papers.to_parquet(baseline / 'papers.parquet')
    authors.to_parquet(candidate / 'authors.parquet')
    repeated_links.to_parquet(candidate / 'paper_authors.parquet')
    papers.to_parquet(candidate / 'papers.parquet')

    report = audit(
        candidate,
        tmp_path / 'audit',
        baseline_dir=baseline,
        fail_on_new_integrity_errors=True,
    )
    assert report['new_repeated_identity_groups'] == 1
    assert report['new_repeated_identity_groups_with_different_names'] == 0
