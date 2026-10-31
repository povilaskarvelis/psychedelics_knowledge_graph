"""Contract-aware cache identities shared by paper-level extraction runners."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]

def secondary_contract_fingerprint(family: str, *, root: Path = ROOT) -> str:
    if family not in {"review", "meta"}:
        raise ValueError(f"Unsupported secondary family {family}")
    folder="review_relationships_v2" if family=="review" else "meta_analysis_v2"
    schema="review_relationships_v2.bundle.schema.json" if family=="review" else "meta_analysis_evidence_v2.schema.json"
    paths=[root/"docs/extraction_profiles"/folder/n for n in ("abstract_extraction.md","full_text_extraction.md")]+[root/"schema"/schema]
    records=[(str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    return hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()

def completed_task_ids(path: Path) -> set[str]:
    if not path.exists():return set()
    return {str(r.get("task_id", "")) for line in path.open() if line.strip()
            for r in [json.loads(line)] if r.get("status")=="ok" and r.get("task_id")}

def attempted_task_ids(batch_dir: Path, current_tasks: Path) -> set[str]:
    return {str(r.get("task_id", "")) for p in batch_dir.glob("*_tasks.jsonl")
            if p.resolve()!=current_tasks.resolve() for line in p.open() if line.strip()
            for r in [json.loads(line)] if r.get("task_id")}
