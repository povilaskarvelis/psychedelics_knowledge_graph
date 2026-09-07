import pandas as pd

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
