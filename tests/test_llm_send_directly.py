import json
from types import SimpleNamespace

from pipeline import llm


class FakeResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **body):
        self.calls += 1
        if body["input"] == "fail":
            raise RuntimeError("provider error")
        return SimpleNamespace(model_dump=lambda mode: {"output_text": "{}", "usage": {"input_tokens": 10, "output_tokens": 5}})


def test_batch_request_file_is_sent_directly_in_batch_output_format(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "PIPELINE_STATE", tmp_path / "no_state.json")
    requests = tmp_path / "requests.jsonl"
    rows = [llm.batch_line(key, {"model": llm.DEFAULT_MODEL, "input": value, "max_output_tokens": 100})
            for key, value in [("a", "ok"), ("b", "fail")]]
    requests.write_text("".join(json.dumps(row) + "\n" for row in rows))
    api = SimpleNamespace(responses=FakeResponses())

    report = llm.send_directly(api, requests, tmp_path / "results.jsonl", tmp_path / "responses", workers=2)
    results = {row["custom_id"]: row["response"] for row in map(json.loads, (tmp_path / "results.jsonl").open())}

    assert report == {"requests": 2, "errors": 1}
    assert results["a"]["status_code"] == 200 and results["b"]["status_code"] is None
    llm.send_directly(api, requests, tmp_path / "results.jsonl", tmp_path / "responses")
    assert api.responses.calls == 2
