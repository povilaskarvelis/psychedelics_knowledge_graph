"""An accepted scholarly analysis shares Reviews, without changing its genre or screen."""
from pathlib import Path
import pandas as pd
import pytest
from pipeline.extract.build_extraction_routes import build_route_rows
from pipeline.extract.build_review_relationship_tasks import production_cohort
from pipeline.fulltext.audit_deterministic_repository_formats import classify_record
from pipeline.review.run_deterministic_prescreen import publication_cleanup_exclusion_decision
from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import paper_type_for

@pytest.mark.parametrize('genre',['commentary_editorial','other_non_primary'])
def test_accepted_analysis_is_ready_single_review_route_and_preserves_raw_screen(genre):
    doi='10.1000/analysis'
    meta=pd.DataFrame([{'doi':doi,'study_title':'Psychedelic research analysis','abstract':'This theoretical article discusses psychedelic research.','publication_type':'Journal Article'}])
    pre=pd.DataFrame([{'doi':doi,'prescreen_decision':'retain','retained_for_extraction_candidate':True}])
    lit=pd.DataFrame([{'doi':doi,'source_family':'non_primary_publication','source_type':genre,'non_primary_flags':genre}])
    screen=pd.DataFrame([{'doi':doi,'paper_type_group':'non_primary_publication','paper_type':genre,'screening_decision':'include_in_scope','screening_reason':'Substantive analysis of psychedelic science.','model':'gpt-6-luna','domain_route':'context_only'}])
    original=screen.copy(deep=True)
    routes=build_route_rows(meta,pre,lit,screen,fulltext_dir=Path('/tmp/no-analysis-source'),generated_at_utc='2026-10-22')
    assert len(routes)==1
    r=routes[0]
    assert r['source_family']=='secondary_literature'
    assert r['source_type']==genre
    assert r['primary_secondary_source_type']==genre
    assert r['retained_for_extraction_candidate'] is True
    assert r['route_action']=='extract_from_abstract_only'
    pd.testing.assert_frame_equal(screen,original)
    cohort,_=production_cohort([{'doi':doi,'retained_for_extraction_candidate':True,'primary_secondary_source_type':genre,'extraction_route_status':'ready_for_abstract_extraction','extraction_domain_screening_decisions':'include_in_scope'}])
    assert cohort[0]['review_type']==genre
    assert paper_type_for({'paper_metadata':{'review_type':genre}})==genre

@pytest.mark.parametrize('decision',['exclude_out_of_scope',''])
def test_rejected_or_unscreened_analysis_cannot_enter_review_builder(decision):
    cohort,report=production_cohort([{'doi':'10.1000/rejected','retained_for_extraction_candidate':True,'primary_secondary_source_type':'other_non_primary','extraction_route_status':'ready_for_abstract_extraction','extraction_domain_screening_decisions':decision}])
    assert not cohort
    assert report['skipped']=={'analysis_without_positive_screen':1}

@pytest.mark.parametrize('publication_type',['Editorial','Comment','Letter'])
def test_accepted_analysis_genre_does_not_override_positive_scope(publication_type):
    row={'doi':'10.1000/analysis','study_doi':'10.1000/analysis','study_title':'Psychedelic science','abstract':'This theoretical article discusses psychedelic science.','publication_type':publication_type,'paper_type':'commentary_editorial','screening_decision':'include_in_scope','language':'en'}
    assert classify_record(row) is None
    assert publication_cleanup_exclusion_decision(row) is None
    row['publication_type']=publication_type+'|Conference Abstract'
    assert classify_record(row)['publication_format']=='conference_abstract'
    assert publication_cleanup_exclusion_decision(row) is not None
    row['publication_type']=publication_type
    row['language']='de'
    assert publication_cleanup_exclusion_decision(row) is not None


def test_analysis_exception_requires_saved_positive_screen():
    row={'doi':'10.1000/analysis','study_doi':'10.1000/analysis','study_title':'Editorial','publication_type':'Editorial','paper_type':'commentary_editorial'}
    assert classify_record(row) is not None
    assert publication_cleanup_exclusion_decision(row) is not None

@pytest.mark.parametrize('genre',['commentary_editorial','other_non_primary'])
def test_analysis_uses_existing_review_normalization_and_design_tags(genre):
    from pipeline.kg.build_evidence_tables import is_review_row, review_design_category
    assert is_review_row({'paper_type':genre})
    assert review_design_category({'paper_type':genre},{'review_design':'Conceptual and theoretical analysis'})=='conceptual_or_theoretical_review'
