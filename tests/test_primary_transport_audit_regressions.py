"""Source-audit regressions for conversion and publication, without model calls."""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.kg.convert_routed_extractions_to_evidence_rows import (
    add_common_field_aliases, convert_outputs, evidence_design_for,
)
from pipeline.publish.export_evidence_payload import (
    columnar_bootstrap_payload, finding_from_record, overview_graph_subjects,
)
from pipeline.publish.export_query_api import build_public_tables, project_relationship_subjects
from tests.query_api_fixtures import write_minimal_kg


class PrimaryTransportAuditRegressions(unittest.TestCase):
    def test_molecular_dose_tissue_and_quantity_reach_browser_with_units(self):
        row = {
            'domain': 'molecular_pathway_readout', 'compound_or_exposure': 'Ketamine',
            'dose_or_exposure': '10 µM for 2 hours', 'tissue_or_sample': 'Cultured rat hippocampal neurons',
            'quantitative_value': '1.3-fold versus vehicle', 'unit': 'fold',
            'assessment_timepoint': '30 minutes after corticosterone',
            'specific_readout_or_marker': 'GluR2', 'graph_entity_label': 'GluR2',
        }
        add_common_field_aliases(row, row['domain'])
        self.assertEqual(row['dose'], '10 µM for 2 hours')
        finding = finding_from_record({'raw_row_json': json.dumps(row)}, {})
        payload = columnar_bootstrap_payload([finding], 'test', Path('.'), 'primary', schema_version='test')
        displayed = dict(zip(payload['fields'], [payload['values'][i] for i in payload['rows'][0]]))
        for field in ('dose', 'dose_or_exposure', 'tissue_or_sample', 'quantitative_value', 'unit', 'assessment_timepoint'):
            self.assertEqual(displayed[field], row[field])
        self.assertNotIn('raw_row_json', displayed)
        self.assertNotIn('supporting_quote', displayed)

    def test_phase_alias_is_explicit_and_does_not_overwrite_precise_time(self):
        row = {'timepoint_or_phase': 'Preparation before dosing', 'timepoint': 'not_reported'}
        add_common_field_aliases(row, 'intervention_context')
        self.assertEqual(row['assessment_timepoint'], 'Preparation before dosing')
        self.assertEqual(row['timepoint'], 'Preparation before dosing')
        precise = {'dose': '5 mg/kg', 'dose_or_exposure': 'alternate dose wording',
                   'assessment_timepoint': '24 hours', 'timepoint_or_phase': 'Follow-up'}
        add_common_field_aliases(precise, 'intervention_context')
        self.assertEqual(precise['assessment_timepoint'], '24 hours')
        self.assertEqual(precise['timepoint_or_phase'], 'Follow-up')
        self.assertEqual(precise['dose'], '5 mg/kg')

    def test_explicit_experimental_system_precedes_donor_species(self):
        for system, population, expected in [
            ('in_vitro', 'rat_model', 'in_vitro'),
            ('ex_vivo', 'animal_model', 'ex_vivo'),
            ('not_reported', 'ex_vivo_tissue_model', 'ex_vivo'),
            ('computational', 'human_participants', 'computational'),
        ]:
            with self.subTest(system=system, population=population):
                self.assertEqual(evidence_design_for({
                    'model_or_system': 'Rat hippocampal preparation',
                    'study_design_category': 'other',
                    'experimental_system_category': system,
                    'population_model_category': population,
                }), expected)
        self.assertEqual(evidence_design_for({'study_design_category': 'rct', 'study_design': 'Randomized trial'}),
                         'randomized_controlled_trial')
        self.assertEqual(evidence_design_for({'study_design_category': 'preclinical_experiment',
            'population_model_category': 'mouse_model', 'study_design': 'Randomized animal experiment'}), 'preclinical')
        self.assertEqual(evidence_design_for({'experimental_system_category': 'in_vivo',
            'population_model_category': 'human_participants', 'study_design': 'Observational imaging study'}), 'observational')

    def test_unconvertible_item_keeps_identity_in_exclusion_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = {'task_id': 'audit-task', 'route_id': 'route', 'study_doi': '10.1000/audit'}
            result = {**task, 'domain_route': 'molecular_target', 'extraction_status': 'extracted',
                      'items': [{'compound_or_exposure': 'Ketamine', 'target': 'NMDA receptor'},
                                {'compound_or_exposure': 'Ketamine', 'target': 'not_reported'}]}
            (root/'tasks.jsonl').write_text(json.dumps(task)+'\n')
            (root/'outputs.jsonl').write_text(json.dumps({'status': 'ok', 'result': result})+'\n')
            rows, report = convert_outputs(input_jsonl=root/'outputs.jsonl', tasks_jsonl=root/'tasks.jsonl')
            self.assertEqual(len(rows), 1)
            self.assertEqual(report['skipped'], {'missing_compound_or_entity_label': 1})
            self.assertEqual(report['item_exclusions'], [{**task, 'domain_route': 'molecular_target',
                'source_item_type': 'primary_item', 'source_item_index': 2, 'reason': 'missing_entity_label'}])

    def test_api_expands_browser_plural_subjects_but_keeps_narrow_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_kg(root)
            edges = pd.read_parquet(root/'evidence_edges.parquet')
            projections = json.dumps([
                {'label': 'Psilocybin', 'kind': 'atomic_compound'},
                {'label': 'Ketamine', 'kind': 'atomic_compound'},
            ])
            edges['graph_overview_subjects_json'] = ''
            first = edges.index[edges['graph_admission_status'].eq('main_graph')][0]
            edges.loc[first, 'graph_overview_subjects_json'] = projections
            edges.to_parquet(root/'evidence_edges.parquet', index=False)
            tables = build_public_tables(root)
            paper_id = edges.loc[first, 'paper_id']
            relations = tables['relationships'][tables['relationships']['paper_id'].eq(paper_id)]
            self.assertEqual(set(relations['subject_label']),
                             {s['label'] for s in overview_graph_subjects(edges.loc[first].to_dict())})
            self.assertEqual(set(relations['subject_id']), {'compound:psilocybin', 'compound:ketamine'})
            self.assertEqual(set(relations['object_id']), {edges.loc[first, 'entity_id']})
            self.assertFalse({'finding_id', 'graph_overview_subjects_json', 'dose', 'effect_size'} & set(relations.columns))
            self.assertFalse(tables['relationships']['paper_id'].eq('paper:10.1000/review').any())

    def test_missing_projected_concept_fails_instead_of_silently_dropping_subject(self):
        edges = pd.DataFrame([{'compound': 'Ketamine', 'compound_id': 'compound:ketamine',
            'graph_subject_kind': 'atomic_compound', 'graph_overview_subjects_json': json.dumps([
                {'label': 'Ketamine', 'kind': 'atomic_compound'}, {'label': 'Psilocybin', 'kind': 'atomic_compound'}])}])
        entities = pd.DataFrame([{'entity_id': 'compound:ketamine', 'entity_kind': 'atomic_compound', 'label': 'Ketamine'}])
        with self.assertRaisesRegex(ValueError, 'Psilocybin'):
            project_relationship_subjects(edges, entities)

    def test_subject_resolution_accepts_existing_compound_used_as_analyte(self):
        edges = pd.DataFrame([{'compound': 'DMT', 'compound_id': 'compound:dmt',
            'graph_subject_kind': 'atomic_compound', 'graph_overview_subjects_json': json.dumps([
                {'label': 'DMT', 'kind': 'atomic_compound'}, {'label': 'Bufotenin', 'kind': 'atomic_compound'}])}])
        entities = pd.DataFrame([{'entity_id': 'compound:bufotenin', 'entity_type': 'compound',
                                 'entity_kind': 'compound', 'label': 'Bufotenin'}])
        projected = project_relationship_subjects(edges, entities)
        self.assertEqual(list(projected['compound_id']), ['compound:dmt', 'compound:bufotenin'])
        self.assertEqual(set(projected['graph_subject_kind']), {'atomic_compound'})


if __name__ == '__main__':
    unittest.main()
