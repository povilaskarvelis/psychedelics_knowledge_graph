import pytest
from pipeline.extract.statistical_result_contract import (
    result_bundles_multiple_estimates,
    result_has_effect_scale_conflict,
)


@pytest.mark.parametrize('heterogeneity',[
    'I 2 level2 = 11.39% and I 2 level3 = 77.67%',
    'I² = 11.39% and I² = 77.67%',
    'I^2 = 11.39% and I^2 = 77.67%',
])
def test_single_estimate_keeps_multilevel_heterogeneity(heterogeneity):
    item=dict(relationship_statement=f'SMC: -1.24, 95% CI -1.83 to -0.65; {heterogeneity}.',effect_estimate={'estimate':'-1.24'})
    assert not result_bundles_multiple_estimates(item)


@pytest.mark.parametrize('statement',[
    'SMD = 0.7 (95% CI 0.4 to 0.9) versus midazolam; SMD = 1.8 (95% CI 1.4 to 2.2) versus saline.',
    'Response rates were 45% under ketamine and 18% under midazolam.',
    'SMD = 0.7 and SMD = 1.8; I² = 40% and I² = 50%.',
])
def test_distinct_estimates_remain_blocked(statement):
    assert result_bundles_multiple_estimates(dict(relationship_statement=statement,effect_estimate={'estimate':'0.7; 1.8'}))


@pytest.mark.parametrize('statement,estimate', [
    ('Pooled OR 10.09 (95% CI 4.96-20.52). Response occurred in 84/161 ketamine recipients (52.2%) and 11/140 placebo recipients (7.8%).',
     {'metric': 'Odds ratio', 'estimate': '10.09', 'interval_lower': '4.96', 'interval_upper': '20.52'}),
    ('Insomnia was reported by 52 patients (7.3%) in the esketamine group and 40 (6.7%) in the placebo group.',
     {'metric': 'Odds ratio (OR)', 'estimate': '1.07', 'interval_lower': '.68', 'interval_upper': '1.69'}),
    ('Ketamine increased response versus placebo: 50% versus 13%, RR 2.6 (95% CI 1.6 to 4.4); NNT 2.9.',
     {'metric': 'Relative risk', 'estimate': '2.6', 'interval_lower': '1.6', 'interval_upper': '4.4'}),
    ('The pooled prevalence was 26% (95% CI 14%-43%).',
     {'metric': 'Pooled proportion', 'estimate': '26%', 'interval_lower': '14%', 'interval_upper': '43%'}),
    ('Response required at least a 50% reduction; the pooled RD=0.11%.',
     {'metric': 'Risk difference', 'estimate': '0.11%'}),
    ('The active-control response rate differences were 25% for ESK-NS and 9% for AAPs. Their difference was +16% (95% CI .07-.25).',
     {'metric': 'Between-category difference in response-rate differences', 'estimate': '+16%', 'interval_lower': '.07', 'interval_upper': '.25'}),
])
def test_single_effect_retains_contextual_percentages(statement, estimate):
    assert not result_bundles_multiple_estimates({'relationship_statement': statement, 'effect_estimate': estimate})


def test_one_regression_coefficient_can_include_model_predictions():
    item = {'result_role': 'meta_regression', 'relationship_statement':
            'Mean age did not moderate prevalence (coefficient .20), despite model-predicted prevalence increasing from 25.04% at age 18 to 62.99% at age 26.',
            'effect_estimate': {'metric': 'Meta-regression coefficient', 'estimate': '.20'}}
    assert not result_bundles_multiple_estimates(item)
    item['result_role'] = 'subgroup_analysis'
    assert result_bundles_multiple_estimates(item)


@pytest.mark.parametrize('item', [
    {'relationship_statement': 'Response rates were 95% under ketamine and 90% under placebo.', 'effect_estimate': {'metric': 'Response rates', 'estimate': '95%; 90%'}},
    {'relationship_statement': 'Ketamine response was 54% and remission was 30%.', 'effect_estimate': {'metric': 'Pooled proportion', 'estimate': 'Response 54%; remission 30%'}},
    {'relationship_statement': 'OR=2.1 for response; OR=1.6 for remission, rates 50% and 20%.', 'effect_estimate': {'metric': 'OR', 'estimate': '2.1'}},
    {'relationship_statement': 'Treatment response 50%, remission 20%, dropout 10%; control response 15%.', 'effect_estimate': {'metric': 'OR', 'estimate': '2.1'}},
    {'relationship_statement': 'Pooled prevalence was 44% to 77%.', 'effect_estimate': {'metric': 'Prevalence', 'estimate': '44% to 77%'}},
])
def test_true_bundles_and_ranges_are_not_released(item):
    assert result_bundles_multiple_estimates(item)


def test_percentage_risk_difference_nnt_scale_conflict_is_flagged_not_repaired():
    item = {'relationship_statement': 'The article reports RD=0.11% and NNT=9.',
            'effect_estimate': {'metric': 'Risk difference (RD)', 'estimate': '0.11%', 'interval_lower': '0.05', 'interval_upper': '0.16'}}
    assert result_has_effect_scale_conflict(item)
    assert item['effect_estimate']['estimate'] == '0.11%'


@pytest.mark.parametrize('estimate,statement', [
    ('11%', 'RD=11% and NNT=9.'),
    ('0.11', 'RD=0.11 and NNT=9.'),
    ('0.11%', 'RD=0.11% and NNT=909.'),
    ('0.11%', 'RD=0.11%, with a 95% CI of0.05-0.16.'),
])
def test_compatible_or_unspecified_percentage_scale_is_not_rejected(estimate, statement):
    assert not result_has_effect_scale_conflict({'relationship_statement': statement, 'effect_estimate': {'metric': 'Risk difference', 'estimate': estimate}})


def test_scalar_contrast_does_not_excuse_two_different_outcome_rates():
    item = {'relationship_statement': 'Ketamine response was 50% and remission was 20% compared with placebo.',
            'effect_estimate': {'metric': 'OR', 'estimate': '2.1'}}
    assert result_bundles_multiple_estimates(item)


def test_named_effect_list_does_not_require_percentages_or_repeated_metric():
    item = {'relationship_statement': 'Mean changes were 1.21 for psilocybin, 1.28 for SSRIs, and 1.43 for esketamine.',
            'effect_estimate': {'metric': 'SMC (SEM)', 'estimate': 'Psilocybin: 1.21; SSRI: 1.28; esketamine: 1.43'}}
    assert result_bundles_multiple_estimates(item)
    item['effect_estimate']['estimate'] = 'SMC: 1.21; SEM: 0.15; NNT: 9'
    assert not result_bundles_multiple_estimates(item)
