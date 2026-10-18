"""Opt-in observation fields survive conversion/publication without new inference."""
import copy
import json
import unittest
from pathlib import Path

from pipeline.extract.primary_observation_contract import SHARED_FIELDS
from pipeline.kg.build_evidence_tables import finding_row
from pipeline.kg.convert_routed_extractions_to_evidence_rows import evidence_row_for_item
from pipeline.publish.export_evidence_payload import (
    OPTIONAL_PRIMARY_OBSERVATION_FIELDS,
    columnar_bootstrap_payload,
    finding_from_record,
)


class PrimaryObservationTransportTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            'schema_version': 'primary_molecular_pathway_readout_v1',
            'task_id': 'observation-roundtrip', 'route_id': 'route',
            'study_doi': '10.1000/observation',
            'domain_route': 'molecular_pathway_readout',
            'text_depth': 'article_text', 'extraction_status': 'extracted',
        }
        self.item = {
            'compound_or_exposure': 'Ketamine',
            'graph_entity_label': 'BDNF',
            'specific_readout_or_marker': 'BDNF',
            'molecular_effect_category': 'protein_expression',
            'tissue_or_sample': 'Cultured rat hippocampal neurons',
            'dose_or_exposure': '10 µM',
            'quantitative_value': '1.3-fold versus vehicle',
            'unit': 'fold', 'comparator': 'vehicle-treated neurons',
            'experimental_system_category': 'in_vitro',
            'result_direction': 'increase',
            'finding_summary': 'BDNF protein abundance increased versus vehicle.',
        }
        self.optional = {
            'observation_role': 'experimental_result',
            'exposure_role': 'focal_exposure',
            'comparison_basis': 'between_groups',
            'measurement_type': 'expression_or_abundance',
            'analysis_unit': 'biological_samples',
            'result_pattern': 'increase',
            'value_status': 'source_reported',
            'value_source_locator': 'Table 2; BDNF row; ketamine versus vehicle',
        }

    def convert(self, item, result):
        return evidence_row_for_item(
            output_row={}, result=result, item=item, item_kind='primary_item',
            item_index=1, tasks={},
        )

    def build(self, row):
        return finding_row(
            row, 'routed_evidence', 'molecular_pathway_readout',
            'molecular_pathway_readout', 'primary', 'finding:example',
            'paper:10.1000/observation', id_field='finding_id',
        )

    def test_all_candidate_fields_and_comparator_round_trip_to_browser(self):
        self.assertEqual(set(self.optional), set(SHARED_FIELDS))
        candidate = {**self.item, **self.optional}
        result = {**self.result, 'schema_version': 'primary_molecular_pathway_readout_v2_observation'}
        row = self.convert(candidate, result)
        self.assertEqual(row['route_output_schema_version'], 'routed_evidence_rows_v1')
        self.assertEqual(row['extraction_schema_version'], result['schema_version'])
        built = self.build(row)
        raw = json.loads(built['raw_row_json'])
        browser = finding_from_record(built, {})
        payload = columnar_bootstrap_payload(
            [browser], 'test', Path('.'), 'primary', schema_version='test',
        )
        displayed = dict(zip(payload['fields'], [payload['values'][i] for i in payload['rows'][0]]))
        expected = {**self.optional, 'comparator': self.item['comparator'],
                    'extraction_schema_version': result['schema_version']}
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertEqual(row[field], value)
                self.assertEqual(raw[field], value)
                self.assertEqual(browser[field], value)
                self.assertEqual(displayed[field], value)
        self.assertNotIn('raw_row_json', displayed)
        self.assertNotIn('supporting_quote', displayed)

    def test_optional_fields_do_not_change_existing_normalized_claims(self):
        baseline = self.build(self.convert(self.item, self.result))
        candidate = self.build(self.convert({**self.item, **self.optional}, self.result))
        baseline_raw = json.loads(baseline.pop('raw_row_json'))
        candidate_raw = json.loads(candidate.pop('raw_row_json'))
        self.assertEqual(baseline, candidate)
        for field in self.optional:
            self.assertNotIn(field, baseline_raw)
            candidate_raw.pop(field)
        self.assertEqual(baseline_raw, candidate_raw)
        browser = finding_from_record({**baseline, 'raw_row_json': json.dumps(baseline_raw)}, {})
        self.assertFalse(set(self.optional) & set(browser))

    def test_source_version_is_preserved_and_not_invented(self):
        row = self.convert(self.item, self.result)
        self.assertEqual(row['extraction_schema_version'], self.result['schema_version'])
        no_version = copy.deepcopy(self.result)
        del no_version['schema_version']
        self.assertNotIn('extraction_schema_version', self.convert(self.item, no_version))
        self.assertEqual(set(OPTIONAL_PRIMARY_OBSERVATION_FIELDS),
                         set(SHARED_FIELDS) | {'extraction_schema_version'})


if __name__ == '__main__':
    unittest.main()
