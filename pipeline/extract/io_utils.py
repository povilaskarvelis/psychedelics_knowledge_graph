"""Shared extraction JSONL and text helpers."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


SYSTEM_NORMALIZATION = {
    "in vitro": "in_vitro",
    "in-vitro": "in_vitro",
    "in vivo": "in_vivo",
    "in-vivo": "in_vivo",
    "ex vivo": "ex_vivo",
    "ex-vivo": "ex_vivo",
    "not applicable": "not_applicable",
    "not_applicable": "not_applicable",
}


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def source_text_hashes(stored_abstract: object, packet: dict | None) -> dict:
    """The texts a task sends, by the hashes the verdict table names them with.

    ``artifact_sha256`` is the full-text file the packet was built from, empty
    when the task reads no packet. ``abstract_sha256`` is the record's abstract
    as stored, before whitespace is collapsed for the prompt; identity decisions
    name abstracts by this hash.
    """
    provenance = (packet or {}).get("fulltext_provenance", {})
    missing = stored_abstract is None or (isinstance(stored_abstract, float) and math.isnan(stored_abstract))
    abstract = "" if missing else normalize(stored_abstract)
    return {
        "artifact_sha256": normalize(provenance.get("artifact_sha256", "")) if isinstance(provenance, dict) else "",
        "abstract_sha256": hashlib.sha256(abstract.encode("utf-8")).hexdigest() if abstract else "",
    }


def task_text_hashes(task: dict, output_task_id: object) -> dict:
    """Finding-row fields naming the texts a secondary-literature output was read from.

    They are filled only when the output belongs to this task: the task ID fixes
    the text that was sent. Otherwise the text is unknown and they stay empty.
    """
    source = task.get("source", {}) if isinstance(task.get("source"), dict) else {}
    same_task = bool(normalize(output_task_id)) and normalize(task.get("task_id", "")) == normalize(output_task_id)
    return {
        "source_artifact_sha256": normalize(source.get("artifact_sha256", "")) if same_task else "",
        "source_abstract_sha256": normalize(source.get("abstract_sha256", "")) if same_task else "",
    }


def secondary_packet_text(task: dict, packet: dict | None) -> str:
    """The article text of a review or meta-analysis task, after checking it is the text the task was built on."""
    if packet is None:
        raise ValueError(f"Missing article packet for {task.get('study_doi')}")
    text = "\n\n".join(text_parts_from_packet(packet)).strip()
    source = task.get("source", {}) if isinstance(task.get("source"), dict) else {}
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != normalize(source.get("source_fingerprint", "")):
        raise ValueError(f"The article packet for {task.get('study_doi')} is not the one the task was built on; rebuild the tasks")
    return text


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def metadata_text_parts(metadata: dict) -> list[str]:
    parts = []
    for label, key in [
        ("Publication type", "publication_type"),
        ("Journal", "study_journal"),
        ("Publication year", "study_year"),
        ("Trial registry IDs", "trial_registry_ids"),
        ("Funders", "funders"),
        ("MeSH terms", "mesh_terms"),
        ("Keywords", "keywords"),
    ]:
        value = metadata.get(key)
        if isinstance(value, list):
            text = " | ".join(normalize(item) for item in value if normalize(item))
        else:
            text = normalize(value)
        if text:
            parts.append(f"{label}: {text}")
    return parts


def text_parts_from_packet(packet: dict) -> list[str]:
    parts = []
    metadata = packet.get("paper_metadata", {}) if isinstance(packet.get("paper_metadata"), dict) else {}
    parts.extend(metadata_text_parts(metadata))
    title = normalize(metadata.get("study_title", ""))
    abstract = normalize(metadata.get("abstract", ""))
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")

    for chunk in packet.get("llm_chunks", []) if isinstance(packet.get("llm_chunks"), list) else []:
        if not isinstance(chunk, dict):
            continue
        text = normalize(chunk.get("text", ""))
        if not text:
            continue
        chunk_id = normalize(chunk.get("chunk_id", ""))
        heading = normalize(chunk.get("heading", ""))
        label = " ".join(part for part in [chunk_id, heading] if part)
        parts.append(f"[{label}] {text}" if label else text)

    for table in packet.get("tables", []) if isinstance(packet.get("tables"), list) else []:
        if not isinstance(table, dict):
            continue
        text = normalize(table.get("text", ""))
        caption = normalize(table.get("caption", ""))
        label = normalize(table.get("table_id", "")) or normalize(table.get("label", ""))
        if text or caption:
            parts.append(f"[{label}] {caption} {text}".strip())

    for figure in packet.get("figures", []) if isinstance(packet.get("figures"), list) else []:
        if not isinstance(figure, dict):
            continue
        text = normalize(figure.get("text", ""))
        caption = normalize(figure.get("caption", ""))
        label = normalize(figure.get("figure_id", "")) or normalize(figure.get("label", ""))
        if text or caption:
            parts.append(f"[{label}] {caption} {text}".strip())
    return parts
