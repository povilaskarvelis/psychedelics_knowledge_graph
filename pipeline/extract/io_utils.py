"""Shared extraction JSONL and text helpers."""

from __future__ import annotations

import json
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
