from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "outputs" / "source_identity_repair_20260710"
WORK_DIR = Path(__file__).resolve().parent


def records(frame: pd.DataFrame) -> list[dict]:
    return frame.fillna("").to_dict("records")


manifest = pd.read_csv(REPORT_DIR / "final_source_identity_repair_manifest.csv").fillna("")
queue = pd.read_csv(REPORT_DIR / "manual_download_queue_all.csv").fillna("")
old_payload_path = WORK_DIR / "triage_data.json"
old_payload = json.loads(old_payload_path.read_text(encoding="utf-8")) if old_payload_path.exists() else {}

abstract_only = manifest[manifest["final_action_category"] == "abstract_only_no_fulltext_repair"].copy()
known_no_public_fulltext = abstract_only[abstract_only["curated_access_status"] != ""].copy()
other_abstract_only = abstract_only[abstract_only["curated_access_status"] == ""].copy()
excluded = manifest[
    manifest["final_action_category"].isin(
        ["excluded_prescreen_no_artifact_repair", "not_retained_no_artifact_repair"]
    )
].copy()

payload = {
    "summary": {
        "original_artifact_count": int(len(manifest)),
        "active_verified_artifacts": int(manifest["current_identity_verified"].astype(str).str.lower().eq("true").sum()),
        "abstract_only_no_repair": int(len(abstract_only)),
        "known_no_public_fulltext": int(len(known_no_public_fulltext)),
        "fulltext_repair_queue": int(len(queue)),
        "excluded_no_repair": int(len(excluded)),
        "newly_excluded_this_pass": 424,
        "format_excluded_kg_leaks": 0,
    },
    "known_no_public_fulltext": records(known_no_public_fulltext.sort_values("doi")),
    "other_abstract_only": records(other_abstract_only.sort_values("doi")),
    "fulltext_repairs": records(
        queue.sort_values(["priority_score", "kg_finding_count", "doi"], ascending=[False, False, True])
    ),
    "excluded": records(excluded.sort_values("doi")),
    "imported": old_payload.get("imported", []),
}
old_payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
