"""Trusted metadata transport is distinct from scientific extraction quality."""
import copy
import pytest
from pipeline.validate.primary_refinement_experiment import apply_trusted_identity_envelope
from pipeline.extract.run_route_extraction import OutputQualityError

@pytest.fixture
def task():
    return {'task_id': 'task-one', 'route_id': 'route-one', 'study_doi': '10.1111/j.1476-5381.1995.tb15037.x',
            'extraction_contract': {'prompt_profile': 'primary_safety', 'schema_profile': 'primary_evidence_schema', 'domain_route': 'safety_tolerability'},
            'route_context': {'source_type': 'primary', 'domain_route': 'safety_tolerability'},
            'text_source': {'mode': 'full_text_packet', 'access_level': 'full_text_seen'}}

def test_echo_typo_repaired_without_changing_items_or_experimental_schema(task):
    result = {'schema_version': 'primary_safety_v2_observation', 'task_id': 'task-one', 'route_id': 'route-one',
              'study_doi': '10.1111/j.1476-5385.1995.tb15037.x', 'domain_route': 'safety_tolerability',
              'paper_type': 'primary_study', 'text_depth': 'full_text', 'source_type': 'primary',
              'warnings': [], 'items': [{'finding_summary': 'Body temperature increased.'}]}
    original = copy.deepcopy(result)
    fixed, metadata = apply_trusted_identity_envelope(result, task)
    assert result == original
    assert fixed['items'] == original['items']
    assert fixed['schema_version'] == original['schema_version']
    assert fixed['study_doi'] == task['study_doi']
    assert any(m['field'] == 'study_doi' and m['model_echo'] == original['study_doi'] for m in metadata['echo_mismatches'])

@pytest.mark.parametrize('warning', ['The supplied DOI and title do not match the supplied text.', 'The supplied DOI does not match the abstract.'])
def test_source_content_mismatch_still_rejected(task, warning):
    with pytest.raises(OutputQualityError):
        apply_trusted_identity_envelope({'warnings': [warning], 'items': []}, task)

def test_scientific_statistic_disagreement_is_not_identity_mismatch(task):
    result = {'warnings': ['The statistics in the text do not match the table values.'], 'items': []}
    fixed, _ = apply_trusted_identity_envelope(result, task)
    assert fixed['warnings'] == result['warnings']

def test_unsupported_task_profile_not_silently_accepted(task):
    task['extraction_contract']['prompt_profile'] = 'unrecognized'
    with pytest.raises(ValueError):
        apply_trusted_identity_envelope({'items': [], 'warnings': []}, task)
