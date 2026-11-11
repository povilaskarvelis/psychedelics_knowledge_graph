#!/usr/bin/env python3
"""Take a promoted literature search through screening and article-text retrieval.

The stages after `pipeline/discovery/promote_search_run.py`, in order:

1. abstract recovery for the search's screening handoff (PubMed and PMC, then
   Crossref for the records still without one);
2. rules-based initial screening;
3. Luna title and abstract screening with the active instruction, one provider
   batch and one retry of failed requests, added to the canonical screening
   table;
4. PMC/Europe PMC XML, open-access link refresh, direct and alternate PDF
   downloads, and GROBID conversion of the downloaded PDFs;
5. extraction routes for the update's papers, added to the canonical route
   table, and the source-identity audit;
6. the list of papers whose article text was not obtained automatically, in
   batches of at most 50 for manual download.

It stops there. Manual PDFs are imported with
`pipeline/fulltext/import_manual_pdfs.py`; then `--after-manual-import N` (N
numbers the import round) converts them, rebuilds the update's routes, runs the
identity audit and lists the papers still without article text. Extraction
follows.

Every stage writes a receipt and is skipped when its receipt exists, so the
command can be run again after an interruption. Rows of papers outside the
update are checked to be unchanged before a canonical table is replaced.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import html
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline import llm  # noqa: E402
from pipeline.extract import build_extraction_routes as routes  # noqa: E402
from pipeline.review import run_domain_routing as screening  # noqa: E402
from pipeline.review import run_domain_routing_batch as batch  # noqa: E402

DISCOVERY_RUNS = ROOT / "data/processed/discovery/runs"
MANUAL_INBOX = ROOT / "data/raw/papers/manual_pdf_inbox"
SCREENING_PROFILE = "v5_class_scope"
SCREENING_MODEL = "gpt-6-luna"
BATCH_SIZE = 50
BASELINE_FILES = [
    "data/processed/corpus/candidate_papers.parquet",
    "data/processed/corpus/paper_metadata_enrichment.parquet",
    "data/processed/corpus/paper_prescreen_decisions.parquet",
    "data/processed/corpus/paper_domain_routing.parquet",
    "data/processed/corpus/paper_extraction_routes.parquet",
    "data/processed/graph_payload_active.json",
    "data/processed/extraction/active_routed_run.json",
]
PUBLISHED_POINTERS = BASELINE_FILES[-2:]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(Path(path).read_text())


def sha(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_dois(path: Path) -> list[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


class Update:
    def __init__(self, run_id: str, python: str):
        self.run_id = run_id
        self.python = python
        self.search_dir = DISCOVERY_RUNS / run_id
        self.dir = self.search_dir / "downstream"
        self.fulltext = self.dir / "fulltext"
        self.inputs = self.dir / "inputs"
        self.baseline = self.dir / "baseline"
        self.scope = self.dir / "scope_dois.txt"
        self.state_path = self.dir / "state.json"

    # Receipts

    def state(self) -> dict:
        return read_json(self.state_path) if self.state_path.exists() else {"run_id": self.run_id, "done": []}

    def save_state(self, **fields) -> dict:
        state = {**self.state(), **fields, "updated_at_utc": now()}
        llm.atomic_json(self.state_path, state)
        return state

    def done(self, stage: str) -> bool:
        return stage in self.state()["done"]

    def mark_done(self, stage: str) -> None:
        state = self.state()
        state["done"].append(stage)
        self.save_state(done=state["done"], stage=stage)

    def command(self, stage: str, script: str, *args) -> None:
        if self.done(stage):
            return
        self.save_state(status="running", stage=stage)
        if script.startswith("-m "):
            cmd = [self.python, "-m", script[3:], *map(str, args)]
        else:
            cmd = [self.python, str(ROOT / script), *map(str, args)]
        log = self.dir / "logs" / f"{stage}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        print(f"{now()} {stage}", flush=True)
        started = now()
        with log.open("a") as handle:
            result = subprocess.run(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        llm.atomic_json(log.with_suffix(".receipt.json"), {"stage": stage, "command": cmd, "started_at_utc": started,
                                                          "ended_at_utc": now(), "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{stage} exited {result.returncode}; see {log}")
        self.mark_done(stage)

    # Stages

    def prepare(self) -> None:
        manifest = read_json(self.search_dir / "run_manifest.json")
        if manifest.get("status") != "promoted":
            raise SystemExit(f"Discovery run {self.run_id} is not promoted")
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.scope.exists():
            shutil.copy2(self.search_dir / "screening_candidate_dois.txt", self.scope)
        if not (self.baseline / "manifest.json").exists():
            self.baseline.mkdir(parents=True, exist_ok=True)
            files = []
            for relative in BASELINE_FILES:
                source = ROOT / relative
                shutil.copy2(source, self.baseline / source.name)
                files.append({"path": relative, "sha256": sha(source)})
            llm.atomic_json(self.baseline / "manifest.json", files)
        if not read_dois(self.scope):
            raise SystemExit("The search added no papers to screen")

    def abstracts(self) -> None:
        for suffix, providers in [("abstracts", "pubmed,pmc"), ("abstracts_crossref", "crossref")]:
            self.command(suffix, "pipeline/ingest/run_batch_abstract_enrichment.py",
                         "--run-id", f"{self.run_id}_{suffix}", "--doi-file", self.scope, "--providers", providers)

    def prescreen(self) -> None:
        self.command("prescreen", "pipeline/review/run_deterministic_prescreen.py", "--run-id", self.run_id,
                     "--doi-file", self.scope, "--reconciliation-report", self.dir / "prescreen_reconciliation.json")

    def instruction(self) -> Path:
        frozen = self.inputs / "screening_instruction.md"
        if not frozen.exists():
            active = ROOT / read_json(llm.PIPELINE_STATE)["screening_instruction_file"]
            self.inputs.mkdir(parents=True, exist_ok=True)
            shutil.copy2(active, frozen)
        return frozen

    def freeze_inputs(self) -> None:
        freeze = self.inputs / "freeze.json"
        if not freeze.exists():
            scope = set(read_dois(self.scope))
            self.inputs.mkdir(parents=True, exist_ok=True)
            for name, source in [("candidate_scope.parquet", screening.DEFAULT_CANDIDATE_TABLE),
                                 ("metadata_scope.parquet", screening.DEFAULT_METADATA_TABLE),
                                 ("prescreen_scope.parquet", screening.DEFAULT_PRESCREEN_TABLE)]:
                frame = pd.read_parquet(source)
                frame.loc[frame.doi.isin(scope)].to_parquet(self.inputs / name, index=False)
            prescreen = pd.read_parquet(self.inputs / "prescreen_scope.parquet")
            model_dois = sorted(set(prescreen.loc[prescreen.prescreen_decision.eq("retain"), "doi"]))
            (self.inputs / "model_dois.txt").write_text("".join(doi + "\n" for doi in model_dois))
            self.instruction()
            llm.atomic_json(freeze, {path.name: sha(path) for path in self.inputs.iterdir()
                                     if path.is_file() and path.name != "freeze.json"})
        for name, digest in read_json(freeze).items():
            if sha(self.inputs / name) != digest:
                raise RuntimeError(f"Frozen screening input changed: {name}")

    def send_direct(self, api, requests: Path, results: Path, responses: Path) -> None:
        """Send each request on its own and write the replies in the batch output format, so the batch parser reads them."""
        lines = []
        for line in requests.open():
            row = json.loads(line)
            saved = responses / f"{row['custom_id']}.json"
            if not saved.exists():
                llm.reserve_budget(str(saved), llm.reservation_cost(row["body"]))
                try:
                    reply = {"status_code": 200, "body": api.responses.create(**row["body"]).model_dump(mode="json")}
                except Exception as error:
                    reply = {"status_code": getattr(error, "status_code", None), "body": {"error": str(error)}}
                llm.atomic_json(saved, reply)
                usage = reply["body"].get("usage") or {}
                llm.settle_budget(str(saved), llm.token_cost(usage) if usage.get("output_tokens") is not None else 0.0)
                print(now(), "direct", row["custom_id"], reply["status_code"], flush=True)
            lines.append({"custom_id": row["custom_id"], "response": read_json(saved)})
        results.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))

    def screening_batch(self, name: str, doi_file: Path, direct: bool = False) -> dict[str, Path]:
        folder = self.dir / "screening" / name
        folder.mkdir(parents=True, exist_ok=True)
        paths = {key: folder / value for key, value in {
            "requests": "requests.jsonl", "manifest": "manifest.json", "job": "job.json", "results": "results.jsonl",
            "raw": "raw.jsonl", "routes": "routes.parquet", "summary": "summary.json", "counts": "counts.csv",
            "report": "parse_report.json"}.items()}
        instruction = self.instruction()
        tables = ["--candidate-table", self.inputs / "candidate_scope.parquet",
                  "--metadata-table", self.inputs / "metadata_scope.parquet",
                  "--prescreen-decisions-table", self.inputs / "prescreen_scope.parquet"]
        if not paths["manifest"].exists():
            self.command(f"screening_{name}_prepare", "pipeline/review/run_domain_routing_batch.py", "prepare", *tables,
                         "--doi-file", doi_file, "--screening-profile", SCREENING_PROFILE,
                         "--screening-instruction-file", instruction, "--model", SCREENING_MODEL,
                         "--max-output-tokens", "2048", "--batch-input-jsonl", paths["requests"],
                         "--manifest-json", paths["manifest"], "--raw-jsonl", paths["raw"])
        bodies = [json.loads(line)["body"] for line in paths["requests"].open()]
        if not bodies or any(body["model"] != SCREENING_MODEL or body["reasoning"]["effort"] != "low"
                             or body["instructions"] != instruction.read_text().strip() for body in bodies):
            raise RuntimeError("Screening requests do not use the frozen model, reasoning effort and instruction")
        llm.atomic_json(paths["requests"].with_suffix(".cost.json"), {
            "requests": len(bodies),
            "reservation_ceiling_usd": sum(llm.reservation_cost(body, batch=True) for body in bodies),
            "instruction_sha256": sha(instruction)})
        api = llm.client(batch.api_key_from_env(type("Args", (), {"env_file": str(ROOT / ".env")})(), required=True))
        if direct:
            if not paths["results"].exists():
                self.save_state(stage=f"screening_{name}_direct")
                self.send_direct(api, paths["requests"], paths["results"], folder / "responses")
        elif not paths["job"].exists():
            llm.submit(api, requests_path=paths["requests"], job_path=paths["job"],
                       metadata={"stage": "screening", "model": SCREENING_MODEL, "run_id": self.run_id})
        if not direct:
            job_id = read_json(paths["job"]).get("job_name")
            if not job_id:
                raise RuntimeError("The submission receipt has no job ID; reconcile it before submitting again")
            self.save_state(stage=f"screening_{name}_batch", batch_job=job_id)
            last = None
            while True:
                job = api.batches.retrieve(job_id)
                snapshot = job.model_dump(mode="json")
                llm.atomic_json(folder / "latest_status.json", snapshot)
                progress = (job.status, json.dumps(snapshot.get("request_counts", {}), sort_keys=True))
                if progress != last:
                    print(now(), name, *progress, flush=True)
                    last = progress
                if job.status in llm.TERMINAL_STATES:
                    break
                time.sleep(30)
            if not paths["results"].exists():
                llm.download(api, job, paths["results"])
        if not paths["report"].exists():
            args = type("Args", (), dict(
                batch_output_jsonl=str(paths["results"]), manifest_json=str(paths["manifest"]),
                raw_jsonl=str(paths["raw"]), output_table=str(paths["routes"]), summary_json=str(paths["summary"]),
                counts_csv=str(paths["counts"]), report_json=str(paths["report"]),
                candidate_table=str(self.inputs / "candidate_scope.parquet"),
                metadata_table=str(self.inputs / "metadata_scope.parquet"),
                prescreen_decisions_table=str(self.inputs / "prescreen_scope.parquet"),
                env_file=str(ROOT / ".env"), model=SCREENING_MODEL))()
            batch.parse_batch_results(args)
        return paths

    def screen(self) -> None:
        if self.done("screening_promoted"):
            return
        self.freeze_inputs()
        model_dois = self.inputs / "model_dois.txt"
        raw = [json.loads(line) for line in self.screening_batch("main", model_dois)["raw"].open()]
        latest = {row["doi"]: row for row in raw}
        failed = sorted(doi for doi, row in latest.items() if row["status"] != "ok")
        if failed:
            retry_file = self.inputs / "retry_dois.txt"
            retry_file.write_text("".join(doi + "\n" for doi in failed))
            retry = [json.loads(line) for line in self.screening_batch("retry", retry_file, direct=True)["raw"].open()]
            raw.extend(retry)
            latest.update({row["doi"]: row for row in retry})
        if any(row["status"] != "ok" for row in latest.values()):
            raise RuntimeError("Screening requests still failed after one retry")
        if set(latest) != set(read_dois(model_dois)):
            raise RuntimeError("Screening results do not cover the papers sent to the model")
        combined = self.dir / "screening/raw_combined.jsonl"
        combined.write_text("".join(json.dumps({**row, "screening_run_id": self.run_id}, ensure_ascii=False) + "\n"
                                    for row in raw))
        self.command("screening_combine", "pipeline/review/run_domain_routing.py", "--parse-only",
                     "--screening-profile", SCREENING_PROFILE, "--raw-jsonl", combined,
                     "--candidate-table", self.inputs / "candidate_scope.parquet",
                     "--metadata-table", self.inputs / "metadata_scope.parquet",
                     "--prescreen-decisions-table", self.inputs / "prescreen_scope.parquet",
                     "--output-table", self.dir / "screening/routes.parquet",
                     "--summary-json", self.dir / "screening/summary.json",
                     "--counts-csv", self.dir / "screening/counts.csv")
        merged = self.replace_scope_rows(screening.DEFAULT_OUTPUT_TABLE, self.dir / "screening/routes.parquet",
                                         ["doi", "domain_route"])
        raw_log = screening.DEFAULT_RAW_JSONL
        if not any(json.loads(line).get("screening_run_id") == self.run_id for line in raw_log.open() if line.strip()):
            temporary = raw_log.with_suffix(".jsonl.tmp")
            with temporary.open("wb") as handle, raw_log.open("rb") as previous:
                shutil.copyfileobj(previous, handle)
                handle.write(combined.read_bytes())
            temporary.replace(raw_log)
        summary, counts = screening.build_summary(merged.to_dict("records"), inputs={"increment": self.run_id})
        screening.write_json(screening.DEFAULT_SUMMARY_JSON, summary)
        screening.write_counts_csv(screening.DEFAULT_COUNTS_CSV, counts)
        llm.atomic_json(self.dir / "screening/promotion.json", {
            "at_utc": now(), "scope": len(read_dois(self.scope)), "model_decisions": len(latest),
            "decisions": dict(Counter(row["parsed"]["screening_decision"] for row in latest.values())),
            "instruction_sha256": sha(self.instruction()), "canonical_sha256": sha(screening.DEFAULT_OUTPUT_TABLE)})
        state = read_json(llm.PIPELINE_STATE)
        state.setdefault("screening_scope_additions", {})[self.run_id] = {
            "screening_status": "complete", "path": str(self.dir), "scope_file": str(self.scope),
            "screening_promotion": str(self.dir / "screening/promotion.json"), "fulltext_status": "pending"}
        state["screening_table_sha256"] = sha(screening.DEFAULT_OUTPUT_TABLE)
        llm.atomic_json(llm.PIPELINE_STATE, state)
        llm.atomic_json(self.dir / "queue.json", {"run_id": self.run_id, "inputs": {
            "previous_candidate_table": str(self.baseline / "candidate_papers.parquet")},
            "parts": [{"raw_jsonl": str(combined)}]})
        self.mark_done("screening_promoted")

    def replace_scope_rows(self, table: Path, increment_table: Path, order: list[str]) -> pd.DataFrame:
        """Replace the update's rows of a canonical table, after checking no other row changed."""
        scope = set(read_dois(self.scope))
        baseline = pd.read_parquet(self.baseline / table.name)
        current = pd.read_parquet(table)
        increment = pd.read_parquet(increment_table)
        outside = baseline.loc[~baseline.doi.isin(scope)].sort_values(order).reset_index(drop=True)
        actual = current.loc[~current.doi.isin(scope), baseline.columns].sort_values(order).reset_index(drop=True)
        pd.testing.assert_frame_equal(outside, actual, check_dtype=False)
        merged = pd.concat([current.loc[~current.doi.isin(scope)], increment], ignore_index=True)
        temporary = table.with_suffix(".parquet.tmp")
        merged.to_parquet(temporary, index=False)
        temporary.replace(table)
        return merged

    def worklist(self, label: str) -> None:
        f = self.fulltext
        self.command(f"worklist_{label}", "pipeline/fulltext/build_fulltext_enrichment_worklist.py",
                     "--queue-json", self.dir / "queue.json", "--include-previously-processed",
                     "--output-selected-dois", f / "selected_dois.txt", "--output-enrichment-dois", f / "enrichment_dois.txt",
                     "--output-access-metadata-refresh-dois", f / "access_refresh_dois.txt",
                     "--output-no-accessible-fulltext-dois", f / "no_accessible_fulltext_dois.txt",
                     "--output-oa-landing-dois", f / "oa_landing_dois.txt",
                     "--output-table", f / "worklist.parquet", "--report-json", f / "worklist_report.json",
                     *sum((["--pmc-report", str(path)] for path in sorted(f.glob("pmc_*.json"))), []))
        snapshot = f / f"worklist_report.{label}.json"
        if not snapshot.exists():
            shutil.copy2(f / "worklist_report.json", snapshot)

    def retrieve(self) -> None:
        f = self.fulltext
        f.mkdir(parents=True, exist_ok=True)
        pdf_options = ["--include-weak-pdf-urls", "--no-rebuild-routes-after", "--attempt-log-every", "0",
                       "--candidate-log-every", "0", "--timeout-sec", "25", "--max-retries", "1"]
        self.worklist("initial")
        self.command("pmc_initial", "pipeline/fulltext/fetch_pmc_fulltext_xml.py", "--selection-table", f / "worklist.parquet",
                     "--report", f / "pmc_initial.json", "--workers", "8", "--rps", "2", "--timeout-sec", "25",
                     "--no-rebuild-routes-after")
        self.worklist("after_pmc")
        if (f / "enrichment_dois.txt").read_text().strip():
            self.command("open_access", "pipeline/ingest/refresh_open_access_links.py", "--doi-file", f / "enrichment_dois.txt",
                         "--config", ROOT / "pipeline/config.local.yaml", "--only-missing-pdf-url", "--workers", "8",
                         "--report-json", f / "access_refresh.json", "--pmc-report", f / "pmc_initial.json",
                         "--timeout-sec", "25", "--max-retries", "1", "--max-retry-after-sec", "30")
        self.worklist("after_access")
        self.command("pmc_after_access", "pipeline/fulltext/fetch_pmc_fulltext_xml.py", "--selection-table",
                     f / "worklist.parquet", "--report", f / "pmc_after_access.json", "--workers", "8", "--rps", "2",
                     "--timeout-sec", "25", "--no-rebuild-routes-after")
        self.worklist("before_pdf")
        self.command("pdf_direct", "pipeline/fulltext/download_fulltext_worklist_pdfs.py", "--selection-table",
                     f / "worklist.parquet", "--report", f / "pdf_direct.json", "--workers", "10", "--rps", "3", *pdf_options)
        self.worklist("after_direct")
        self.command("pdf_alternate", "pipeline/fulltext/download_fulltext_worklist_pdfs.py", "--selection-table",
                     f / "worklist.parquet", "--report", f / "pdf_alternate.json", "--workers", "8", "--rps", "2",
                     "--alternate-pdf-sources", "pmc,openalex,semantic_scholar", "--alternate-sources-only", *pdf_options)
        self.worklist("after_alternate")
        self.command("grobid", "pipeline/fulltext/start_grobid.py")
        self.command("convert_pdfs", "pipeline/fulltext/convert_routed_local_pdfs.py", "--selection-table",
                     f / "worklist.parquet", "--doi-file", f / "selected_dois.txt", "--report", f / "conversion.json",
                     "--no-rebuild-routes-after", "--backend", "grobid")
        self.worklist("final")

    def route(self, label: str = "") -> None:
        suffix = f"_{label}" if label else ""
        if not self.done(f"routes_promoted{suffix}"):
            self.command(f"routes{suffix}", "pipeline/extract/build_extraction_routes.py", "--doi-file", self.scope,
                         "--output-table", self.dir / "extraction_routes.parquet",
                         "--summary-json", self.dir / "extraction_routes_summary.json",
                         "--counts-csv", self.dir / "extraction_routes_counts.csv")
            merged = self.replace_scope_rows(routes.DEFAULT_OUTPUT_TABLE, self.dir / "extraction_routes.parquet",
                                             ["doi", "route_id"])
            summary, counts = routes.build_summary(merged.to_dict("records"), inputs={"scope_addition": self.run_id})
            routes.write_json(routes.DEFAULT_SUMMARY_JSON, summary)
            routes.write_counts_csv(routes.DEFAULT_COUNTS_CSV, counts)
            self.mark_done(f"routes_promoted{suffix}")
        self.command(f"identity_audit{suffix}", "-m pipeline.identity", "audit")

    def after_manual_import(self, number: int) -> dict:
        """Convert PDFs imported by hand, rebuild routes, and list the papers still without text."""
        f, label = self.fulltext, f"manual_{number}"
        self.worklist(label)
        self.command(f"grobid_{label}", "pipeline/fulltext/start_grobid.py")
        self.command(f"convert_{label}", "pipeline/fulltext/convert_routed_local_pdfs.py", "--selection-table",
                     f / "worklist.parquet", "--doi-file", f / "selected_dois.txt",
                     "--report", f / f"conversion_{label}.json", "--no-rebuild-routes-after", "--backend", "grobid")
        self.route(label)
        self.worklist(f"{label}_audited")
        self.command(f"manual_queue_{label}", "pipeline/fulltext/export_manual_pdf_queue.py", "--selection-table",
                     f / "worklist.parquet", "--output-csv", f / f"manual_recovery_{label}.csv",
                     "--output-txt", f / f"manual_recovery_dois_{label}.txt")
        table = pd.read_parquet(self.dir / "extraction_routes.parquet").drop_duplicates("doi")
        included = table[table.domain_screening_decision.eq("include_in_scope")]
        report = {"run_id": self.run_id, "round": number,
                  "included_papers": len(included),
                  "by_access_tier": dict(Counter(included.access_tier)),
                  "still_on_manual_list": len(read_dois(f / f"manual_recovery_dois_{label}.txt")),
                  "generated_at_utc": now()}
        llm.atomic_json(self.dir / f"manual_import_{number}.json", report)
        self.check_published_release_unchanged()
        self.save_state(status=f"manual_import_{number}_converted", stage="complete")
        return report

    def manual_handoff(self) -> dict:
        out = self.dir / "manual_download"
        # Rebuilt after the identity audit, so texts it rejected go to the manual list.
        self.worklist("handoff")
        self.command("manual_queue", "pipeline/fulltext/export_manual_pdf_queue.py", "--selection-table",
                     self.fulltext / "worklist.parquet", "--output-csv", self.fulltext / "manual_recovery.csv",
                     "--output-txt", self.fulltext / "manual_recovery_dois.txt", "--require-automated-retrieval-complete")
        if (out / "batches.json").exists():
            return read_json(out / "batches.json")
        rows = pd.read_csv(self.fulltext / "manual_recovery.csv", dtype=str).fillna("").to_dict("records")
        rows = list({row["doi"]: row for row in rows}.values())
        batches = []
        for offset in range(0, len(rows), BATCH_SIZE):
            number = offset // BATCH_SIZE + 1
            papers = rows[offset:offset + BATCH_SIZE]
            folder = out / f"batch_{number:03d}"
            inbox = MANUAL_INBOX / self.run_id / f"batch_{number:03d}"
            folder.mkdir(parents=True, exist_ok=True)
            inbox.mkdir(parents=True, exist_ok=True)
            for position, row in enumerate(papers, 1):
                row["batch_position"] = position
                row["doi_url"] = "https://doi.org/" + quote(row["doi"], safe="/():;@!$&'+,=-._~")
            write_csv(folder / "papers.csv", papers)
            (folder / "urls.txt").write_text("".join(row["doi_url"] + "\n" for row in papers))
            (folder / "index.html").write_text(batch_page(self.run_id, number, papers, inbox))
            batches.append({"batch": number, "papers": len(papers), "page": str(folder / "index.html"),
                            "inbox": str(inbox)})
        report = {"run_id": self.run_id, "papers": len(rows), "batches": batches, "generated_at_utc": now()}
        llm.atomic_json(out / "batches.json", report)
        return report

    def check_published_release_unchanged(self) -> None:
        for item in read_json(self.baseline / "manifest.json"):
            if item["path"] in PUBLISHED_POINTERS and sha(ROOT / item["path"]) != item["sha256"]:
                raise RuntimeError(f"A published release pointer changed: {item['path']}")

    def run(self) -> None:
        self.prepare()
        self.abstracts()
        self.prescreen()
        self.screen()
        self.retrieve()
        self.route()
        report = self.manual_handoff()
        self.check_published_release_unchanged()
        state = read_json(llm.PIPELINE_STATE)
        state["screening_scope_additions"][self.run_id].update(
            fulltext_status="automated_complete_manual_download_prepared",
            manual_download=str(self.dir / "manual_download/batches.json"))
        llm.atomic_json(llm.PIPELINE_STATE, state)
        self.save_state(status="manual_download_ready", stage="complete", manual_papers=report["papers"])
        print(json.dumps({key: value for key, value in report.items() if key != "batches"}), flush=True)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def batch_page(run_id: str, number: int, rows: list[dict], inbox: Path) -> str:
    escape = lambda value: html.escape(str(value or ""), quote=True)  # noqa: E731
    cards = "".join(
        f'<article data-doi="{escape(row["doi"])}"><label><input type="checkbox" class="done"> '
        f'{row["batch_position"]}. <strong>{escape(row.get("study_title"))}</strong></label>'
        f'<p>{escape(row.get("study_year"))} · {escape(row["doi"])} · '
        f'{escape(row.get("open_access_status") or "access status unknown")}</p>'
        f'<p><a target="_blank" rel="noopener" href="{escape(row["doi_url"])}">Publisher page</a>'
        + "".join(f' <a target="_blank" rel="noopener" href="{escape(row[column])}">{label}</a>'
                  for column, label in [("open_access_url", "Open-access page"), ("best_pdf_url", "Known PDF link")]
                  if row.get(column))
        + '</p><input class="notes" placeholder="Outcome and notes"></article>'
        for row in rows)
    storage = f"manual-download-{run_id}-{number:03d}"
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Manual download batch {number:03d}</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto;padding:0 20px;color:#192d3c;background:#f7fafc}}
article{{background:#fff;padding:18px;border:1px solid #cbd5df;border-radius:8px;margin:14px 0}}a{{color:#075a9c;margin-right:18px}}
code{{overflow-wrap:anywhere}}.notes{{width:95%;padding:8px}}.handled{{opacity:.5}}</style>
<h1>Manual download · {escape(run_id)} · batch {number:03d} · {len(rows)} papers</h1>
<p>Save the complete main-article PDF of each paper in <code>{escape(inbox)}</code>. Any file name works; files are
matched to papers by their content when imported.</p>
<p>Ticks and notes are kept in this browser only.</p>{cards}
<script>const key="{storage}";let saved=JSON.parse(localStorage.getItem(key)||"{{}}");
document.querySelectorAll("article").forEach(card=>{{const doi=card.dataset.doi,s=saved[doi]||{{}},box=card.querySelector(".done"),note=card.querySelector(".notes");
box.checked=!!s.done;note.value=s.note||"";card.classList.toggle("handled",box.checked);
const save=()=>{{saved[doi]={{done:box.checked,note:note.value}};localStorage.setItem(key,JSON.stringify(saved));card.classList.toggle("handled",box.checked)}};
box.onchange=save;note.oninput=save}});</script></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True, help="A promoted discovery run under data/processed/discovery/runs")
    parser.add_argument("--after-manual-import", type=int, default=0, metavar="ROUND",
                        help="After importing manually downloaded PDFs: convert them, rebuild routes and list what remains")
    args = parser.parse_args()
    update = Update(args.run_id, sys.executable)
    update.dir.mkdir(parents=True, exist_ok=True)
    lock = (update.dir / "update.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another process is running this update")
    update.save_state(status="running", error="")
    try:
        if args.after_manual_import:
            print(json.dumps(update.after_manual_import(args.after_manual_import)), flush=True)
        else:
            update.run()
    except Exception as exc:
        update.save_state(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
