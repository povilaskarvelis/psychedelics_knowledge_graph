#!/usr/bin/env python3
"""Audit manual PDF candidates for high-confidence non-English titles."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import subprocess

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_QUEUE = AUDITS / "manual_pdf_recovery_priority_queue.csv"
DEFAULT_CANDIDATE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_SWIFT = Path(__file__).with_name("detect_title_languages.swift")
DEFAULT_OUTPUT = AUDITS / "manual_pdf_recovery_language_audit.csv"
DEFAULT_REPORT = AUDITS / "manual_pdf_recovery_language_audit.json"

ENGLISH_CODES = {"en", "eng", "english"}


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    text = clean(value).lower()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text).rstrip(".,; ")


def title_token_count(title: str) -> int:
    return len(re.findall(r"[^\W\d_]+", title, flags=re.UNICODE))


def non_latin_ratio(title: str) -> float:
    letters = re.findall(r"[^\W\d_]", title, flags=re.UNICODE)
    if not letters:
        return 0.0
    non_latin = re.findall(r"[\u0370-\u052f\u0590-\u06ff\u0900-\u0dff\u3040-\u30ff\u3400-\u9fff]", title)
    return len(non_latin) / len(letters)


def assess_language(
    *,
    title: str,
    metadata_language: str,
    detected_language: str,
    confidence: float,
    publication_type: str = "",
) -> dict:
    metadata = clean(metadata_language).lower()
    detected = clean(detected_language).lower()
    tokens = title_token_count(title)
    script_ratio = non_latin_ratio(title)
    metadata_non_english = bool(metadata and metadata not in ENGLISH_CODES)
    detected_non_english = bool(detected and detected not in ENGLISH_CODES)
    translated_title_signal = bool(re.match(r"^\s*\[.+\][.?!]?\s*$", title, re.DOTALL))
    english_abstract_signal = "english abstract" in clean(publication_type).lower()

    # Scientific names and chemical nomenclature can fool a generic language
    # recognizer.  For Latin-script titles without supporting metadata, demand
    # extremely strong model confidence; non-Latin scripts remain decisive.
    strong_title_signal = detected_non_english and (
        script_ratio >= 0.20
        or (confidence >= 0.98 and tokens >= 5)
        or (confidence >= 0.995 and tokens >= 3)
    )
    metadata_supported = metadata_non_english and detected_non_english and (
        confidence >= 0.80 or (detected == metadata and confidence >= 0.65)
    ) and tokens >= 3

    if strong_title_signal or metadata_supported or (
        translated_title_signal and (metadata_non_english or english_abstract_signal)
    ):
        basis = (
            f"title_language={detected};confidence={confidence:.4f};metadata_language={metadata or 'missing'};"
            f"title_tokens={tokens};non_latin_ratio={script_ratio:.4f};"
            f"translated_title={translated_title_signal};english_abstract={english_abstract_signal}"
        )
        return {
            "language_audit_decision": "exclude_non_english",
            "recommended_action": "exclude_publication_format",
            "publication_format": "non_english_article",
            "format_evidence": basis,
        }
    if metadata_non_english or detected_non_english:
        basis = (
            f"ambiguous_language_signal:title_language={detected or 'unknown'};confidence={confidence:.4f};"
            f"metadata_language={metadata or 'missing'};title_tokens={tokens}"
        )
        return {
            "language_audit_decision": "review_language_signal",
            "recommended_action": "review_language",
            "publication_format": "possible_non_english_article",
            "format_evidence": basis,
        }
    return {
        "language_audit_decision": "retain_language_eligible",
        "recommended_action": "retain_for_manual_recovery",
        "publication_format": "",
        "format_evidence": f"title_language={detected or 'unknown'};confidence={confidence:.4f};metadata_language={metadata or 'missing'}",
    }


def recognize_titles(frame: pd.DataFrame, swift_script: Path) -> dict[str, dict]:
    payload = "".join(
        json.dumps({"doi": normalize_doi(row["doi"]), "title": clean(row["study_title"])}, ensure_ascii=False) + "\n"
        for row in frame.to_dict("records")
    )
    completed = subprocess.run(
        ["xcrun", "swift", str(swift_script.resolve())],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    )
    out: dict[str, dict] = {}
    for line in completed.stdout.splitlines():
        row = json.loads(line)
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi] = row
    return out


def build_audit(queue: pd.DataFrame, candidate: pd.DataFrame, recognized: dict[str, dict]) -> pd.DataFrame:
    candidate = candidate.copy()
    candidate["doi"] = candidate["doi"].map(normalize_doi)
    candidate_by_doi = candidate.drop_duplicates("doi", keep="last").set_index("doi")
    languages = candidate_by_doi["language"].to_dict()
    publication_types = candidate_by_doi["publication_type"].to_dict()
    rows = []
    for row in queue.fillna("").to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        title = clean(row.get("study_title", ""))
        result = recognized.get(doi, {})
        detected = clean(result.get("detectedLanguage", ""))
        confidence = float(result.get("confidence", 0) or 0)
        assessment = assess_language(
            title=title,
            metadata_language=clean(languages.get(doi, "")),
            detected_language=detected,
            confidence=confidence,
            publication_type=clean(publication_types.get(doi, "")),
        )
        rows.append(
            {
                "doi": doi,
                "study_title": title,
                "metadata_language": clean(languages.get(doi, "")),
                "detected_title_language": detected,
                "detected_title_language_confidence": round(confidence, 6),
                "detected_title_language_alternatives": json.dumps(result.get("alternatives", {}), sort_keys=True),
                **assessment,
                "evidence_excerpt": title,
                "decision_method": "apple_natural_language_title_recognizer_v1",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--swift-script", default=str(DEFAULT_SWIFT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    queue = pd.read_csv(Path(args.queue), dtype=str, keep_default_na=False)
    candidate = pd.read_parquet(
        Path(args.candidate_table), columns=["doi", "language", "publication_type"]
    ).fillna("")
    recognized = recognize_titles(queue, Path(args.swift_script))
    audit = build_audit(queue, candidate, recognized)
    output = Path(args.output_csv).resolve()
    report_path = Path(args.report_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output, index=False)
    report = {
        "schema_version": "manual_pdf_recovery_language_audit_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_rows": len(queue),
        "recognized_rows": len(recognized),
        "decision_counts": dict(Counter(audit["language_audit_decision"])),
        "excluded_language_counts": dict(
            Counter(audit.loc[audit["language_audit_decision"].eq("exclude_non_english"), "detected_title_language"])
        ),
        "output_csv": str(output),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
