"""Opt-in, versioned primary extraction candidate; production defaults stay explicit.

The instruction-only arm uses unchanged domain schemas. The structured arm
adds small shared role fields to those same schemas for a separate ablation.
"""
from __future__ import annotations

import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'primary_observation_v2'
PROMPT = ROOT / 'docs/extraction_profiles/candidates/primary_observation_v2.md'


def enum_field(values, description):
    return {'type': 'string', 'enum': values, 'description': description}


SHARED_FIELDS = {
    'observation_role': enum_field(
        ['experimental_result', 'observational_association', 'descriptive_measurement',
         'qualitative_finding', 'observed_adverse_event', 'care_or_eligibility_practice',
         'analytical_method_result', 'other', 'not_reported'],
        'What the source actually reports, independent of the graph topic. Anticipated risks or eligibility policies are care_or_eligibility_practice, not observed adverse events.'),
    'exposure_role': enum_field(
        ['focal_exposure', 'intervention_package', 'mixed_exposure', 'measured_predictor',
         'assay_probe', 'comparator', 'contextual_exposure', 'not_reported'],
        'Role of the named exposure in THIS observation. Keep genuine packages/mixed exposures intact; drugs used only as tracers or care medication are not focal recreational exposures.'),
    'comparison_basis': enum_field(
        ['between_groups', 'within_subject_baseline', 'dose_comparison', 'time_comparison',
         'association', 'descriptive_without_comparator', 'other', 'not_reported'],
        'Scientific comparison supporting this item; not the overall study design. Name the actual arms or reference in comparator.'),
    'measurement_type': enum_field(
        ['clinical_or_behavioral_measure', 'reported_or_observed_experience', 'binding',
         'functional_response', 'expression_or_abundance', 'phosphorylation',
         'concentration', 'release_or_uptake', 'enzyme_activity', 'connectivity',
         'electrophysiology', 'anatomy_or_morphology', 'population_or_service_measure',
         'practice_or_document_measure', 'other', 'not_reported'],
        'What was directly measured. A mechanistic interpretation does not replace assay identity; tracer binding is binding of the tracer, not automatically the focal drug.'),
    'analysis_unit': enum_field(
        ['participants', 'animals', 'cells', 'spines_or_synapses', 'biological_samples',
         'encounters_or_events', 'documents', 'geographical_or_time_units',
         'nested_or_mixed', 'other', 'not_reported'],
        'Unit of the reported analysis/sample count. Preserve nested counts and their experiment in sample_size; never borrow n from an adjacent panel.'),
    'result_pattern': enum_field(
        ['increase', 'decrease', 'no_detected_difference', 'positive_association',
         'negative_association', 'descriptive', 'mixed', 'other', 'not_reported'],
        'Measured result relative to the stated comparison. Separate from beneficial/harmful valence. Nonsignificance is not equivalence.'),
    'value_status': enum_field(
        ['source_reported', 'qualitative_only', 'ambiguous_or_conflicting', 'not_reported'],
        'Whether quantitative attribution is secure. Ambiguous numerical fields stay not_reported, with the ambiguity explained in warnings. No speculative unit/table repair.'),
    'value_source_locator': {
        'type': 'string',
        'description': 'Concise source analysis identity for quantitative values: supplied table/figure locator plus row/column or panel and endpoint/contrast, or Abstract. Use not_reported when no value is reported. This is provenance, not new scientific evidence.'},
}

STRUCTURED_INSTRUCTION = '''## Shared structured observation fields

In the added shared fields, state the observation's role, exposure role, comparison basis, measurement type, analysis unit, measured result pattern and quantitative-source status using their supplied definitions. Name table rows/outcome columns or figure panels in value_source_locator when a number depends on them. These fields describe the same observation as the domain fields, not a new interpretation. Use comparator for the actual reference arm or condition when one exists. Keep specimen, dose, population and timing in their existing domain fields, and retain additional scientifically useful detail in the summary. If a result is mixed, label each contrast in prose rather than assigning a single misleading sign.
'''


def candidate_instruction(base_instruction: str, *, structured: bool = False) -> str:
    if '## Scope' not in base_instruction:
        raise ValueError('Primary instruction lacks explicit domain scope')
    scope = base_instruction.split('## Scope', 1)[1].split('## Extraction Outcome', 1)[0].strip()
    return (PROMPT.read_text().replace('{{DOMAIN_SCOPE}}', scope)
            .replace('{{STRUCTURED_FIELDS}}', STRUCTURED_INSTRUCTION if structured else '').strip())


def candidate_schema(schema: dict) -> dict:
    """Input is the native resolved primary schema; preserve all old fields."""
    result = copy.deepcopy(schema)
    version = result.get('properties', {}).get('schema_version', {})
    if version.get('enum'):
        version['enum'] = [v.removesuffix('_v1') + '_v2_observation' for v in version['enum']]
    item = result['properties']['items']['items']
    if item.get('type') != 'object':
        raise ValueError('Expected resolved primary item object')
    item['properties'].update(copy.deepcopy(SHARED_FIELDS))
    if 'comparator' not in item['properties'] and 'comparator_or_reference' not in item['properties']:
        item['properties']['comparator'] = {
            'type': 'string', 'description': 'Actual reference arm, condition, predictor contrast or not_applicable for a descriptive observation. Do not infer placebo from the overall trial design.'}
        item.setdefault('required', []).append('comparator')
    item.setdefault('required', []).extend(k for k in SHARED_FIELDS if k not in item['required'])
    return result
