import json
from pathlib import Path

import pytest

from pipeline.review.build_domain_routing_batch_queue import part_paths
from pipeline.review.repack_domain_routing_batch_queue import repack_pending_queue


def make_queue(tmp_path):
    parts = []
    for n in range(1, 5):
        paths = part_paths("test", n, tmp_path)
        records, lines = [], []
        for i in range(2 * n - 1, 2 * n + 1):
            records.append(dict(key=f"key-{i}", doi=f"10.example/{i}", input_row_index=i))
            lines.append(json.dumps(dict(custom_id=f"key-{i}", body=dict(model="gpt-6-luna", input=f"Paper {i}"))) + "\n")
        Path(paths["batch_requests_jsonl"]).write_text("".join(lines))
        Path(paths["manifest_json"]).write_text(json.dumps(dict(records=records, inputs={}, outputs={}, summary={})))
        parts.append(dict(part=n, requests=2, approx_input_tokens_char4=10, **paths))
    # Even an interrupted submission with an unknown remote outcome must stay intact.
    Path(parts[0]["job_json"]).write_text('{"status": "uploaded"}')
    queue = dict(name="test", summary=dict(records=8, parts=4), parts=parts)
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(queue))
    return path, queue


def test_repack_preserves_submitted_attempt_and_exact_pending_requests(tmp_path):
    path, original = make_queue(tmp_path)
    pending_bytes = b"".join(Path(p["batch_requests_jsonl"]).read_bytes() for p in original["parts"][1:])
    report = repack_pending_queue(path, tmp_path / "repacked", max_bytes=10_000, max_requests=4)
    queue = json.loads(path.read_text())
    assert report["submitted_parts_preserved"] == 1
    assert report["pending_parts_before"] == 3
    assert report["pending_parts_after"] == 2
    assert report["pending_papers"] == 6
    assert queue["parts"][0] == original["parts"][0]
    assert [p["requests"] for p in queue["parts"]] == [2, 4, 2]
    assert b"".join(Path(p["batch_requests_jsonl"]).read_bytes() for p in queue["parts"][1:]) == pending_bytes
    for p in queue["parts"][1:]:
        assert not Path(p["job_json"]).exists()
        manifest = json.loads(Path(p["manifest_json"]).read_text())
        assert len(manifest["records"]) == p["requests"]
        assert manifest["inputs"]["raw_jsonl"] == p["raw_jsonl"]
    assert json.loads((tmp_path / "repacked/queue.before.json").read_text()) == original


def test_repack_respects_bytes_and_rejects_duplicate_requests_before_switching(tmp_path):
    path, original = make_queue(tmp_path)
    line_size = len(Path(original["parts"][1]["batch_requests_jsonl"]).read_bytes()) // 2
    repack_pending_queue(path, tmp_path / "small", max_bytes=3 * line_size, max_requests=50_000)
    queue = json.loads(path.read_text())
    assert all(Path(p["batch_requests_jsonl"]).stat().st_size <= 3 * line_size for p in queue["parts"][1:])
    request_path = Path(queue["parts"][-1]["batch_requests_jsonl"])
    lines = request_path.read_text().splitlines(keepends=True)
    row = json.loads(lines[0]); row["custom_id"] = "key-1"
    lines[0] = json.dumps(row) + "\n"
    request_path.write_text("".join(lines))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Duplicate"):
        repack_pending_queue(path, tmp_path / "bad")
    assert path.read_bytes() == before
    assert not (tmp_path / "bad").exists()
