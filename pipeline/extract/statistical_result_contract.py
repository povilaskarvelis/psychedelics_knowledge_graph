"""Shared checks for the statistical meaning of one extracted result.

The structured effect is the estimate being graphed. Arm rates, its confidence
limits, an outcome definition and model predictions can accompany that effect
without becoming additional estimates. These checks do not repair source data.
"""
import re


NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
SCALAR = re.compile(rf"^\s*({NUMBER})\s*(%)?\s*$")
PERCENT = re.compile(rf"(?<![\d.])({NUMBER})\s*%")
INTERVAL_LABEL = r"(?:ci|confidence\s+interval|credible\s+interval|prediction\s+interval)"


def _normalized(value: object) -> str:
    return str(value or '').replace('−', '-').replace('–', '-').replace('—', '-')


def _scalar(value: object):
    return SCALAR.fullmatch(_normalized(value))


def _percentages_without_context(statement: str, estimate: dict) -> str:
    # Do not delete arbitrary spans between comparisons such as < and >.
    text = re.sub(
        rf'\bI\s*(?:\^\s*)?(?:2|²)\s*(?:\(?\s*(?:level\s*)?\d+\s*\)?)?\s*[=:]\s*{NUMBER}\s*%',
        '', statement, flags=re.IGNORECASE)
    # A confidence level is not an observed outcome rate (including levels
    # other than 90/95/99). Conversely an actual 95% response rate still is.
    text = re.sub(rf'\b\d+(?:\.\d+)?\s*%\s*(?={INTERVAL_LABEL}(?![A-Za-z]))', '', text, flags=re.IGNORECASE)
    if _scalar(estimate.get('interval_lower')) and _scalar(estimate.get('interval_upper')):
        # The interval is one uncertainty statement, not two outcome estimates.
        text = re.sub(
            rf'\b{INTERVAL_LABEL}(?![A-Za-z])\s*[=:]?\s*[\[(]?\s*{NUMBER}\s*%?\s*(?:-|to|,)\s*{NUMBER}\s*%?',
            '', text, flags=re.IGNORECASE)
    # Explicit responder definitions are thresholds, not measured rates.
    text = re.sub(
        rf'(?:at\s+least|at\s+most|more\s+than|less\s+than|[<>]=?|[≤≥])\s*(?:a\s+)?{NUMBER}\s*%\s+(?:reduction|increase|change|improvement)',
        '', text, flags=re.IGNORECASE)
    return text


def _contextual_percentages(statement: str, item: dict, estimate: dict) -> bool:
    """Whether remaining percentages describe one scalar effect's context.

Require an atomic structured estimate and explicit statistical roles. A list of
pooled rates, subgroups, rankings or outcome-specific effects is never released
just because its prose also mentions treatment/control groups.
"""
    scalar = _scalar(estimate.get('estimate'))
    if not scalar:
        return False
    text = _percentages_without_context(statement, estimate)
    values = list(PERCENT.finditer(text))
    if len(values) <= 1:
        return True
    metric = _normalized(estimate.get('metric')).lower()
    # One comparative effect may include its two arm/component rates. Remove
    # the primary percentage itself first for risk differences.
    if scalar.group(2):
        target = float(scalar.group(1))
        for value in values:
            if float(value.group(1)) == target:
                text = text[:value.start()] + ' ' * (value.end()-value.start()) + text[value.end():]
                break
        values = list(PERCENT.finditer(text))
    contrast_metric = bool(re.search(
        r'\b(?:odds\s+ratio|relative\s+risk|risk\s+ratio|hazard\s+ratio|risk\s+difference|or|rr|hr|rd)\b|difference.*response.rate',
        metric, re.IGNORECASE))
    arm_context = bool(re.search(
        r'\b(?:response|remission|incidence|event|reported\s+by|occurred\s+in)\b', text, re.IGNORECASE))
    comparison_context = bool(re.search(
        r'\b(?:versus|vs\.?|placebo|control|active.arm|treatment.arm|recipients|group)\b', text, re.IGNORECASE))
    distinct_outcomes = bool(re.search(r'\bresponse\b', text, re.I) and re.search(r'\bremission\b', text, re.I))
    if contrast_metric and len(values) == 2 and arm_context and comparison_context and not distinct_outcomes:
        return True
    # Predictions at two covariate values illustrate the one fitted coefficient;
    # they are not independently estimated subgroup effects.
    return (
        len(values) == 2
        and item.get('result_role') == 'meta_regression'
        and bool(re.search(r'\bcoefficient\b', metric))
        and bool(re.search(r'\bmodel.predicted\b', text, re.IGNORECASE))
        and bool(re.search(r'\bfrom\b.*%.*\bto\b.*%', text, re.IGNORECASE))
    )


