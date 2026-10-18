"""Shared checks for a result containing more than one quantitative estimate."""
import re


def result_bundles_multiple_estimates(item: dict) -> bool:
    statement = str(item.get('relationship_statement') or '').strip()
    ci_count = len(re.findall(r'95\s*%?\s*(?:ci|credible interval)', statement, re.IGNORECASE))
    assignments = len(re.findall(
        r"\b(?:hedges'?\s*g|g|smd|md|rr|or|hr|risk ratio|odds ratio|hazard ratio)\s*[=:]\s*[-+]?\d",
        statement, re.IGNORECASE))
    # Multilevel heterogeneity can report several I-squared percentages for a
    # single pooled estimate. They must not count as additional outcome rates.
    without_heterogeneity = re.sub(
        r'\bI\s*(?:\^\s*)?(?:2|²)\s*(?:\(?\s*(?:level\s*)?\d+\s*\)?)?\s*[=:]\s*[-+]?\d+(?:\.\d+)?\s*%',
        '', statement, flags=re.IGNORECASE)
    percentages = [v for v in re.findall(r'(?<!\d)(\d+(?:\.\d+)?)\s*%', without_heterogeneity)
                   if v not in {'95','90','99'}]
    estimate = item.get('effect_estimate') or {}
    return ci_count > 1 or assignments > 1 or (bool(estimate.get('estimate')) and len(percentages) > 1)
