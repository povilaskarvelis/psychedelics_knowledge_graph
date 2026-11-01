import json
import tempfile
import unittest
from pathlib import Path

from pipeline.publish import release_history as history


class ReleaseHistoryTest(unittest.TestCase):
    def test_first_promotion_records_the_replaced_release_with_its_own_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "release_history.jsonl"
            history.record_release(
                kind="promotion",
                run_id="luna",
                evidence_release_id="luna:ev",
                public_release_id="luna:public",
                replaced_extraction_pointer={
                    "run_id": "september",
                    "release_id": "september:ev",
                    "updated_at_utc": "2026-09-18T20:00:00+00:00",
                },
                path=path,
            )
            history.record_release(
                kind="public_refresh",
                run_id="luna",
                evidence_release_id="luna:ev",
                public_release_id="luna:public:2",
                path=path,
            )

            records = history.read_release_history(path)
            self.assertEqual([record["kind"] for record in records], ["seed", "promotion", "public_refresh"])
            self.assertEqual(records[0]["promoted_at"], "2026-09-18T20:00:00+00:00")
            self.assertEqual(history.previous_run_id(records, "luna"), "september")
            self.assertEqual(history.promotion_time(records, "luna"), records[1]["promoted_at"])
            self.assertEqual(history.promotion_time(records, "september"), "2026-09-18T20:00:00+00:00")

    def test_replaced_release_is_recorded_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "release_history.jsonl"
            replaced = {"run_id": "a", "release_id": "a:ev", "updated_at_utc": "2026-01-01T00:00:00+00:00"}
            history.record_release(
                kind="promotion", run_id="b", evidence_release_id="b:ev", public_release_id="b:p",
                replaced_extraction_pointer=replaced, path=path,
            )
            history.record_release(
                kind="promotion", run_id="c", evidence_release_id="c:ev", public_release_id="c:p",
                replaced_extraction_pointer={"run_id": "b", "release_id": "b:ev"}, path=path,
            )

            runs = [record["run_id"] for record in history.read_release_history(path)]
            self.assertEqual(runs, ["a", "b", "c"])

    def test_invalid_records_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "release_history.jsonl"
            path.write_text(json.dumps({"kind": "promotion"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                history.read_release_history(path)


if __name__ == "__main__":
    unittest.main()
