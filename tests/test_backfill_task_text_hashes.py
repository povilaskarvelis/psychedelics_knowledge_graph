"""Tasks built before tasks recorded their texts get hashes only where the text can be shown."""
import hashlib
import json
import os
from collections import Counter

from pipeline.extract.backfill_task_text_hashes import backfill_task, load_packets
from pipeline.extract.build_extraction_tasks import canonical_sha256, stable_packet_payload
from pipeline.extract.build_review_relationship_tasks import packet_text_fingerprint


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def setup(tmp_path, *, built: str = "2030-01-01T00:00:00+00:00"):
    """A full-text file written in 2020 and the packet file holding a packet built from it."""
    artifact = tmp_path / "paper.json"
    artifact.write_text("{}")
    os.utime(artifact, (1_600_000_000, 1_600_000_000))
    packet = {
        "packet_id": "article:10.1000/x", "study_doi": "10.1000/x", "created_at_utc": built,
        "fulltext_provenance": {"artifact_path": str(artifact)}, "llm_chunks": [{"text": "Results."}],
    }
    packet_path = tmp_path / "packets.jsonl"
    packet_path.write_text(json.dumps(packet) + "\n")
    return packet, packet_path


def primary_task(packet: dict, packet_path, sent_abstract: str = "An  abstract\nwith breaks.") -> dict:
    text_source = {"mode": "full_text_packet", "packet_source_path": str(packet_path), "packet_id": packet["packet_id"]}
    metadata = {"study_title": "A study", "abstract": sent_abstract}
    # Fingerprinted as tasks were before 1 November: the packet with its build time.
    text_source["source_fingerprint"] = canonical_sha256({
        "mode": "full_text_packet", "packet": stable_packet_payload(packet, frozenset({"_packet_source_path", "generated_at_utc"})),
    })
    return {"task_id": "t", "study_doi": "10.1000/x", "paper_metadata": metadata, "text_source": text_source}


def backfill(task: dict, abstracts: dict | None = None, counts: Counter | None = None) -> dict:
    return backfill_task(task, load_packets([task]), abstracts or {}, Counter() if counts is None else counts)


def test_primary_task_names_the_file_its_own_packet_was_built_from(tmp_path):
    packet, packet_path = setup(tmp_path)
    stored = "An abstract with breaks."
    task = backfill(primary_task(packet, packet_path), {"10.1000/x": stored})
    assert task["text_source"]["artifact_sha256"] == hashlib.sha256(b"{}").hexdigest()
    # The abstract is named as stored when it is the abstract that was sent.
    assert task["text_source"]["abstract_sha256"] == sha(stored)


def test_no_file_is_named_when_the_packet_or_the_file_changed(tmp_path):
    packet, packet_path = setup(tmp_path)
    task = primary_task(packet, packet_path)
    packet_path.write_text(json.dumps({**packet, "llm_chunks": [{"text": "Other results."}]}) + "\n")
    counts = Counter()
    assert backfill(task, counts=counts)["text_source"]["artifact_sha256"] == ""
    assert counts["named_packet_fingerprint_differs"] == 1

    packet, packet_path = setup(tmp_path, built="2019-01-01T00:00:00+00:00")
    counts = Counter()
    changed = backfill(primary_task(packet, packet_path), counts=counts)
    assert changed["text_source"]["artifact_sha256"] == ""
    assert counts["full_text_file_changed_after_packet"] == 1
    # Another abstract is stored now: the one sent is not named.
    assert changed["text_source"]["abstract_sha256"] == ""


def test_secondary_task_names_the_file_when_its_packet_text_is_the_same(tmp_path):
    packet, packet_path = setup(tmp_path)
    task = {
        "task_id": "reviewrel:1", "study_doi": "10.1000/x", "paper_metadata": {"abstract": ""},
        "source": {"kind": "article_text", "packet_path": str(packet_path), "packet_id": packet["packet_id"],
                   "source_fingerprint": packet_text_fingerprint(packet)[0]},
    }
    assert backfill(task)["source"]["artifact_sha256"] == hashlib.sha256(b"{}").hexdigest()


def test_task_that_records_its_texts_is_left_unchanged():
    task = {"task_id": "t", "text_source": {"artifact_sha256": "a" * 64, "abstract_sha256": ""}}
    assert backfill_task(task, {}, {}, Counter()) is task


def test_a_rebuilt_packet_file_is_searched_in_its_kept_copies(tmp_path):
    packet, packet_path = setup(tmp_path)
    task = primary_task(packet, packet_path)
    kept = tmp_path / "kept_packets.jsonl"
    kept.write_text(packet_path.read_text())
    packet_path.write_text(json.dumps({**packet, "created_at_utc": "2031-01-01T00:00:00+00:00"}) + "\n")
    assert backfill(task)["text_source"]["artifact_sha256"] == ""
    named = backfill_task(task, load_packets([task], [kept]), {}, Counter())
    assert named["text_source"]["artifact_sha256"] == hashlib.sha256(b"{}").hexdigest()
