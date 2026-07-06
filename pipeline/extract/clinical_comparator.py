#!/usr/bin/env python3
"""Normalize clinical comparator labels into stable design buckets."""

from __future__ import annotations

import re

try:
    from pipeline.extract.io_utils import normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from io_utils import normalize


COMPARATOR_ORDER = (
    "Placebo",
    "Active placebo",
    "Baseline",
    "No comparator",
    "Dose or route comparison",
    "Active treatment",
    "Standard care",
    "Observational controls",
    "Not reported",
    "Not applicable",
    "Other",
)

NOT_REPORTED_VALUES = {"", "not_reported", "not reported", "unknown", "uncertain"}
NOT_APPLICABLE_VALUES = {"not_applicable", "not applicable", "n/a", "na"}


def comparator_text(value: object) -> str:
    text = normalize(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[_/()+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def normalize_clinical_comparator(comparator: object = "") -> str:
    text = comparator_text(comparator)
    if text in NOT_REPORTED_VALUES:
        return "Not reported"
    if text in NOT_APPLICABLE_VALUES:
        return "Not applicable"

    if has(r"\b(no comparator|no control|no comparative|uncontrolled|single arm|no treatment|no ketamine|no analgesia|none)\b", text):
        return "No comparator"
    if has(
        r"\b(baseline|pre treatment|pre intervention|pre retreat|pre dose|previous treatments?|retrospective pre|"
        r"pre operation|preoperation|pretreatment|before infusion|preinfusion|before psychedelic|intake|time period before|"
        r"pre study|study exit|after first pap|post dosing|before the second infusion)\b",
        text,
    ):
        return "Baseline"
    if has(r"\b(midazolam|niacin|diphenhydramine|active placebo|psychoactive placebo|1 mg psilocybin|5 mg psilocybin|low dose)\b", text):
        return "Active placebo"
    if has(r"\b(placebo|saline|normal saline|isotonic saline|0\.9% saline|vehicle|lactose|nitrogen|water)\b", text):
        return "Placebo"
    if has(r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|ug|μg|µg|g|ml)|dose|doses?)\b", text) and has(
        r"\b(ket|ketamine|esketamine|psilocybin|comp360|mdma|dmt|lsd|nitrous|cannabidiol)\b",
        text,
    ):
        return "Dose or route comparison"
    if has(
        r"\b(iv ketamine|intravenous ketamine|intranasal esketamine|in esketamine|esketamine alone|ketamine alone|"
        r"ketamine therapy|es ketamine therapy|r s ketamine|oral ketamine|subcutaneous versus intranasal|four infusion|"
        r"injectable r s ketamine|racemic ketamine|s ketamine|r ketamine|esk in|mdma alone|psilocybin alone|"
        r"intrathecal psilocin|ketamine only|2r 6r hnk|ibogaine|other routes of administration)\b",
        text,
    ):
        return "Dose or route comparison"
    if has(
        r"\b(treatment as usual|treatment-as-usual|standard care|standard of care|usual care|conventional|community of practice|"
        r"mbsr|routine treatment|rwt|standard postpartum care|linkage alone|outpatient medication management|waitlist)\b",
        text,
    ):
        return "Standard care"
    if has(
        r"\b("
        r"healthy comparison|comparison group|matched controls?|control group|controls?|non users?|non mdma users?|"
        r"non responders?|nonresponders?|younger patients?|unmedicated|anxious mdd|no change|non aia|patients without|"
        r"patients with no|non early improvers?|no lifetime|"
        r"subjects who had no|normative sample|reference category|men|women|unipolar depression|low trauma|trauma type absent|"
        r"without pain|other chronic pain|mild pain|non pain|healthy individuals?|males?|female|socially isolated|"
        r"with low insomnia|non obese|without comorbid|do not suffer|without diabetes|without hyperlipidemia|"
        r"did not have|did not receive|responders?|abstinent users?|neuroleptic free|adults without"
        r")\b",
        text,
    ):
        return "Observational controls"
    if has(
        r"\b("
        r"ect|electro convulsive|electroconvulsive|escitalopram|antidepressants?|ssri|oad|quetiapine|lithium|"
        r"rtms|methadone|ketorolac|fentanyl|sufentanil|remifentanil|acetaminophen|hydromorphone|morphine|"
        r"opioid|analgesic|propofol|etomidate|bupivacaine|dexamethasone|gabapentin|tramadol|diclofenac|"
        r"metoclopramide|psychotherapy|therapy alone|thiopental|methohexital|dexmedetomidine|lorazepam|"
        r"prochlorperazine|aminophylline|lidocaine|anaesthetic|benzodiazepines?|medication management|valproate|lexapro"
        r"|ketamine|esketamine|mdma|lsd|ayahuasca|dextromethorphan|pethidine|imipramine|duloxetine|sertraline|"
        r"magnesium sulfate|budesonide|methamphetamine|opiates|psychostimulants|antidepressivos"
        r")\b",
        text,
    ):
        return "Active treatment"
    return "Other"
