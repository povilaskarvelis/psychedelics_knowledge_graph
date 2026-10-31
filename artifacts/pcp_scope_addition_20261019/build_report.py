"""Build a local count report from saved receipts; makes no provider/model calls."""
from pathlib import Path
import html
import json
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from pipeline import llm

R = ROOT / "data/processed/discovery/runs/pcp_scope_addition_20261019"
D = R / "downstream"


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def main():
    cohort = pd.read_csv(D / "cohort.csv")
    pre_path = D / "inputs/prescreen_scope.parquet"
    pre = pd.read_parquet(pre_path) if pre_path.exists() else pd.DataFrame()
    promotion = read(R / "discovery_promotion_report.json")
    controller = read(D / "controller_state.json", {})
    handoff = read(D / "handoff_status.json", {})
    live_batch = read(D / "screening/main/latest_status.json", {})
    raw_path = D / "screening/raw_combined.jsonl"
    latest = {}
    if raw_path.exists():
        for line in raw_path.open():
            row = json.loads(line)
            latest[row["doi"]] = row
    decisions = pd.DataFrame([{"doi": doi, "screening_decision": row.get("parsed", {}).get("screening_decision", "error"),
        "screening_reason": row.get("parsed", {}).get("screening_reason", ""), "model": row.get("model"),
        "prompt_sha256": row.get("prompt_sha256")} for doi, row in latest.items()])
    joined = cohort.copy()
    if not pre.empty:
        joined = joined.merge(pre[["doi", "prescreen_decision", "prescreen_action"]], on="doi", validate="one_to_one")
    if not decisions.empty:
        joined = joined.merge(decisions, on="doi", how="left", validate="one_to_one")
    by_origin = []
    for origin in ["new_discovery", "pcp_scope_reconsideration", "restored_abstract"]:
        group = joined.loc[joined.origin.eq(origin)]
        row = {"origin": origin, "records": len(group)}
        if not pre.empty:
            row.update(deterministic_excluded=int(group.prescreen_decision.eq("exclude").sum()),
                luna_inputs=int(group.prescreen_decision.eq("retain").sum()))
        if not decisions.empty:
            row.update(luna_included=int(group.screening_decision.eq("include_in_scope").sum()),
                luna_excluded=int(group.screening_decision.eq("exclude_out_of_scope").sum()))
        by_origin.append(row)
    actual_cost = 0.0
    billed_responses = 0
    for path in sorted((D / "screening").glob("*/results.jsonl")):
        for line in path.open():
            usage = json.loads(line).get("response", {}).get("body", {}).get("usage", {}) or {}
            if "input_tokens" in usage and "output_tokens" in usage:
                actual_cost += llm.token_cost(usage, batch=True)
                billed_responses += 1
    baseline = pd.read_parquet(D / "baseline/candidate_papers.parquet", columns=["doi", "retained_for_extraction_candidate"])
    baseline_retained = int(baseline.retained_for_extraction_candidate.fillna(False).astype(bool).sum())
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": R.name,
        "status": handoff.get("status") or controller.get("status"), "stage": controller.get("stage"),
        "handoff": handoff, "batch_status": live_batch.get("status"), "batch_request_counts": live_batch.get("request_counts"),
        "discovery": promotion["counts"], "by_origin": by_origin,
        "deterministic_actions": pre.prescreen_action.value_counts().to_dict() if not pre.empty else {},
        "screening_decisions": dict(Counter(x.get("parsed", {}).get("screening_decision", "error") for x in latest.values())),
        "screening_model": "gpt-6-luna", "reasoning_effort": "low", "prompt": "V5 with explicit PCP substance name only",
        "screening_inputs": "title_and_abstract_only", "baseline_extraction_eligible": baseline_retained,
        "model_billed_response_count": billed_responses, "model_cost_usd_from_saved_usage": actual_cost,
        "extraction_model_calls": 0, "graph_publication": False,
        "completion_integrity": read(D / "completion_integrity.json"),
        "fulltext": read(D / "fulltext/worklist_report.json", {}).get("counts", {}),
        "source_identity_note": "Mechanical identity checks and source retrieval do not rescreen paper eligibility.",
        "limitations": ["OpenAlex returned 8269 of 8270 reported hits after retries; the one-record shortfall was accepted under the existing count-drift tolerance and disclosed.",
            "1289 no-DOI identifier groups remain in the existing resolution ledger, not scientific scope exclusions.",
            "Records and DOIs are not independent studies; retrieval completion is not measured search recall.",
            "Prepared extraction inputs remain provisional while manual full-text recovery is pending."],
    }
    report["prepared_task_counts"] = {}
    for label, path in {
        "primary_and_guideline": D / "extraction_tasks.jsonl",
        "reviews": D / "review_tasks/review_relationship_tasks.jsonl",
        "meta_analyses": D / "meta_analysis_tasks/meta_analysis_v2_tasks.jsonl",
    }.items():
        if path.exists():
            report["prepared_task_counts"][label] = sum(bool(line.strip()) for line in path.open())
    llm.atomic_json(D / "report.json", report)
    pd.DataFrame(by_origin).to_csv(D / "screening_by_origin.csv", index=False)
    joined.to_csv(D / "record_dispositions.csv", index=False)
    labels = {"new_discovery": "New DOI discoveries", "pcp_scope_reconsideration": "Existing PCP records reconsidered", "restored_abstract": "Other restored abstracts"}
    columns = [("records", "Records"), ("deterministic_excluded", "Cleanup exclusions"), ("luna_inputs", "Luna inputs"),
        ("luna_included", "Luna included"), ("luna_excluded", "Luna excluded")]
    table = '<table><thead><tr><th>Cohort</th>' + ''.join('<th>' + name + '</th>' for _, name in columns) + '</tr></thead><tbody>'
    for row in by_origin:
        table += '<tr><th>' + labels[row['origin']] + '</th>' + ''.join('<td>' + (f'{row[key]:,}' if key in row else 'Pending') + '</td>' for key, _ in columns) + '</tr>'
    table += '</tbody></table>'
    fulltext = '<pre>' + html.escape(json.dumps(report['fulltext'], indent=2)) + '</pre>' if report['fulltext'] else '<p>Source recovery follows completed screening.</p>'
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>PCP search addition — 19 October 2026</title>
<style>body{{font:16px system-ui;line-height:1.5;max-width:1050px;margin:40px auto;padding:0 24px;color:#17212b}}table{{border-collapse:collapse;width:100%;margin:24px 0}}th,td{{border:1px solid #ccd5dd;padding:10px;text-align:left}}td{{text-align:right}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f7;padding:16px}}</style>
<h1>PCP search addition — 19 October 2026</h1>
<p><b>Status:</b> {html.escape(str(report['status']))}. Stage: {html.escape(str(report['stage']))}.</p>
<p>Batch: {html.escape(str(report['batch_status']))}; requests: {html.escape(str(report['batch_request_counts']))}. Updated: {html.escape(report['generated_at_utc'])}.</p>
<p>Two targeted historical searches, PubMed and OpenAlex, 1800–19 October 2026. The search produced 14,451 provider records, merging into 5,474 new DOI records, 2,429 rediscovered DOI records and 1,289 no-DOI resolution records.</p>
<p>Current publication-format, language and usable-abstract cleanup precedes Luna. Screening uses titles and abstracts only: GPT-6 Luna, low reasoning, V5 with PCP explicitly named. Existing included papers are preserved.</p>
{table}
<p><b>Saved-usage model cost:</b> ${actual_cost:.4f} across {billed_responses:,} billed responses currently downloaded. Zero extraction model calls.</p>
<h2>Source recovery</h2>{fulltext}
<p>Baseline extraction-eligible papers: {baseline_retained:,}. The published graph and active extraction release remain unchanged.</p>
<h2>Limits and pending work</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in report['limitations'])}</ul>
<p><a href="report.json">Full counts</a> · <a href="record_dispositions.csv">Every scoped DOI and disposition</a> · <a href="../search_plan.csv">Exact search queries</a> · <a href="controller.log">Continuous pipeline log</a> · <a href="fulltext/manual_recovery.csv">Manual full-text queue, when prepared</a></p></html>'''
    (D / "report.html").write_text(body)
    print(json.dumps({"report": str(D / "report.html"), "status": report['status'], "screening_decisions": report['screening_decisions'], "cost_usd": actual_cost}))


if __name__ == "__main__":
    main()
