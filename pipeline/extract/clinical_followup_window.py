#!/usr/bin/env python3
"""Normalize clinical timepoint labels into stable follow-up windows."""

from __future__ import annotations

import re

try:
    from pipeline.extract.io_utils import normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from io_utils import normalize


FOLLOW_UP_WINDOW_ORDER = (
    "Acute / same day",
    "Early follow-up (1-7 days)",
    "Short follow-up (1-4 weeks)",
    "Medium follow-up (1-3 months)",
    "Long follow-up (4-12 months)",
    "Extended follow-up (>12 months)",
    "During treatment",
    "Treatment endpoint",
    "Baseline / pre-treatment",
    "Retrospective / lifetime",
    "Follow-up not reported",
    "Not applicable",
    "Other / mixed follow-up",
)

NOT_REPORTED_VALUES = {"", "not_reported", "not reported", "unknown", "uncertain"}
NOT_APPLICABLE_VALUES = {"not_applicable", "not applicable", "n/a", "na"}
NUMBER_WORDS = {
    "one": "1",
    "first": "1",
    "two": "2",
    "second": "2",
    "three": "3",
    "third": "3",
    "four": "4",
    "fourth": "4",
    "five": "5",
    "fifth": "5",
    "six": "6",
    "sixth": "6",
    "seven": "7",
    "seventh": "7",
    "eight": "8",
    "ninth": "9",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "twelfth": "12",
}


def followup_text(*values: object) -> str:
    parts = [normalize(value) for value in values if normalize(value)]
    text = " ".join(parts).casefold()
    for word, number in NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", number, text)
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[_/()+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def duration_days(text: str) -> float | None:
    """Return the longest explicit duration in days, if one is present."""

    durations: list[float] = []
    patterns = (
        (r"\b(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min)\b", 1 / 1440),
        (r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b", 1 / 24),
        (r"\b(?:days?|d|pod)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:days?|d)\b", 1),
        (r"\b(?:week|weeks|wk|w)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|wk)\b", 7),
        (r"\b(?:month|mo)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:months?|mos?|mo)\b", 30.44),
        (r"\b(?:year|yr)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?|yr)\b", 365.25),
    )
    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, text):
            value = next((group for group in match.groups() if group), "")
            if not value:
                continue
            try:
                durations.append(float(value) * multiplier)
            except ValueError:
                continue
    sequence_patterns = (
        (r"\bdays?\s+([0-9][0-9.,\sandto\-]+)", 1),
        (r"\bweeks?\s+([0-9][0-9.,\sandto\-]+)", 7),
        (r"\bmonths?\s+([0-9][0-9.,\sandto\-]+)", 30.44),
        (r"\byears?\s+([0-9][0-9.,\sandto\-]+)", 365.25),
    )
    for pattern, multiplier in sequence_patterns:
        for match in re.finditer(pattern, text):
            for value in re.findall(r"\d+(?:\.\d+)?", match.group(1)):
                try:
                    durations.append(float(value) * multiplier)
                except ValueError:
                    continue
    return max(durations) if durations else None


def window_from_days(days: float) -> str:
    if days <= 1:
        return "Acute / same day"
    if days <= 7:
        return "Early follow-up (1-7 days)"
    if days <= 31:
        return "Short follow-up (1-4 weeks)"
    if days <= 93:
        return "Medium follow-up (1-3 months)"
    if days <= 366:
        return "Long follow-up (4-12 months)"
    return "Extended follow-up (>12 months)"


def normalize_clinical_followup_window(follow_up_duration: object = "", timepoint: object = "") -> str:
    text = followup_text(follow_up_duration, timepoint)
    if text in NOT_REPORTED_VALUES:
        return "Follow-up not reported"
    if text in NOT_APPLICABLE_VALUES:
        return "Not applicable"

    if has(r"\b(lifetime|past year|past year|past month|past week|past use|prior use|history of|retrospective|previous year)\b", text):
        return "Retrospective / lifetime"
    if has(r"\b(baseline|pre treatment|pretreatment|pre dose|pre infusion|preinfusion|before treatment|before infusion|from baseline)\b", text):
        return "Baseline / pre-treatment"
    if has(
        r"\b(during|throughout|within|across)\b.*\b(treatment|infusions?|sessions?|administration|study|course|maintenance|series)\b|"
        r"\bover (?:the )?(?:treatment )?course\b|\bover the course of\b.*\b(treatment|infusions?|sessions?|study|course)\b|"
        r"\b(intraoperative|intra operative|within session)\b",
        text,
    ):
        return "During treatment"
    if has(
        r"\b(end of treatment|end treatment|treatment endpoint|endpoint|post treatment|after treatment|"
        r"posttreatment|post therapy|after therapy|study exit|on discharge|after induction|conclusion of|"
        r"pre to post intervention|after .* treatment|after completed treatment|after completion of|"
        r"after the treatment series|after induction phase|after (?:the )?\d+(?:st|nd|rd|th)?.*(?:infusions?|treatments?|sessions?)|"
        r"after the \d+(?:st|nd|rd|th)? (?:infusions?|treatments?|sessions?)|"
        r"by the \d+(?:st|nd|rd|th)? (?:treatment|session)|treatment \d+|"
        r"final .*(?:infusion|treatment|session)|following (?:each |\d+ )?infusions?|after repeated infusions?)\b",
        text,
    ):
        days = duration_days(text)
        return window_from_days(days) if days is not None else "Treatment endpoint"
    if has(
        r"\b(acut\w*|rapid\w*|immediate|same day|postoperative\w*|post operative\w*|postinfusion|"
        r"post infusion|post administration|post dosing|after dosing|after first infusion|after each infusion)\b",
        text,
    ):
        days = duration_days(text)
        return window_from_days(days) if days is not None else "Acute / same day"

    days = duration_days(text)
    if days is not None:
        return window_from_days(days)

    if has(r"\b(short term)\b", text):
        return "Short follow-up (1-4 weeks)"
    if has(r"\b(long term|long lasting|sustained|follow up|followup|over time|later|maintenance)\b", text):
        return "Other / mixed follow-up"
    return "Other / mixed follow-up"
