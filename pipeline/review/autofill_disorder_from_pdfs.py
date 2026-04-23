#!/usr/bin/env python3
"""Autofill disorder stubs from local PDF full text."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    from pipeline.review.pdf_runtime import ensure_pdf_runtime
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from pdf_runtime import ensure_pdf_runtime

ROOT = Path(__file__).resolve().parents[2]

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.ERROR)

DATASET_CONFIG = {
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
    }
}

STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
LITERAL_STRING_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")
HEX_STRING_RE = re.compile(rb"<([0-9A-Fa-f\s]+)>")

OUTCOME_MEASURE_PATTERNS = [
    ("madrs", "MADRS"),
    ("montgomery asberg depression rating scale", "MADRS"),
    ("montgomery asberg", "MADRS"),
    ("hamilton depression rating scale", "HAM-D"),
    ("hamilton depression", "HAM-D"),
    ("hdrs", "HAM-D"),
    ("hamd", "HAM-D"),
    ("ham d", "HAM-D"),
    ("ham a", "HAM-A"),
    ("hama", "HAM-A"),
    ("hamilton anxiety rating scale", "HAM-A"),
    ("phq 9", "PHQ-9"),
    ("phq9", "PHQ-9"),
    ("patient health questionnaire 9", "PHQ-9"),
    ("gad 7", "GAD-7"),
    ("gad7", "GAD-7"),
    ("generalized anxiety disorder 7", "GAD-7"),
    ("bdi", "BDI"),
    ("beck depression inventory", "BDI"),
    ("qids", "QIDS"),
    ("quick inventory of depressive symptomatology", "QIDS"),
    ("ybocs", "Y-BOCS"),
    ("y bocs", "Y-BOCS"),
    ("yale brown obsessive compulsive scale", "Y-BOCS"),
    ("caps 5", "CAPS-5"),
    ("caps5", "CAPS-5"),
    ("caps-5", "CAPS-5"),
    ("clinician administered ptsd scale", "CAPS-5"),
    ("pcl 5", "PCL-5"),
    ("pcl5", "PCL-5"),
    ("pcl-5", "PCL-5"),
    ("ptsd checklist", "PCL-5"),
    ("stai", "STAI"),
    ("state trait anxiety inventory", "STAI"),
    ("dass 21", "DASS-21"),
    ("depression anxiety stress scale", "DASS-21"),
    ("cgi s", "CGI-S"),
    ("cgi i", "CGI-I"),
    ("clinical global impression", "CGI"),
    ("heavy drinking days", "Percent heavy drinking days"),
    ("percent heavy drinking days", "Percent heavy drinking days"),
    ("drinks per drinking day", "Drinks per drinking day"),
    ("alcohol craving", "Alcohol craving score"),
    ("obsessive compulsive drinking scale", "OCDS"),
    ("abstinent days", "Abstinent days"),
    ("abstinence", "Abstinence rate"),
    ("abstinence rate", "Abstinence rate"),
    ("relapse", "Relapse rate"),
]

PROTOCOL_KEYWORDS = {
    "study protocol",
    "trial protocol",
    "protocol for",
    "protocol:",
}

CONFERENCE_OR_POSTER_KEYWORDS = {
    "poster abstract",
    "poster abstracts",
    "meeting abstract",
    "meeting abstracts",
    "annual meeting",
    "scientific meeting",
    "conference abstract",
    "conference proceedings",
    "psychopharmacology congress",
    "objectives/goals",
    "objectives/specific aims",
    "methods/study population",
    "results/anticipated results",
    "discussion/significance",
}
NUMBERED_ABSTRACT_TITLE_RE = re.compile(r"^\s*(\d{2,5})\s+[A-Za-z]")

REVIEWISH_KEYWORDS = {
    "systematic review",
    "narrative review",
    "scoping review",
    "umbrella review",
    "literature review",
    "review article",
    "rapid review",
    "meta analysis",
    "meta-analysis",
    "pooled analysis",
}

NON_COUNTABLE_ARTICLE_KEYWORDS = {
    "commentary",
    "editorial",
    "future directions",
    "highlight research directions",
    "is there a place for",
    "research directions",
    "viewpoint",
    "we aim to explore this topic",
    "where do we go from here",
}

HEALTHY_VOLUNTEER_RE = re.compile(r"\bhealthy (?:volunteers?|participants?|adults?|subjects?|controls?)\b")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def disorder_context_terms(disorder: str) -> Set[str]:
    text = normalize_text(disorder)
    terms = {text} if text else set()
    if "major depressive disorder" in text:
        terms.update({"depression", "mdd", "unipolar depression"})
    if "treatment resistant depression" in text:
        terms.update({"treatment resistant depression", "trd", "depression"})
    if "post traumatic stress disorder" in text or "posttraumatic stress disorder" in text:
        terms.update({"ptsd", "post traumatic stress disorder", "posttraumatic stress disorder"})
    if "social anxiety disorder" in text:
        terms.update({"social anxiety", "social anxiety disorder"})
    if "substance use disorder" in text:
        terms.update({"substance use disorder", "addiction"})
    return {term for term in terms if term}


def has_disorder_sample_context(disorder: str, text_norm: str) -> bool:
    for term in disorder_context_terms(disorder):
        escaped = re.escape(term)
        if re.search(
            rf"\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people) with [a-z0-9 ]{{0,80}}\b{escaped}\b",
            text_norm,
        ):
            return True
        if re.search(rf"\bhealthy (?:volunteers?|participants?|controls?|subjects?) and [a-z0-9 ]{{0,50}}\b{escaped}\b", text_norm):
            return True
        if re.search(
            rf"\b{escaped}\b [a-z0-9 ]{{0,60}}\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people)\b",
            text_norm,
        ):
            return True
    return False


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, Set[str]], Dict[str, str], List[Set[str]], Set[str]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, Set[str]] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[Set[str]] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups, set(properties.keys())


def is_valid_type(raw_value: str, expected_type: str) -> bool:
    if raw_value == "":
        return True
    if expected_type == "integer":
        try:
            int(float(raw_value))
            return True
        except Exception:
            return False
    if expected_type == "number":
        try:
            float(raw_value)
            return True
        except Exception:
            return False
    return True


def evaluate_row(
    row: dict,
    required: List[str],
    enums: Dict[str, Set[str]],
    types: Dict[str, str],
    one_of_groups: List[Set[str]],
    allowed_keys: Set[str],
) -> Tuple[List[str], List[dict]]:
    blocker_fields: Set[str] = set()
    blockers: List[dict] = []

    cleaned = {k: row.get(k, "") for k in allowed_keys}

    for field in required:
        if normalize(cleaned.get(field, "")) == "":
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "missing_required"})

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            merged = "|".join(sorted({field for group in one_of_groups for field in group}))
            blocker_fields.add(merged)
            blockers.append({"field": merged, "reason": "missing_one_of"})

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_enum", "value": value})

    for field, expected in types.items():
        value = normalize(cleaned.get(field, ""))
        if not is_valid_type(value, expected):
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_type", "value": value, "expected": expected})

    return sorted(blocker_fields), blockers


def append_note(notes: str, message: str) -> str:
    base = normalize(notes)
    msg = normalize(message)
    if not msg:
        return base
    if base and msg.lower() in base.lower():
        return base
    if not base:
        return msg
    return f"{base}; {msg}"


def is_weak_locator(value: str) -> bool:
    lowered = normalize(value).lower()
    return lowered in {"", "unspecified", "unknown", "n/a", "na", "not specified"}


def text_snippet(text: str, max_chars: int = 180) -> str:
    cleaned = normalize(" ".join(normalize(text).split()))
    if not cleaned:
        return ""
    return cleaned[:max_chars].rstrip()


def infer_study_design(source_type: str, text_norm: str) -> str:
    if source_type == "meta_analysis":
        return "meta_analysis"
    if source_type == "review":
        return "systematic_review" if "systematic review" in text_norm else "review"
    if "randomized" in text_norm or "double blind" in text_norm or "double-blind" in text_norm:
        return "randomized_controlled_trial"
    if "phase 3" in text_norm:
        return "phase_3_trial"
    if "phase 2" in text_norm:
        return "phase_2_trial"
    if "open label" in text_norm or "open-label" in text_norm:
        return "open_label_trial"
    if "pilot" in text_norm:
        return "pilot_trial"
    if "cohort" in text_norm or "cross sectional" in text_norm or "observational" in text_norm:
        return "observational_study"
    if "rat" in text_norm or "mice" in text_norm or "mouse" in text_norm:
        return "preclinical_study"
    return "pending_curation"


def looks_like_numbered_abstract_title(title: str) -> bool:
    match = NUMBERED_ABSTRACT_TITLE_RE.match(normalize(title))
    return bool(match)


def detect_paper_type(text_norm: str, title: str = "") -> str:
    source_type_text = normalize_text(f"{title} {text_norm[:1000]}")
    if looks_like_numbered_abstract_title(title):
        return "conference_or_poster_abstract"
    if any(normalize_text(kw) in source_type_text for kw in CONFERENCE_OR_POSTER_KEYWORDS):
        return "conference_or_poster_abstract"
    if any(normalize_text(kw) in source_type_text for kw in PROTOCOL_KEYWORDS):
        return "protocol"
    if any(normalize_text(kw) in source_type_text for kw in REVIEWISH_KEYWORDS):
        return "review"
    if any(normalize_text(kw) in source_type_text for kw in NON_COUNTABLE_ARTICLE_KEYWORDS):
        return "other"

    primary_keywords = {
        "randomized",
        "placebo",
        "double blind",
        "double-blind",
        "phase 2",
        "phase 3",
        "clinical trial",
        "open label",
        "open-label",
        "participants",
        "patients",
    }
    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        return "primary_results"
    return "other"


def infer_evidence_level(source_type: str, study_design: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur in {"high", "medium", "low"} and cur != "low":
        return cur
    if source_type in {"review", "meta_analysis"}:
        return "medium"
    if study_design in {"randomized_controlled_trial", "phase_3_trial"}:
        return "high"
    if study_design in {"phase_2_trial", "open_label_trial", "pilot_trial"}:
        return "medium"
    if "case report" in text_norm or "retrospective" in text_norm:
        return "low"
    return cur if cur in {"high", "medium", "low"} else "low"


def infer_system(text_norm: str, current: str) -> str:
    cur = normalize(current)
    clinical_signal = (
        "trial" in text_norm
        or "randomized" in text_norm
        or "placebo" in text_norm
        or "patients" in text_norm
        or "participants" in text_norm
        or "adults" in text_norm
    )
    if clinical_signal:
        return "clinical"
    if cur and cur != "unknown":
        return cur
    if "rat" in text_norm or "mouse" in text_norm or "mice" in text_norm or "rodent" in text_norm:
        return "preclinical"
    if "cohort" in text_norm or "cross sectional" in text_norm or "observational" in text_norm:
        return "observational"
    if "trial" in text_norm or "patients" in text_norm or "participants" in text_norm or "adults" in text_norm:
        return "clinical"
    return "unknown"


def infer_outcome_type(disorder: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur

    d = normalize(disorder).lower()
    negative = any(phrase in text_norm for phrase in {"no significant", "not significant", "did not improve"})

    if "post-traumatic stress disorder" in d or "ptsd" in d:
        return "no significant change in PTSD severity" if negative else "reduces PTSD severity"
    if "treatment-resistant depression" in d or "major depressive disorder" in d or "depression" in d:
        return "no significant change in depressive symptoms" if negative else "reduces depressive symptoms"
    if "alcohol use disorder" in d:
        return "no significant change in alcohol use outcomes" if negative else "reduces heavy drinking outcomes"
    if "tobacco use disorder" in d:
        return "no significant change in tobacco outcomes" if negative else "supports smoking abstinence"
    if "anxiety" in d or "distress associated with life-threatening disease" in d or "life-threatening disease" in d:
        return "no significant change in anxiety/depression symptoms" if negative else "reduces anxiety/depression symptoms"
    return "no significant clinical change" if negative else "improves clinical symptoms"


def infer_result_direction(text_norm: str, outcome_type: str, current: str) -> str:
    cur = normalize(current).lower()
    if cur in {"positive", "null", "negative", "mixed"}:
        return cur

    text = normalize_text(f"{normalize(outcome_type)} {normalize(text_norm)}")
    has_null = any(
        token in text
        for token in {
            "no significant",
            "not significant",
            "no difference",
            "did not improve",
            "did not reduce",
            "not associated",
            "no association",
            "failed to show",
        }
    )
    has_negative = any(
        token in text
        for token in {
            "worsened",
            "worsening",
            "increased symptoms",
            "greater severity",
            "adverse effect",
            "adverse effects",
            "harmful",
            "poorer outcome",
            "poorer outcomes",
        }
    )
    has_positive = any(
        token in text
        for token in {
            "reduced symptoms",
            "reduces",
            "reduction",
            "improved",
            "improves",
            "improvement",
            "response",
            "remission",
            "abstinence",
            "reduced drinking",
            "reduced craving",
            "decreased severity",
            "supports smoking abstinence",
        }
    )

    if sum([has_positive, has_null, has_negative]) >= 2:
        return "mixed"
    if has_null:
        return "null"
    if has_negative:
        return "negative"
    if has_positive:
        return "positive"
    return "unclear"


def infer_outcome_measure(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    for token, label in OUTCOME_MEASURE_PATTERNS:
        if token in text_norm:
            return label
    return ""


def infer_population(disorder: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    disorder_text = normalize(disorder).lower()
    if has_disorder_sample_context(disorder, text_norm):
        return f"adults with {disorder_text}"
    if HEALTHY_VOLUNTEER_RE.search(text_norm):
        return "healthy volunteers"
    if "adolescent" in text_norm or "children" in text_norm:
        return f"adolescents with {disorder_text}"
    if "adult" in text_norm or "participants" in text_norm or "patients" in text_norm:
        return f"adults with {disorder_text}"
    return ""


def decode_pdf_literal(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b != 0x5C:
            out.append(b)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        esc = raw[i]
        i += 1
        if esc in (0x6E,):
            out.append(0x0A)
        elif esc in (0x72,):
            out.append(0x0D)
        elif esc in (0x74,):
            out.append(0x09)
        elif esc in (0x62,):
            out.append(0x08)
        elif esc in (0x66,):
            out.append(0x0C)
        elif esc in (0x28, 0x29, 0x5C):
            out.append(esc)
        elif 0x30 <= esc <= 0x37:
            oct_digits = bytes([esc])
            for _ in range(2):
                if i < len(raw) and 0x30 <= raw[i] <= 0x37:
                    oct_digits += bytes([raw[i]])
                    i += 1
                else:
                    break
            try:
                out.append(int(oct_digits, 8))
            except Exception:
                out.extend(oct_digits)
        else:
            out.append(esc)
    return out.decode("latin-1", errors="ignore")


def decode_pdf_hex(raw: bytes) -> str:
    token = re.sub(rb"\s+", b"", raw)
    if not token:
        return ""
    if len(token) % 2 == 1:
        token += b"0"
    try:
        data = bytes.fromhex(token.decode("ascii"))
    except Exception:
        return ""
    if data.startswith(b"\xfe\xff") or data.startswith(b"\xff\xfe"):
        try:
            return data.decode("utf-16", errors="ignore")
        except Exception:
            pass
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""


def append_pdf_segment(
    segments: List[str],
    seen: Set[str],
    raw: str,
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    line = normalize(" ".join(normalize(raw).split()))
    if not line:
        return chars, False
    key = normalize_text(line)
    if not key or key in seen:
        return chars, False
    seen.add(key)
    segments.append(line)
    chars += len(line)
    return chars, len(segments) >= max_segments or chars >= max_chars


def append_pdf_text(
    segments: List[str],
    seen: Set[str],
    text: str,
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    for line in normalize(text).splitlines():
        chars, done = append_pdf_segment(segments, seen, line, chars, max_segments, max_chars)
        if done:
            return chars, True
    return chars, False


def extract_pdf_segments_with_pdftotext(
    path: Path,
    segments: List[str],
    seen: Set[str],
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    if not shutil.which("pdftotext"):
        return chars, False
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except Exception:
        return chars, False
    if proc.returncode != 0:
        return chars, False
    return append_pdf_text(segments, seen, proc.stdout, chars, max_segments, max_chars)


def extract_pdf_segments_with_pdfplumber(
    path: Path,
    segments: List[str],
    seen: Set[str],
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return chars, False

    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for table in tables:
                    for row in table or []:
                        cells = [normalize(cell) for cell in (row or []) if normalize(cell)]
                        if len(cells) < 2:
                            continue
                        chars, done = append_pdf_segment(
                            segments,
                            seen,
                            " | ".join(cells),
                            chars,
                            max_segments,
                            max_chars,
                        )
                        if done:
                            return chars, True

                try:
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                except Exception:
                    text = ""
                chars, done = append_pdf_text(segments, seen, text, chars, max_segments, max_chars)
                if done:
                    return chars, True
    except Exception:
        return chars, False
    return chars, False


def extract_pdf_segments_with_pymupdf(
    path: Path,
    segments: List[str],
    seen: Set[str],
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    try:
        import fitz  # type: ignore
    except Exception:
        return chars, False
    try:
        try:
            fitz.TOOLS.mupdf_display_errors(False)
            fitz.TOOLS.mupdf_display_warnings(False)
        except Exception:
            pass
        doc = fitz.open(str(path))
        try:
            for page in doc:
                text = page.get_text("text") or ""
                chars, done = append_pdf_text(segments, seen, text, chars, max_segments, max_chars)
                if done:
                    return chars, True
        finally:
            doc.close()
    except Exception:
        return chars, False
    return chars, False


def extract_pdf_segments_with_pypdf(
    path: Path,
    segments: List[str],
    seen: Set[str],
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        for page in reader.pages:
            text = normalize(page.extract_text() or "")
            chars, done = append_pdf_text(segments, seen, text, chars, max_segments, max_chars)
            if done:
                return chars, True
    except Exception:
        return chars, False
    return chars, False


def extract_pdf_segments_from_raw_streams(
    path: Path,
    segments: List[str],
    seen: Set[str],
    chars: int,
    max_segments: int,
    max_chars: int,
) -> Tuple[int, bool]:
    try:
        raw = path.read_bytes()
    except Exception:
        return chars, False

    for match in STREAM_RE.finditer(raw):
        stream = match.group(1)
        stream_candidates: List[bytes] = []
        for wbits in (None, -15):
            try:
                decoded = zlib.decompress(stream) if wbits is None else zlib.decompress(stream, wbits)
                stream_candidates.append(decoded)
                break
            except Exception:
                continue
        if not stream_candidates:
            stream_candidates.append(stream)

        for decoded in stream_candidates:
            for lit in LITERAL_STRING_RE.finditer(decoded):
                token = decode_pdf_literal(lit.group(0)[1:-1])
                chars, done = append_pdf_segment(segments, seen, token, chars, max_segments, max_chars)
                if done:
                    return chars, True
            for hx in HEX_STRING_RE.finditer(decoded):
                token = decode_pdf_hex(hx.group(1))
                if len(normalize(token)) < 2:
                    continue
                chars, done = append_pdf_segment(segments, seen, token, chars, max_segments, max_chars)
                if done:
                    return chars, True
    return chars, False


def extract_pdf_segments(path: Path, max_segments: int = 60000, max_chars: int = 2_000_000) -> List[str]:
    segments: List[str] = []
    seen: Set[str] = set()
    chars = 0
    for extractor in (
        extract_pdf_segments_with_pdftotext,
        extract_pdf_segments_with_pdfplumber,
        extract_pdf_segments_with_pymupdf,
        extract_pdf_segments_with_pypdf,
        extract_pdf_segments_from_raw_streams,
    ):
        chars, done = extractor(path, segments, seen, chars, max_segments, max_chars)
        if done:
            return segments
    return segments


def infer_evidence_location(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur in {"table", "figure", "text", "supplement", "mixed"}:
        return cur
    has_table = " table " in f" {text_norm} "
    has_figure = " figure " in f" {text_norm} "
    if has_table and has_figure:
        return "mixed"
    if has_table:
        return "table"
    if has_figure:
        return "figure"
    return "text"


def choose_pdf_locator(segments: List[str], disorder: str, outcome_measure: str) -> str:
    d_norm = normalize_text(disorder)
    o_norm = normalize_text(outcome_measure)
    key_terms = {term for term in (d_norm, o_norm) if term}
    if "post traumatic stress disorder" in d_norm:
        key_terms.add("ptsd")
    if "major depressive disorder" in d_norm or "depression" in d_norm:
        key_terms.add("depress")
    key_terms.update({"randomized", "placebo", "response", "remission", "effect size", "p value"})

    for line in segments[:12000]:
        line_norm = normalize_text(line)
        if not line_norm:
            continue
        if any(term and term in line_norm for term in key_terms):
            snippet = text_snippet(line, max_chars=170)
            if snippet:
                return f"PDF snippet: {snippet}"

    fallback = text_snippet(" ".join(segments[:30]), max_chars=170)
    if fallback:
        return f"PDF snippet: {fallback}"
    return "PDF full text reviewed"


def main() -> int:
    ensure_pdf_runtime()

    parser = argparse.ArgumentParser(description="Autofill disorder stubs from local PDF full text")
    parser.add_argument("--dataset", choices=["disorder"], required=True)
    parser.add_argument("--status-filter", default="pending_curation", help="Only process rows with this status")
    parser.add_argument("--all-statuses", action="store_true", help="Ignore status filter")
    parser.add_argument("--apply", action="store_true", help="Write updates to stub files")
    parser.add_argument("--mark-ready", action="store_true", help="Set clean rows to ready_for_promotion")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for faster trial runs")
    parser.add_argument("--progress-every", type=int, default=20, help="Print progress every N rows")
    parser.add_argument("--max-segments-per-pdf", type=int, default=70000)
    parser.add_argument("--max-chars-per-pdf", type=int, default=2_000_000)
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/pdf_autofill_report_disorder.json)",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"pdf_autofill_report_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    paper_db = load_json_array(cfg["paper_db_json"])
    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    paper_by_doi: Dict[str, dict] = {}
    for row in paper_db:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            paper_by_doi[doi] = row

    considered = 0
    updated = 0
    matched_pdf = 0
    extracted_text = 0
    ready_marked = 0
    no_pdf = 0
    extraction_failures = 0
    rows_report: List[dict] = []
    out_rows: List[dict] = []
    pdf_cache: Dict[str, List[str]] = {}

    for idx, stub in enumerate(stubs, start=1):
        status = normalize(stub.get("stub_status", ""))
        if not args.all_statuses and status != args.status_filter:
            out_rows.append(stub)
            continue
        if status == "excluded_not_relevant":
            out_rows.append(stub)
            continue
        if args.limit and considered >= args.limit:
            out_rows.append(stub)
            continue

        considered += 1
        new_row = dict(stub)
        changed_fields: List[str] = []
        doi = normalize_doi(stub.get("study_doi", "")).lower()
        paper = paper_by_doi.get(doi)
        pdf_path = Path(normalize(paper.get("pdf_local_path", ""))) if paper else Path("")

        if not paper or not normalize(paper.get("pdf_local_path", "")) or not pdf_path.exists():
            no_pdf += 1
            rows_report.append(
                {
                    "stub_index": idx,
                    "study_doi": normalize(stub.get("study_doi", "")),
                    "pdf_found": False,
                    "changed_fields": [],
                    "reason": "pdf_not_available",
                }
            )
            out_rows.append(new_row)
            continue

        matched_pdf += 1

        if doi in pdf_cache:
            segments = pdf_cache[doi]
        else:
            try:
                segments = extract_pdf_segments(
                    path=pdf_path,
                    max_segments=max(1000, args.max_segments_per_pdf),
                    max_chars=max(100_000, args.max_chars_per_pdf),
                )
            except Exception as err:
                segments = []
                extraction_failures += 1
                rows_report.append(
                    {
                        "stub_index": idx,
                        "study_doi": normalize(stub.get("study_doi", "")),
                        "pdf_found": True,
                        "changed_fields": [],
                        "reason": f"pdf_parse_failed: {type(err).__name__}",
                    }
                )
                out_rows.append(new_row)
                continue
            pdf_cache[doi] = segments

        if segments:
            extracted_text += 1
        else:
            extraction_failures += 1
            rows_report.append(
                {
                    "stub_index": idx,
                    "study_doi": normalize(stub.get("study_doi", "")),
                    "pdf_found": True,
                    "changed_fields": [],
                    "reason": "no_text_segments_extracted",
                }
            )
            out_rows.append(new_row)
            continue

        title = normalize(paper.get("study_title", ""))
        full_text = " ".join(segments[:6000])
        text_norm = normalize_text(f"{title} {full_text}")
        source_type = normalize(new_row.get("source_type", ""))
        inferred_paper_type = detect_paper_type(text_norm, title=title)
        if normalize(new_row.get("paper_type", "")) != inferred_paper_type:
            new_row["paper_type"] = inferred_paper_type
            changed_fields.append("paper_type")

        for key_stub, key_paper in (
            ("study_title", "study_title"),
            ("authors", "authors"),
            ("study_year", "study_year"),
        ):
            if not normalize(new_row.get(key_stub, "")) and normalize(paper.get(key_paper, "")):
                new_row[key_stub] = paper.get(key_paper, "")
                changed_fields.append(key_stub)

        if inferred_paper_type == "conference_or_poster_abstract":
            if normalize(new_row.get("access_level", "")) != "abstract_only":
                new_row["access_level"] = "abstract_only"
                changed_fields.append("access_level")
        elif normalize(new_row.get("access_level", "")) != "full_text_seen":
            new_row["access_level"] = "full_text_seen"
            changed_fields.append("access_level")

        inferred_loc = infer_evidence_location(text_norm, new_row.get("evidence_location", ""))
        if inferred_loc and normalize(new_row.get("evidence_location", "")) != inferred_loc:
            new_row["evidence_location"] = inferred_loc
            changed_fields.append("evidence_location")

        if normalize(new_row.get("paper_type", "")) == "primary_results":
            inferred_outcome_type = infer_outcome_type(
                new_row.get("disorder", ""),
                text_norm,
                new_row.get("outcome_type", ""),
            )
            if inferred_outcome_type and normalize(new_row.get("outcome_type", "")) != inferred_outcome_type:
                new_row["outcome_type"] = inferred_outcome_type
                changed_fields.append("outcome_type")

        inferred_measure = infer_outcome_measure(text_norm, new_row.get("outcome_measure", ""))
        if inferred_measure and normalize(new_row.get("outcome_measure", "")) != inferred_measure:
            new_row["outcome_measure"] = inferred_measure
            changed_fields.append("outcome_measure")

        inferred_population = infer_population(new_row.get("disorder", ""), text_norm, new_row.get("population", ""))
        if inferred_population and normalize(new_row.get("population", "")) != inferred_population:
            new_row["population"] = inferred_population
            changed_fields.append("population")

        inferred_design = infer_study_design(source_type, text_norm)
        if normalize(new_row.get("study_design", "")).lower() in {"", "pending_curation", "unknown", "unspecified"}:
            if inferred_design and normalize(new_row.get("study_design", "")) != inferred_design:
                new_row["study_design"] = inferred_design
                changed_fields.append("study_design")

        inferred_system = infer_system(text_norm, new_row.get("system", ""))
        if inferred_system and normalize(new_row.get("system", "")) != inferred_system:
            new_row["system"] = inferred_system
            changed_fields.append("system")

        inferred_level = infer_evidence_level(
            source_type=source_type,
            study_design=normalize(new_row.get("study_design", "")),
            text_norm=text_norm,
            current=normalize(new_row.get("evidence_level", "")),
        )
        if inferred_level and normalize(new_row.get("evidence_level", "")) != inferred_level:
            new_row["evidence_level"] = inferred_level
            changed_fields.append("evidence_level")

        inferred_direction = (
            infer_result_direction(
                text_norm=text_norm,
                outcome_type=normalize(new_row.get("outcome_type", "")),
                current=normalize(new_row.get("result_direction", "")),
            )
            if normalize(new_row.get("paper_type", "")) == "primary_results"
            else "unclear"
        )
        if inferred_direction and normalize(new_row.get("result_direction", "")) != inferred_direction:
            new_row["result_direction"] = inferred_direction
            changed_fields.append("result_direction")

        if is_weak_locator(new_row.get("evidence_locator", "")):
            locator = choose_pdf_locator(
                segments=segments,
                disorder=normalize(new_row.get("disorder", "")),
                outcome_measure=normalize(new_row.get("outcome_measure", "")),
            )
            new_row["evidence_locator"] = locator
            changed_fields.append("evidence_locator")

        new_notes = append_note(new_row.get("notes", ""), "Full-text PDF autofill for disorder fields")
        if normalize(new_notes) != normalize(new_row.get("notes", "")):
            new_row["notes"] = new_notes
            changed_fields.append("notes")

        blocker_fields, blockers = evaluate_row(
            row=new_row,
            required=required,
            enums=enums,
            types=types,
            one_of_groups=one_of_groups,
            allowed_keys=allowed_keys,
        )

        if normalize(new_row.get("paper_type", "")) != "primary_results":
            blocker_fields = sorted(set(blocker_fields) | {"paper_type"})
            blockers.append({"field": "paper_type", "reason": "not_primary_results"})

        if args.mark_ready and not blockers:
            if normalize(new_row.get("stub_status", "")) != "ready_for_promotion":
                new_row["stub_status"] = "ready_for_promotion"
                changed_fields.append("stub_status")
                ready_marked += 1

        if changed_fields:
            updated += 1

        rows_report.append(
            {
                "stub_index": idx,
                "study_doi": normalize(stub.get("study_doi", "")),
                "pdf_found": True,
                "changed_fields": sorted(set(changed_fields)),
                "blocker_count_after": len(blockers),
                "blocker_fields_after": blocker_fields,
            }
        )
        out_rows.append(new_row)

        if args.progress_every > 0 and (considered % args.progress_every == 0):
            pct = considered / max(1, (args.limit if args.limit else len(stubs))) * 100.0
            print(
                "PROGRESS: pdf_disorder_autofill "
                f"{considered} rows ({pct:.1f}%) "
                f"pdf={matched_pdf} text={extracted_text} updated={updated} ready={ready_marked}",
                flush=True,
            )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "status_filter": "*" if args.all_statuses else args.status_filter,
        "mark_ready": args.mark_ready,
        "apply": args.apply,
        "counts": {
            "stubs_total": len(stubs),
            "considered": considered,
            "rows_with_pdf": matched_pdf,
            "rows_with_text": extracted_text,
            "updated_rows": updated,
            "ready_marked": ready_marked,
            "no_pdf": no_pdf,
            "extraction_failures": extraction_failures,
        },
        "rows": rows_report,
    }

    if args.apply:
        write_json(cfg["stubs_json"], out_rows)
        write_csv(cfg["stubs_csv"], out_rows)

    write_json(report_path, report)
    print(f"Dataset: {args.dataset}")
    print(f"Considered rows: {considered}")
    print(f"Rows with PDF: {matched_pdf}")
    print(f"Rows with extracted text: {extracted_text}")
    print(f"Updated rows: {updated}")
    if args.mark_ready:
        print(f"Marked ready: {ready_marked}")
    print(f"No PDF rows: {no_pdf}")
    print(f"Extraction failures: {extraction_failures}")
    if args.apply:
        print(f"Stubs JSON: {cfg['stubs_json']}")
        print(f"Stubs CSV: {cfg['stubs_csv']}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
