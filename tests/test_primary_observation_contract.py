import copy
import unittest

from jsonschema import Draft7Validator

from pipeline.extract import primary_observation_contract as contract
from pipeline.extract import route_extraction_profiles as profiles


class ObservationContractTests(unittest.TestCase):
    def test_all_domain_schemas_retain_existing_scientific_fields(self):
        for name in profiles.PRIMARY_PROMPT_PROFILES:
            profile = profiles.primary_profile(name)
            schema = profiles.schema_for_native(profiles.load_schema_for_profile(profile))
            original = copy.deepcopy(schema)
            candidate = contract.candidate_schema(schema)
            Draft7Validator.check_schema(candidate)
            self.assertEqual(schema, original)
            old = original['properties']['items']['items']
            new = candidate['properties']['items']['items']
            for key, value in old['properties'].items():
                self.assertEqual(new['properties'][key], value)
            self.assertTrue(set(old['required']) <= set(new['required']))
            self.assertTrue(set(contract.SHARED_FIELDS) <= set(new['required']))
            self.assertIn('_v2_observation', candidate['properties']['schema_version']['enum'][0])

    def test_assigned_scope_preserved_and_schema_arm_instructions_separate(self):
        base = '# Title\n\nOpening\n\n## Scope\n\nExact domain wording.\n\n## Extraction Outcome\n\nOld instructions.'
        prompt = contract.candidate_instruction(base)
        structured = contract.candidate_instruction(base, structured=True)
        self.assertIn('Exact domain wording.', prompt)
        self.assertNotIn('Old instructions.', prompt)
        self.assertNotIn('Shared structured observation fields', prompt)
        self.assertIn('Shared structured observation fields', structured)
        self.assertNotIn('{{', structured)

    def test_empty_source_scope_fails_closed(self):
        with self.assertRaises(ValueError):
            contract.candidate_instruction('Unknown task')


if __name__ == '__main__':
    unittest.main()
