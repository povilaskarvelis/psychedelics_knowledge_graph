#!/usr/bin/env python3
"""Package a built candidate run as a local-only site preview, or serve one.

The same steps as promote_routed_run.py, into an isolated folder: the ledger's
graph status is reconciled with the run in a copy, and the browser and Methods
data are exported from it. The live ledger, the active pointers and data/kg are
checked to be unchanged. Run from the repository root:

    python pipeline/publish/prepare_local_preview.py --run-id RUN --port 8015
    python pipeline/publish/prepare_local_preview.py --run-id RUN --serve
"""
from __future__ import annotations

import argparse
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R))
from pipeline.kg.build_methods_flow import MethodsFlowBuilder  # noqa: E402
from pipeline.kg.update_corpus_graph_status import DEFAULT_DISPOSITION_OVERRIDES, update_corpus_graph_status  # noqa: E402
from pipeline.publish.export_evidence_payload import export_evidence_payload  # noqa: E402
from scripts.serve_site import PreviewRequestHandler, build_local_preview  # noqa: E402

ALIASES = R / "pipeline/validate/doi_alias_registry.json"
PREVIEW_ROOT = R / "data/processed/previews"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(run: str, port: int) -> dict:
    v = PREVIEW_ROOT / run
    isolated = v / "isolated_root"
    kg = R / "data/processed/kg_routed_runs" / run
    outputs = R / "data/processed/extraction/routed_runs" / run / "route_extraction_outputs.jsonl"
    ledger = v / "candidate_for_preview.parquet"
    release = run + ":local"
    v.mkdir(parents=True, exist_ok=True)

    protected = [
        R / "data/processed/graph_payload_active.json",
        R / "data/processed/extraction/active_routed_run.json",
        R / "data/processed/corpus/candidate_papers.parquet",
        *sorted((R / "data/kg/views").glob("*.json")),
    ]
    before = {str(p): sha(p) for p in protected if p.is_file()}

    report = update_corpus_graph_status(
        candidate_table=R / "data/processed/corpus/candidate_papers.parquet", output_table=ledger, kg_dir=kg,
        disposition_overrides=DEFAULT_DISPOSITION_OVERRIDES, extraction_results=[outputs],
        doi_alias_registry=ALIASES, run_id=run, release_id=release,
    )
    (v / "corpus_disposition_report.json").write_text(json.dumps(report, indent=2, default=str))
    print("Ledger copy reconciled with the run", flush=True)

    out = isolated / "data/processed/graph_payload_runs" / run
    export_evidence_payload(kg_dir=kg, out_dir=out, active_json=None, require_fresh_author_tables=True,
                            candidate_papers_table=ledger, doi_alias_registry=ALIASES)
    manifest = json.loads((out / "graph_payload_manifest.json").read_text())
    prefix = out.relative_to(R).as_posix() + "/"

    def rewrite(value):
        if isinstance(value, str) and value.startswith(prefix):
            return f"data/processed/graph_payload_runs/{run}/" + value[len(prefix):]
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    manifest = rewrite(manifest)
    manifest.update(run_id=run, release_id=release, evidence_release_id=release)
    (out / "graph_payload_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Browser data exported", flush=True)

    methods = MethodsFlowBuilder(candidate_table=ledger).build()
    assert methods["pipeline_status"]["run_id"] == run
    views = isolated / "data/kg/views"
    views.mkdir(parents=True, exist_ok=True)
    for key, name in [("pipeline_status", "pipeline_status_graph.json"), ("methods_bibliography", "methods_bibliography.json"),
                      ("graph_inclusion_dispositions", "graph_inclusion_dispositions.json")]:
        (views / name).write_text(json.dumps(methods[key]))

    pointer, allowed = build_local_preview(isolated, requested_run_id=run)
    (v / "preview_pointer.json").write_text(json.dumps(pointer, indent=2))
    (v / "allowed_files.json").write_text(json.dumps({k: str(p) for k, p in allowed.items()}, indent=2))
    with (v / "site_build.log").open("w") as log:
        subprocess.run(["bash", "scripts/build_site.sh"], cwd=R, env={**os.environ, "DIST_DIR": str(isolated / "dist")},
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    index = isolated / "dist/index.html"
    index.write_text(re.sub(r"Graph version: [^<]+", f"Graph version: candidate {run} (local preview)", index.read_text()))

    after = {str(p): sha(p) for p in protected if p.is_file()}
    assert before == after, "A live file changed while packaging the preview"
    completion = {"status": "preview_ready", "run_id": run, "release_id": release, "port": port,
                  "url": f"http://127.0.0.1:{port}/?data-source=local", "live_files_unchanged": True,
                  "paper_counts": manifest.get("summary_stats", {}).get("paper_counts")}
    (v / "completion.json").write_text(json.dumps(completion, indent=2))
    return completion


def serve(run: str) -> None:
    v = PREVIEW_ROOT / run
    completion = json.loads((v / "completion.json").read_text())
    handler = partial(
        PreviewRequestHandler, directory=str(v / "isolated_root/dist"),
        local_pointer=(v / "preview_pointer.json").read_bytes(),
        local_files={k: Path(p) for k, p in json.loads((v / "allowed_files.json").read_text()).items()},
        published_pointer=None, published_files={},
    )
    server = ThreadingHTTPServer(("127.0.0.1", completion["port"]), handler)
    print(completion["url"], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True, help="A run built under data/processed/kg_routed_runs")
    parser.add_argument("--port", type=int, default=8015)
    parser.add_argument("--serve", action="store_true", help="Serve a prepared preview instead of preparing one")
    args = parser.parse_args()
    if args.serve:
        serve(args.run_id)
    else:
        print(json.dumps(prepare(args.run_id, args.port), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
