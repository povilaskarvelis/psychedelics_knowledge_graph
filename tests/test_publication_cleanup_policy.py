"""Regression checks for publication eligibility, distinct from Luna topic scope."""
import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.fulltext.audit_deterministic_repository_formats import classify_record
from pipeline.fulltext.apply_post_retrieval_publication_format_screen import build_arg_parser, run, candidate_updates
from pipeline.fulltext.register_retrieved_pdf_exclusions import audit_exclusions
from pipeline.review.run_deterministic_prescreen import publication_cleanup_exclusion_decision
from pipeline.review.run_domain_routing import merged_routing_metadata, selected_records


def test_named_educational_series_does_not_blacklist_a_publisher():
    for doi in ['10.64239/pi-capst0804', '10.64239/pi-vl11508']:
        row = {'study_doi': doi, 'study_title': 'Ketamine treatment', 'publication_type': 'report'}
        assert publication_cleanup_exclusion_decision(row)['action'] == 'exclude_non_evidence_artifact'
    for doi in ['10.64239/research123', '10.64239/pi-capst0804.s1', '10.4172/2155-6105.s9-002']:
        assert publication_cleanup_exclusion_decision({'study_doi': doi, 'publication_type': 'Journal Article'}) is None


def test_empirical_letter_is_protected_but_a_meeting_case_is_excluded():
    row = {'study_doi': '10.example/case', 'doi': '10.example/case',
           'study_title': 'A ketamine case report', 'publication_type': 'Case Reports | Letter'}
    assert publication_cleanup_exclusion_decision(row) is None
    assert classify_record(row) is None
    row['publication_type'] = 'Case Reports | Letter | Conference Abstract'
    assert publication_cleanup_exclusion_decision(row) is not None
    assert classify_record(row)['publication_format'] == 'conference_abstract'


def test_country_publisher_and_single_supplement_page_are_not_exclusions():
    row = {'study_doi': '10.example/journal.suppl.42', 'study_journal': 'Japanese Research Journal',
           'publisher': 'OMICS International', 'language': '', 'publication_type': 'Journal Article', 'journal_pages': 'S42'}
    assert publication_cleanup_exclusion_decision(row) is None
    row['publication_type'] = 'Conference Abstract'
    assert publication_cleanup_exclusion_decision(row) is not None


def test_registration_retains_specific_review_reason_and_ignores_access_failures(tmp_path):
    path = tmp_path / 'review.csv'
    pd.DataFrame([
        {'doi': '10.example/chapter', 'recommended_action': 'exclude_publication_format', 'publication_format': 'book_chapter',
         'format_evidence': 'Primary publisher chapter title page.', 'reason': 'Verified chapter, not the unrelated journal report.'},
        {'doi': '10.example/gate', 'recommended_action': 'retry_download', 'publication_format': 'non_english_article'},
        {'doi': '10.example/unknown', 'recommended_action': 'exclude_publication_format', 'publication_format': 'paywalled'},
    ]).to_csv(path, index=False)
    rows = audit_exclusions(path)
    assert len(rows) == 1
    assert rows[0]['reason'] == 'Verified chapter, not the unrelated journal report.'
    assert rows[0]['evidence'] == 'Primary publisher chapter title page.'


def test_confirmed_exclusions_filter_all_extraction_queues_and_preserve_model_history(tmp_path):
    candidate = tmp_path / 'candidate.parquet'
    pd.DataFrame([{'doi': '10.example/drop', 'retained_for_extraction_candidate': True},
                  {'doi': '10.example/keep', 'retained_for_extraction_candidate': True},
                  {'doi': '10.example/inactive', 'retained_for_extraction_candidate': False}]).to_parquet(candidate)
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps({'records': [{'doi': '10.example/drop', 'decision': 'exclude',
        'publication_format': 'non_english_article', 'evidence': 'Verified original language.'}]}))
    routes = tmp_path / 'routes.parquet'
    pd.DataFrame([{'doi': '10.example/drop'}, {'doi': '10.example/keep'},
                  {'doi': '10.example/inactive'}]).to_parquet(routes)
    model = tmp_path / 'v5.parquet'
    model.write_bytes(routes.read_bytes()); model_before = model.read_bytes()
    queues = [tmp_path / (name + '.jsonl') for name in ['primary', 'review', 'meta']]
    for q in queues:
        q.write_text(json.dumps({'study_doi': '10.example/drop'}) + '\n' + json.dumps({'study_doi': '10.example/keep'}) + '\n')
    args = argparse.Namespace(ledger=str(ledger), candidate_table=str(candidate), decisions_table=str(tmp_path/'decisions.parquet'),
        domain_routing_table='', extraction_routes_table=str(routes), extraction_tasks_jsonl=str(queues[0]),
        review_tasks_jsonl=str(queues[1]), meta_tasks_jsonl=str(queues[2]), report=str(tmp_path/'report.json'),
        run_id='test', doi=['10.example/drop'], apply=True)
    run(args)
    result = pd.read_parquet(candidate).set_index('doi')
    assert not bool(result.at['10.example/drop', 'retained_for_extraction_candidate'])
    assert bool(result.at['10.example/keep', 'retained_for_extraction_candidate'])
    assert result.at['10.example/drop', 'pipeline_exclusion_stage'] == 'post_retrieval_eligibility'
    assert set(pd.read_parquet(routes).doi) == {'10.example/keep', '10.example/inactive'}
    assert not bool(result.at['10.example/inactive', 'retained_for_extraction_candidate'])
    assert all([json.loads(line)['study_doi'] for line in q.read_text().splitlines()] == ['10.example/keep'] for q in queues)
    assert model.read_bytes() == model_before
    assert build_arg_parser().parse_args([]).domain_routing_table == ''


def test_retain_does_not_resurrect_model_exclusion():
    rows = candidate_updates(pd.DataFrame([{'doi': '10.example/out', 'decision': 'retain'}]))
    assert pd.isna(rows.iloc[0]['retained_for_extraction_candidate'])


def test_future_screening_skips_known_record_exclusions_without_changing_prompt():
    candidate = pd.DataFrame([{'doi': '10.example/drop', 'post_retrieval_decision': 'exclude'},
                              {'doi': '10.example/keep', 'post_retrieval_decision': ''}])
    cache = pd.DataFrame([{'doi': '10.example/keep', 'post_retrieval_decision': 'exclude'}])
    meta = merged_routing_metadata(candidate, cache)
    prescreen = pd.DataFrame([{'doi': d, 'prescreen_decision': 'retain'} for d in candidate.doi])
    result = selected_records(meta, prescreen, scoped_dois=set(), limit=0, completed=set())
    assert [r['doi'] for r in result] == ['10.example/keep']
    assert 'post_retrieval_decision' not in result[0]