def result_bundles_multiple_estimates(item: dict) -> bool:
    statement = _normalized(item.get('relationship_statement')).strip()
    # Preserve the existing explicit multiple-interval check. A confidence and
    # prediction interval may describe the same primary estimate.
    ci_count = len(re.findall(r'95\s*%?\s*(?:ci|credible interval)', statement, re.IGNORECASE))
    assignments = len(re.findall(
        r"\b(?:hedges'?\s*g|g|smd|md|rr|or|hr|risk ratio|odds ratio|hazard ratio)\s*[=:]\s*[-+]?\d",
        statement, re.IGNORECASE))
    estimate = item.get('effect_estimate') or {}
    if not isinstance(estimate, dict):
        estimate = {}
    # Named estimates in the structured estimate field can be bundled without
    # repeated metric assignments or any percentages (e.g. three treatment
    # SMCs). Ignore accompanying uncertainty/sample-size/NNT annotations.
    named_effects = []
    for part in _normalized(estimate.get('estimate')).split(';'):
        match = re.match(rf'\s*([^:;]+?)\s*:\s*({NUMBER})(?:\s|%|$)', part)
        if match and not re.fullmatch(r'(?:\d+\s*%\s*)?(?:CI|CrI|PI|SEM?|SD|NNT|NNH|P|N|K|DF)', match.group(1).strip(), re.I):
            named_effects.append(match.group(1).strip())
    percentages = PERCENT.findall(_percentages_without_context(statement, estimate))
    return (ci_count > 1 or assignments > 1 or len(named_effects) > 1
            or (bool(estimate.get('estimate')) and len(percentages) > 1
                and not _contextual_percentages(statement, item, estimate)))


def result_has_effect_scale_conflict(item: dict) -> bool:
    """Flag a percentage RD that contradicts an explicitly reported NNT.

Bare CI bounds can inherit percentage units, so their magnitude alone is not
proof of a conflict. A directly accompanying NNT provides an independent scale
check: NNT is the reciprocal absolute risk difference on the proportion scale.
The raw source values remain unchanged when this check flags a result.
"""
    estimate = item.get('effect_estimate') or {}
    if not isinstance(estimate, dict):
        return False
    metric = _normalized(estimate.get('metric'))
    if not re.search(r'\b(?:risk\s+difference|absolute\s+risk\s+(?:reduction|increase)|rd|arr|ari)\b', metric, re.IGNORECASE):
        return False
    scalar = _scalar(estimate.get('estimate'))
    if not scalar or not scalar.group(2):
        return False
    value = abs(float(scalar.group(1)))
    if not 0 < value < 1:
        return False
    statement = _normalized(item.get('relationship_statement'))
    nnts = re.findall(rf'\b(?:NNT|number\s+needed\s+to\s+treat)\s*(?:[=:]|of|was|is)?\s*({NUMBER})', statement, re.IGNORECASE)
    if len(nnts) != 1:
        return False
    nnt = abs(float(nnts[0]))
    if nnt == 0:
        return False
    # Allow ordinary integer rounding; only flag a clear hundred-fold mismatch
    # with the percentage reading and agreement with the proportion reading.
    proportional_nnt = 1 / value
    percentage_nnt = 100 / value
    return (abs(nnt-proportional_nnt) <= max(1, proportional_nnt*.1)
            and abs(nnt-percentage_nnt) > percentage_nnt*.5)
