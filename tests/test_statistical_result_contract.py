import pytest
from pipeline.extract.statistical_result_contract import result_bundles_multiple_estimates


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
