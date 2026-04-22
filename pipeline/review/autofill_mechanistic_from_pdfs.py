#!/usr/bin/env python3
"""Autofill mechanistic stubs from local PDF full text."""

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
import tempfile
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from pipeline.review.pdf_runtime import ensure_pdf_runtime
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from pdf_runtime import ensure_pdf_runtime

ROOT = Path(__file__).resolve().parents[2]

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.ERROR)

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "schema": ROOT / "schema" / "claims.schema.json",
    }
}

STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
LITERAL_STRING_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")
HEX_STRING_RE = re.compile(rb"<([0-9A-Fa-f\s]+)>")

TYPE_VAL_UNIT_RE = re.compile(
    r"\b(?P<atype>Ki|Kd|IC50|EC50|EC90)\b"
    r"[^a-z0-9]{0,20}"
    r"(?P<cmp>[<>≤≥])?\s*(?P<val>\d+(?:\.\d+)?)"
    r"(?:\s*[±\u00b1]\s*\d+(?:\.\d+)?)?\s*(?P<unit>pM|nM|uM|µM|μM|mM|M)\b",
    re.I,
)
VAL_UNIT_TYPE_RE = re.compile(
    r"(?P<cmp>[<>≤≥])?\s*(?P<val>\d+(?:\.\d+)?)"
    r"(?:\s*[±\u00b1]\s*\d+(?:\.\d+)?)?\s*(?P<unit>pM|nM|uM|µM|μM|mM|M)\s*"
    r"(?P<atype>Ki|Kd|IC50|EC50|EC90)\b",
    re.I,
)
VAL_UNIT_RE = re.compile(
    r"(?P<cmp>[<>≤≥])?\s*(?P<val>\d+(?:\.\d+)?)"
    r"(?:\s*[±\u00b1]\s*\d+(?:\.\d+)?)?\s*(?P<unit>pM|nM|uM|µM|μM|mM|M)\b",
    re.I,
)
TYPE_UNIT_HEADER_RE = re.compile(
    r"\b(?P<atype>Ki|Kd|IC50|EC50|EC90)\s*\(\s*(?P<unit>pM|nM|uM|µM|μM|mM|M)\s*\)",
    re.I,
)
AFFINITY_TYPE_HINT_RE = re.compile(r"\b(?:ki|k\s*i|kd|k\s*d|ic50|ec50|ec90)\b", re.I)

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
}

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
    lowered = re.sub(r"[^a-z0-9\s\-\+\.]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def detect_paper_type(text_norm: str, title_norm: str = "") -> str:
    source_type_text = title_norm or text_norm[:1000]
    if any(normalize_text(kw) in source_type_text for kw in CONFERENCE_OR_POSTER_KEYWORDS):
        return "conference_or_poster_abstract"
    if any(normalize_text(kw) in source_type_text for kw in PROTOCOL_KEYWORDS):
        return "protocol"
    if any(normalize_text(kw) in source_type_text for kw in REVIEWISH_KEYWORDS):
        return "review"

    primary_keywords = {
        "binding",
        "affinity",
        "radioligand",
        "assay",
        "ic50",
        "ec50",
        "ki",
        "kd",
        "agonist",
        "antagonist",
        "receptor",
        "transporter",
        "in vitro",
        "in vivo",
    }
    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        return "primary_results"
    return "other"


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


def unit_normalize(raw: str) -> str:
    text = normalize(raw).replace("μ", "u").replace("µ", "u")
    lowered = text.lower()
    if lowered == "pm":
        return "pM"
    if lowered == "nm":
        return "nM"
    if lowered == "um":
        return "uM"
    if lowered == "mm":
        return "mM"
    if lowered == "m":
        return "M"
    return text


def target_aliases(target: str) -> List[str]:
    raw = normalize(target)
    aliases: Set[str] = set()

    norm = normalize_text(raw)
    if norm:
        aliases.add(norm)

    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if match:
        base = normalize_text(match.group(1))
        inside = normalize_text(match.group(2))
        if base:
            aliases.add(base)
        if inside:
            aliases.add(inside)

    normalized_aliases = {normalize_text(item) for item in aliases if normalize_text(item)}
    aliases.update(normalized_aliases)

    for item in list(normalized_aliases):
        ht_match = re.search(r"\b5\s*ht\s*([0-9][a-z]?)\b", item)
        if ht_match:
            code = ht_match.group(1)
            aliases.update(
                {
                    f"5ht{code}",
                    f"5-ht{code}",
                    f"serotonin {code}",
                    f"5 hydroxytryptamine {code}",
                    f"htr{code}",
                }
            )

    lowered = normalize_text(raw)
    if "sert" in lowered or "slc6a4" in lowered:
        aliases.update({"sert", "slc6a4", "serotonin transporter", "5 htt", "5-htt"})
    if "dat" in lowered or "slc6a3" in lowered:
        aliases.update({"dat", "slc6a3", "dopamine transporter"})
    if "net" in lowered or "slc6a2" in lowered:
        aliases.update({"net", "slc6a2", "norepinephrine transporter", "noradrenaline transporter"})
    if "vmat2" in lowered or "slc18a2" in lowered:
        aliases.update({"vmat2", "slc18a2", "vesicular monoamine transporter 2"})
    if "mglur2" in lowered or "grm2" in lowered:
        aliases.update({"mglur2", "grm2", "metabotropic glutamate receptor 2"})
    if "taar1" in lowered:
        aliases.update({"taar1", "trace amine associated receptor 1"})
    if "nmda" in lowered:
        aliases.update({"nmda", "nmda receptor", "n methyl d aspartate receptor", "nmdar", "grin"})
    if "ampa" in lowered:
        aliases.update({"ampa", "ampa receptor", "ampar", "gria"})
    if "sigma 1" in lowered or "sigmar1" in lowered:
        aliases.update({"sigma 1", "sigma-1", "sigmar1", "sigma 1 receptor"})
    if "sigma 2" in lowered or "tmem97" in lowered:
        aliases.update({"sigma 2", "sigma-2", "tmem97", "sigma 2 receptor"})
    if "kappa opioid" in lowered or "oprk1" in lowered:
        aliases.update({"kappa opioid receptor", "kor", "oprk1"})
    if "mu opioid" in lowered or "oprm1" in lowered:
        aliases.update({"mu opioid receptor", "mor", "oprm1"})
    if "delta opioid" in lowered or "oprd1" in lowered:
        aliases.update({"delta opioid receptor", "dor", "oprd1"})

    alpha_match = re.search(r"alpha\s*([12][a-c]?)", lowered)
    if alpha_match and ("adrenergic" in lowered or "adra" in lowered):
        code = alpha_match.group(1)
        aliases.update({f"alpha{code}", f"alpha {code}", f"alpha{code} adrenoceptor", f"alpha{code} adrenergic receptor"})

    beta_match = re.search(r"beta\s*([12])", lowered)
    if beta_match and ("adrenergic" in lowered or "adrb" in lowered):
        code = beta_match.group(1)
        aliases.update({f"beta{code}", f"beta {code}", f"beta{code} adrenoceptor", f"beta{code} adrenergic receptor"})

    muscarinic_match = re.search(r"\bm\s*([1-5])\b", lowered)
    if muscarinic_match and ("muscarinic" in lowered or "chrm" in lowered):
        code = muscarinic_match.group(1)
        aliases.update({f"m{code}", f"m{code} receptor", f"chrm{code}"})

    d_match = re.search(r"\bd\s*([1-5])\b", lowered)
    if d_match and ("receptor" in lowered or "drd" in lowered):
        code = d_match.group(1)
        aliases.update({f"d{code}", f"d{code} receptor", f"drd{code}", f"dopamine d{code} receptor"})

    h_match = re.search(r"\bh\s*([12])\b", lowered)
    if h_match and ("receptor" in lowered or "histamine" in lowered or "hrh" in lowered):
        code = h_match.group(1)
        aliases.update({f"h{code}", f"h{code} receptor", f"hrh{code}", f"histamine h{code} receptor"})

    if "cb1" in lowered or "cnr1" in lowered:
        aliases.update({"cb1", "cb1 receptor", "cnr1", "cannabinoid receptor 1"})
    if "cb2" in lowered or "cnr2" in lowered:
        aliases.update({"cb2", "cb2 receptor", "cnr2", "cannabinoid receptor 2"})

    return sorted({normalize_text(alias) for alias in aliases if normalize_text(alias)})


def decode_pdf_literal(raw: bytes) -> str:
    # Decode PDF literal string escapes (basic subset).
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b != 0x5C:  # backslash
            out.append(b)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        esc = raw[i]
        i += 1
        if esc in (0x6E,):  # n
            out.append(0x0A)
        elif esc in (0x72,):  # r
            out.append(0x0D)
        elif esc in (0x74,):  # t
            out.append(0x09)
        elif esc in (0x62,):  # b
            out.append(0x08)
        elif esc in (0x66,):  # f
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

    # latin-1 keeps bytes reversible and generally works well for PDF text streams
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


def ocr_pdf_segments(
    path: Path,
    max_pages: int,
    max_segments: int,
    max_chars: int,
    lang: str,
    dpi: int = 220,
) -> List[str]:
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        return []

    segments: List[str] = []
    chars = 0
    with tempfile.TemporaryDirectory(prefix="kg_pdf_ocr_") as tmpdir_raw:
        tmpdir = Path(tmpdir_raw)
        prefix = tmpdir / "page"
        raster_cmd = [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            str(max(1, max_pages)),
            "-r",
            str(max(72, dpi)),
            "-png",
            str(path),
            str(prefix),
        ]
        raster = subprocess.run(raster_cmd, capture_output=True, text=True)
        if raster.returncode != 0:
            return []

        images = sorted(tmpdir.glob("page-*.png"))
        for image in images:
            ocr_cmd = [
                "tesseract",
                str(image),
                "stdout",
                "-l",
                lang or "eng",
                "--psm",
                "6",
            ]
            proc = subprocess.run(ocr_cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                continue
            text = normalize(proc.stdout)
            if not text:
                continue
            for line in text.splitlines():
                line = normalize(line)
                if not line:
                    continue
                segments.append(line)
                chars += len(line)
                if len(segments) >= max_segments or chars >= max_chars:
                    return segments
    return segments


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
    cmd = ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
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
        logging.getLogger("pypdf").setLevel(logging.ERROR)
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


def extract_pdf_segments(
    path: Path,
    max_segments: int = 60000,
    max_chars: int = 2_000_000,
    enable_ocr_fallback: bool = True,
    ocr_max_pages: int = 12,
    ocr_lang: str = "eng",
) -> Tuple[List[str], bool]:
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
            return segments, False

    should_ocr = enable_ocr_fallback and (not segments or sum(len(s) for s in segments) < 800 or len(segments) < 40)
    if should_ocr:
        ocr_segments = ocr_pdf_segments(
            path=path,
            max_pages=max(1, ocr_max_pages),
            max_segments=max_segments,
            max_chars=max_chars,
            lang=ocr_lang,
        )
        if ocr_segments:
            for segment in ocr_segments:
                chars, done = append_pdf_segment(segments, seen, segment, chars, max_segments, max_chars)
                if done:
                    return segments, True
            return segments, True

    return segments, False


def infer_assay_type(context: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    low = normalize_text(context)
    if "uptake" in low or "transporter uptake" in low:
        return "uptake inhibition"
    if "radioligand" in low or "binding" in low or "affinity" in low:
        return "radioligand binding"
    if "agonist" in low or "antagonist" in low or "functional" in low:
        return "functional assay"
    return ""


def infer_system(context: str, current: str) -> str:
    cur = normalize(current)
    if cur and cur != "unknown":
        return cur
    low = normalize_text(context)
    if "in vitro" in low or "cell line" in low or "membrane preparation" in low:
        return "in_vitro"
    if "in vivo" in low or "rat" in low or "mouse" in low or "mice" in low:
        return "in_vivo"
    if "ex vivo" in low:
        return "ex_vivo"
    return "unknown"


def infer_study_design_from_assay(assay_type: str, current: str) -> str:
    cur = normalize(current)
    if cur and cur not in {"pending_curation", "unknown", "unspecified"}:
        return cur
    low = normalize_text(assay_type)
    if "uptake" in low:
        return "in_vitro_uptake_assay"
    if "binding" in low:
        return "in_vitro_binding_assay"
    if low:
        return "in_vitro_assay"
    return "pending_curation"


def infer_affinity_type(context: str) -> str:
    raw = normalize(context)
    if re.search(r"\bk\s*i\b|\bki\b", raw, re.I):
        return "Ki"
    if re.search(r"\bk\s*d\b|\bkd\b", raw, re.I):
        return "Kd"
    if re.search(r"\bic50\b", raw, re.I):
        return "IC50"
    if re.search(r"\bec50\b", raw, re.I):
        return "EC50"
    if re.search(r"\bec90\b", raw, re.I):
        return "EC90"
    return "Other"


def to_float(raw: str) -> Optional[float]:
    text = normalize(raw).replace(",", "")
    try:
        return float(text)
    except Exception:
        return None


def extract_candidate_from_segments(
    segments: List[str],
    target_terms: List[str],
    compound_terms: List[str],
    min_score: int,
) -> Optional[dict]:
    candidates: List[dict] = []
    full_text = " ".join(segments)
    full_text = " ".join(full_text.split())

    unique_target_terms = sorted({normalize_text(t) for t in target_terms if normalize_text(t)}, key=len, reverse=True)
    unique_compound_terms = sorted({normalize_text(c) for c in compound_terms if normalize_text(c)}, key=len, reverse=True)

    number_only_re = re.compile(
        r"(?P<cmp>[<>≤≥])?\s*(?P<val>\d+(?:\.\d+)?)"
        r"(?:\s*[±\u00b1]\s*\d+(?:\.\d+)?)?(?:\s*(?P<unit>pM|nM|uM|µM|μM|mM|M))?",
        re.I,
    )

    def add_candidate(
        atype_raw: str,
        val_raw: str,
        unit_raw: str,
        cmp_raw: str,
        local_context: str,
        context: str,
        known_type: bool,
        source: str,
    ) -> None:
        atype = normalize(atype_raw)
        if atype not in {"Ki", "Kd", "IC50", "EC50", "EC90"}:
            atype = infer_affinity_type(context)
        value = to_float(val_raw)
        unit = unit_normalize(unit_raw)
        if value is None:
            return
        if value <= 0.0 or value > 1_000_000:
            return
        if 1900 <= value <= 2100 and unit in {"M", "mM"}:
            return
        if not unit:
            return

        local_norm = normalize_text(local_context)
        context_norm = normalize_text(context)
        has_local_target = any(term in local_norm for term in unique_target_terms)
        has_local_compound = any(term in local_norm for term in unique_compound_terms)
        if not has_local_target:
            return
        has_affinity_context = (
            ("affinity" in context_norm)
            or ("binding" in context_norm)
            or ("inhibition constant" in context_norm)
            or bool(AFFINITY_TYPE_HINT_RE.search(context))
            or source.startswith("table_")
        )
        if not has_affinity_context:
            return

        score = 0
        if known_type:
            score += 6
        if source.startswith("table_"):
            score += 2
        if has_local_target:
            score += 5
        if has_local_compound:
            score += 2
        if has_affinity_context:
            score += 1
        if not known_type and unit == "M":
            return
        if score < min_score:
            return

        candidates.append(
            {
                "score": score,
                "source": source,
                "affinity_type": atype if atype in {"Ki", "Kd", "IC50", "EC50", "EC90"} else "Other",
                "affinity_value": value,
                "affinity_unit": unit,
                "context": context,
                "comparator": normalize(cmp_raw),
            }
        )

    # Pass 1: explicit typed patterns in full text.
    for pattern in (TYPE_VAL_UNIT_RE, VAL_UNIT_TYPE_RE):
        for match in pattern.finditer(full_text):
            start, end = match.span()
            local_context = full_text[max(0, start - 120) : min(len(full_text), end + 120)]
            context = full_text[max(0, start - 260) : min(len(full_text), end + 260)]
            add_candidate(
                atype_raw=normalize(match.groupdict().get("atype", "")),
                val_raw=normalize(match.group("val")),
                unit_raw=normalize(match.group("unit")),
                cmp_raw=normalize(match.groupdict().get("cmp", "")),
                local_context=local_context,
                context=context,
                known_type=True,
                source="typed_fulltext",
            )

    # Pass 2: value+unit patterns in full text; infer type from context.
    for match in VAL_UNIT_RE.finditer(full_text):
        start, end = match.span()
        local_context = full_text[max(0, start - 120) : min(len(full_text), end + 120)]
        context = full_text[max(0, start - 300) : min(len(full_text), end + 300)]
        add_candidate(
            atype_raw="",
            val_raw=normalize(match.group("val")),
            unit_raw=normalize(match.group("unit")),
            cmp_raw=normalize(match.groupdict().get("cmp", "")),
            local_context=local_context,
            context=context,
            known_type=False,
            source="value_unit_fulltext",
        )

    # Pass 3: table-header assisted extraction (e.g., "Ki (nM)" + row value).
    for header in TYPE_UNIT_HEADER_RE.finditer(full_text):
        h_start, h_end = header.span()
        h_type = normalize(header.group("atype"))
        h_unit = normalize(header.group("unit"))
        table_block = full_text[max(0, h_start - 320) : min(len(full_text), h_end + 2200)]
        table_block_norm = normalize_text(table_block)
        if not any(term in table_block_norm for term in unique_target_terms):
            continue

        for term in unique_target_terms:
            if not term:
                continue
            for tmatch in re.finditer(re.escape(term), table_block, re.I):
                t_start, t_end = tmatch.span()
                row = table_block[max(0, t_start - 80) : min(len(table_block), t_end + 220)]
                for nmatch in number_only_re.finditer(row):
                    num_txt = normalize(nmatch.group("val"))
                    num_val = to_float(num_txt)
                    if num_val is None or num_val <= 0.0:
                        continue
                    if 1900 <= num_val <= 2100:
                        continue
                    row_unit = normalize(nmatch.groupdict().get("unit", "")) or h_unit
                    if not row_unit:
                        continue
                    add_candidate(
                        atype_raw=h_type,
                        val_raw=num_txt,
                        unit_raw=row_unit,
                        cmp_raw=normalize(nmatch.groupdict().get("cmp", "")),
                        local_context=row,
                        context=table_block[max(0, t_start - 180) : min(len(table_block), t_end + 280)],
                        known_type=True,
                        source="table_header_row",
                    )

    # Pass 4: token-wise table rows using local segment windows.
    for idx, seg in enumerate(segments):
        seg_norm = normalize_text(seg)
        if not any(term in seg_norm for term in unique_target_terms):
            continue

        row = " ".join(segments[max(0, idx - 2) : min(len(segments), idx + 10)])
        header = " ".join(segments[max(0, idx - 15) : idx + 1])

        found = False
        for pattern in (TYPE_VAL_UNIT_RE, VAL_UNIT_TYPE_RE):
            match = pattern.search(row)
            if not match:
                continue
            add_candidate(
                atype_raw=normalize(match.groupdict().get("atype", "")),
                val_raw=normalize(match.group("val")),
                unit_raw=normalize(match.group("unit")),
                cmp_raw=normalize(match.groupdict().get("cmp", "")),
                local_context=row,
                context=f"{header} {row}",
                known_type=True,
                source="table_row_typed",
            )
            found = True
            break
        if found:
            continue

        row_num = number_only_re.search(row)
        if not row_num:
            continue
        inferred_type = infer_affinity_type(f"{header} {row}")
        if inferred_type == "Other":
            continue
        row_unit = normalize(row_num.groupdict().get("unit", ""))
        if not row_unit:
            h_match = TYPE_UNIT_HEADER_RE.search(header)
            row_unit = normalize(h_match.group("unit")) if h_match else ""
        if not row_unit:
            continue
        add_candidate(
            atype_raw=inferred_type,
            val_raw=normalize(row_num.group("val")),
            unit_raw=row_unit,
            cmp_raw=normalize(row_num.groupdict().get("cmp", "")),
            local_context=row,
            context=f"{header} {row}",
            known_type=True,
            source="table_row_inferred",
        )

    if not candidates:
        return None

    # Prefer strongest score; tie-break typed > table > inferred/other.
    candidates.sort(
        key=lambda c: (
            c["score"],
            1 if c["affinity_type"] != "Other" else 0,
            1 if "typed" in c["source"] else 0,
        ),
        reverse=True,
    )
    return candidates[0]


def main() -> int:
    ensure_pdf_runtime()

    parser = argparse.ArgumentParser(description="Autofill mechanistic stubs from local PDF full text")
    parser.add_argument("--dataset", choices=["mechanistic"], required=True)
    parser.add_argument("--status-filter", default="pending_curation", help="Only process rows with this status")
    parser.add_argument("--all-statuses", action="store_true", help="Ignore status filter")
    parser.add_argument("--apply", action="store_true", help="Write updates to stub files")
    parser.add_argument("--mark-ready", action="store_true", help="Set clean rows to ready_for_promotion")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for faster trial runs")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N rows")
    parser.add_argument("--min-score", type=int, default=6, help="Minimum extraction confidence score")
    parser.add_argument("--max-segments-per-pdf", type=int, default=60000)
    parser.add_argument("--max-chars-per-pdf", type=int, default=2_000_000)
    parser.add_argument(
        "--disable-ocr-fallback",
        action="store_true",
        help="Disable OCR fallback (pdftoppm+tesseract) for scanned PDFs",
    )
    parser.add_argument("--ocr-max-pages", type=int, default=12, help="Max PDF pages for OCR fallback")
    parser.add_argument("--ocr-lang", default="eng", help="Tesseract OCR language (default: eng)")
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/pdf_autofill_report_mechanistic.json)",
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

    pdf_cache: Dict[str, List[str]] = {}
    considered = 0
    updated = 0
    matched_pdf = 0
    extracted_text = 0
    candidates_found = 0
    ready_marked = 0
    no_pdf = 0
    extraction_failures = 0
    ocr_rows = 0
    rows_report: List[dict] = []
    out_rows: List[dict] = []

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
                    "candidate_found": False,
                    "reason": "pdf_not_available",
                    "changed_fields": [],
                }
            )
            out_rows.append(new_row)
            continue

        matched_pdf += 1

        if doi in pdf_cache:
            segments = pdf_cache[doi]
        else:
            try:
                segments, used_ocr = extract_pdf_segments(
                    path=pdf_path,
                    max_segments=max(1000, args.max_segments_per_pdf),
                    max_chars=max(100_000, args.max_chars_per_pdf),
                    enable_ocr_fallback=not args.disable_ocr_fallback,
                    ocr_max_pages=max(1, args.ocr_max_pages),
                    ocr_lang=args.ocr_lang,
                )
                if used_ocr:
                    ocr_rows += 1
            except Exception as err:
                segments = []
                extraction_failures += 1
                rows_report.append(
                    {
                        "stub_index": idx,
                        "study_doi": normalize(stub.get("study_doi", "")),
                        "pdf_found": True,
                        "candidate_found": False,
                        "reason": f"pdf_parse_failed: {type(err).__name__}",
                        "changed_fields": [],
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
                    "candidate_found": False,
                    "reason": "no_text_segments_extracted",
                    "changed_fields": [],
                }
            )
            out_rows.append(new_row)
            continue

        target_terms = target_aliases(new_row.get("target", ""))
        compound_norm = normalize_text(new_row.get("compound", ""))
        compound_terms = [compound_norm] if compound_norm else []
        if compound_norm == "s ketamine":
            compound_terms.extend(["esketamine", "s-ketamine", "ketamine"])

        candidate = extract_candidate_from_segments(
            segments=segments,
            target_terms=target_terms,
            compound_terms=compound_terms,
            min_score=max(0, args.min_score),
        )

        if not candidate:
            rows_report.append(
                {
                    "stub_index": idx,
                    "study_doi": normalize(stub.get("study_doi", "")),
                    "pdf_found": True,
                    "candidate_found": False,
                    "reason": "no_affinity_candidate_found",
                    "changed_fields": [],
                }
            )
            out_rows.append(new_row)
            continue

        candidates_found += 1

        if normalize(new_row.get("affinity_value", "")) == "":
            new_row["affinity_value"] = candidate["affinity_value"]
            changed_fields.append("affinity_value")
        if normalize(new_row.get("affinity_unit", "")) == "":
            new_row["affinity_unit"] = candidate["affinity_unit"]
            changed_fields.append("affinity_unit")

        cur_aff_type = normalize(new_row.get("affinity_type", ""))
        if cur_aff_type in {"", "Other"} and candidate["affinity_type"] in {"Ki", "Kd", "IC50", "EC50", "EC90"}:
            new_row["affinity_type"] = candidate["affinity_type"]
            changed_fields.append("affinity_type")

        inferred_assay = infer_assay_type(candidate["context"], new_row.get("assay_type", ""))
        if inferred_assay and normalize(new_row.get("assay_type", "")) != inferred_assay:
            new_row["assay_type"] = inferred_assay
            changed_fields.append("assay_type")

        title = normalize(paper.get("study_title", ""))
        all_text = " ".join(segments[:5000])
        text_norm = normalize_text(f"{title} {all_text}")
        inferred_paper_type = detect_paper_type(text_norm, title_norm=normalize_text(title))
        if normalize(new_row.get("paper_type", "")) != inferred_paper_type:
            new_row["paper_type"] = inferred_paper_type
            changed_fields.append("paper_type")

        inferred_system = infer_system(all_text, new_row.get("system", ""))
        if inferred_system and normalize(new_row.get("system", "")) != inferred_system:
            new_row["system"] = inferred_system
            changed_fields.append("system")

        inferred_design = infer_study_design_from_assay(new_row.get("assay_type", ""), new_row.get("study_design", ""))
        if inferred_design and normalize(new_row.get("study_design", "")) != inferred_design:
            new_row["study_design"] = inferred_design
            changed_fields.append("study_design")

        if normalize(new_row.get("access_level", "")) != "full_text_seen":
            new_row["access_level"] = "full_text_seen"
            changed_fields.append("access_level")
        if normalize(new_row.get("evidence_location", "")) in {"", "unknown", "abstract"}:
            new_row["evidence_location"] = "text"
            changed_fields.append("evidence_location")

        snippet = normalize(candidate["context"])[:180]
        locator = f"PDF extraction snippet: {snippet}" if snippet else "PDF extraction snippet"
        if normalize(new_row.get("evidence_locator", "")).lower() in {"", "unspecified", "unknown", "abstract"}:
            new_row["evidence_locator"] = locator
            changed_fields.append("evidence_locator")

        if normalize(new_row.get("evidence_level", "")) in {"", "low"}:
            new_row["evidence_level"] = "medium"
            changed_fields.append("evidence_level")

        note = "Full-text PDF autofill for mechanistic affinity fields"
        if candidate["comparator"]:
            note = f"{note} (comparator `{candidate['comparator']}` retained in context only)"
        new_notes = append_note(new_row.get("notes", ""), note)
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
                "candidate_found": True,
                "candidate": {
                    "source": candidate.get("source", ""),
                    "affinity_type": candidate["affinity_type"],
                    "affinity_value": candidate["affinity_value"],
                    "affinity_unit": candidate["affinity_unit"],
                    "score": candidate["score"],
                },
                "changed_fields": sorted(set(changed_fields)),
                "blocker_count_after": len(blockers),
                "blocker_fields_after": blocker_fields,
            }
        )
        out_rows.append(new_row)

        if args.progress_every > 0 and (considered % args.progress_every == 0):
            pct = considered / max(1, (args.limit if args.limit else len(stubs))) * 100.0
            print(
                "PROGRESS: pdf_autofill "
                f"{considered} rows ({pct:.1f}%) "
                f"pdf={matched_pdf} text={extracted_text} candidates={candidates_found} "
                f"updated={updated} ready={ready_marked} ocr_rows={ocr_rows}",
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
            "candidates_found": candidates_found,
            "updated_rows": updated,
            "ready_marked": ready_marked,
            "no_pdf": no_pdf,
            "extraction_failures": extraction_failures,
            "ocr_rows": ocr_rows,
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
    print(f"Candidates found: {candidates_found}")
    print(f"Updated rows: {updated}")
    if args.mark_ready:
        print(f"Marked ready: {ready_marked}")
    print(f"No PDF rows: {no_pdf}")
    print(f"Extraction failures: {extraction_failures}")
    print(f"OCR rows: {ocr_rows}")
    if args.apply:
        print(f"Stubs JSON: {cfg['stubs_json']}")
        print(f"Stubs CSV: {cfg['stubs_csv']}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
