"""Refresh the existing human recovery batches from saved receipts; no retrieval or models."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import html
import json
import shutil
import sys
from urllib.parse import quote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.ingest.metadata_utils import normalize_doi

D = ROOT / "data/processed/discovery/runs/pcp_scope_addition_20261019/downstream"
OLD = ROOT / "data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018"
B = OLD / "manual_chrome_batches_20261019"
OUT = D / "manual_handoff"


def read(path):
    return json.loads(path.read_text())


def key(value):
    return normalize_doi(str(value or "")).lower()


def csv_write(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def batch_page(number, rows, inbox):
    cards = []
    for row in rows:
        e = lambda value: html.escape(str(value), quote=True)
        doi = row["doi"]
        cards.append(f'''<article data-doi="{e(doi)}"><label><input type="checkbox" class="done"> {row['batch_position']}. <strong>{e(row['title'])}</strong></label>
<p>{e(row['year'])} · {e(doi)} · {e(row['oa_status'] or 'OA status unknown')}</p>
<p>{e(row['ranking_reason'])}</p><p><a target="_blank" rel="noopener" href="{e(row['doi_url'])}">Open DOI / publisher page</a>
<a target="_blank" rel="noopener" href="{e(row['recommended_open_url'])}">Saved article location</a></p>
<p>Suggested filename: <code>{e(row['suggested_pdf_filename'])}</code></p><input class="notes" placeholder="Download / access outcome and notes"></article>''')
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>PDF recovery batch {number:03d}</title>
<style>body{{font:16px system-ui;max-width:1050px;margin:30px auto;padding:0 22px;color:#192d3c;background:#f7fafc}}h1{{font-size:28px}}article{{background:white;padding:20px;border:1px solid #cbd5df;border-radius:8px;margin:16px 0}}p{{line-height:1.45}}a{{color:#075a9c;margin-right:20px}}code{{overflow-wrap:anywhere;font-size:13px}}.notes{{width:95%;padding:10px}}button{{padding:10px 16px;cursor:pointer}}.handled{{opacity:.5}}</style>
<h1>PDF recovery · batch {number:03d} · {len(rows)} papers</h1>
<p>Continue after the two batches you already reviewed. These papers remain included under V5 + PCP. The order uses saved download evidence; it is not a probability of success. Start at the DOI page and use the main article's PDF control.</p>
<p>Save complete article PDFs in: <code>{html.escape(str(inbox))}</code></p>
<p>Checkboxes and notes stay in this browser until you export them. They do not confirm a download or change screening. Export outcomes after finishing the batch.</p>
<button id="export">Export outcomes CSV</button> <a href="papers.csv">Paper list</a> <a href="../ready_batches.html">All prepared batches</a>
{''.join(cards)}<script>const rows={payload};const storage='pdf-recovery-pcp-batch-{number:03d}';let saved=JSON.parse(localStorage.getItem(storage)||'{{}}');
document.querySelectorAll('article').forEach(card=>{{let doi=card.dataset.doi,s=saved[doi]||{{}};let box=card.querySelector('.done'),note=card.querySelector('.notes');box.checked=!!s.handled;note.value=s.note||'';card.classList.toggle('handled',box.checked);function save(){{saved[doi]={{handled:box.checked,note:note.value}};localStorage.setItem(storage,JSON.stringify(saved));card.classList.toggle('handled',box.checked)}}box.onchange=save;note.oninput=save}});
document.getElementById('export').onclick=()=>{{let fields=['doi','study_title','browser_batch','manual_status','manual_notes'];const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';let lines=[fields.map(q).join(','),...rows.map(r=>[r.doi,r.title,{number},saved[r.doi]?.handled?'reviewed_pending_pdf_reconciliation':'pending',saved[r.doi]?.note||''].map(q).join(','))];let a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+lines.join('\\r\\n')],{{type:'text/csv;charset=utf-8'}}));a.download='pdf-recovery-batch-{number:03d}-outcomes.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};</script></html>'''


def main():
    assert read(D / "controller_state.json")["status"] == "complete_at_source_recovery_checkpoint"
    assert read(D / "handoff_status.json")["status"] == "complete_at_current_pipeline_checkpoint"
    if (OUT / "batch_manifest.json").exists():
        print(json.dumps(read(OUT / "batch_manifest.json")))
        return
    existing = {key(r['doi']): r for r in pd.read_csv(B / "ranked_remaining.csv").fillna("").to_dict("records")}
    progress = pd.read_csv(B / "progress.csv").fillna("")
    assigned = set(progress.doi.map(key))
    for f in B.glob("batch_*/manifest.json"):
        assigned.update(key(r["doi"]) for r in read(f)["papers"])
    old = pd.read_csv(OLD / "remaining_manual_review.csv").fillna("").to_dict("records")
    increment = pd.read_csv(D / "fulltext/manual_recovery.csv").fillna("").to_dict("records")
    work = pd.read_parquet(OUT / "worklist.parquet").fillna("")
    current = pd.read_parquet(ROOT / "data/processed/corpus/candidate_papers.parquet", columns=["doi", "retained_for_extraction_candidate"])
    retained = set(current.loc[current.retained_for_extraction_candidate.fillna(False).astype(bool), "doi"].map(key))
    work = {key(r["doi"]): r for r in work.to_dict("records")}
    queue = {}; skipped = {"already_assigned": [], "not_currently_retained": [], "usable_text_now_available": []}
    for origin, sources in [("existing_manual_queue", old), ("pcp_increment", increment)]:
        for source in sources:
            doi = key(source["doi"])
            if doi in queue:
                continue
            reason = "already_assigned" if doi in assigned else "not_currently_retained" if doi not in retained else "usable_text_now_available" if work.get(doi, {}).get("has_converted_full_text") else ""
            if reason:
                skipped[reason].append(doi)
                continue
            assert doi in work, f"Retained manual DOI missing from current worklist: {doi}"
            row = {**source, **existing.get(doi, {})}
            oa = str(work[doi].get("open_access_status", "") or row.get("oa_status", ""))
            if doi not in existing:
                score = (25 if oa in ["gold", "green", "bronze", "hybrid", "diamond"] else -50 if oa == "closed" else 0)
                if source.get("pdf_download_failure_category") == "forbidden" and oa != "closed":
                    score += 8
                row.update(recoverability_score=score, ranking_reason=f"Saved OA metadata: {oa or 'unknown'}; automated direct and alternate PDF attempts completed. No browser download control has yet been verified for this new PCP case.", category="pcp_automated_recovery_unresolved")
            row.update(doi=doi, title=source.get("title", source.get("study_title", "")), year=source.get("year", source.get("study_year", "")), oa_status=oa,
                doi_url="https://doi.org/" + quote(doi, safe="/():;@!$&'+,=-._~"), origin=origin, previously_assigned=False,
                manual_status="prepared_not_yet_opened", manual_notes="")
            row.setdefault("recommended_open_url", row["doi_url"])
            row.setdefault("suggested_pdf_filename", source.get("suggested_pdf_filename", ""))
            queue[doi] = row
    rows = sorted(queue.values(), key=lambda r: (-float(r["recoverability_score"]), -float(r.get("year") or 0), r["doi"]))
    snapshot = OUT / "previous_batch_owner";snapshot.mkdir(exist_ok=True)
    for name in ["ranked_remaining.csv", "ranking_method.json", "README.md", "progress.csv", "active_batch.json"]:
        if (B/name).exists() and not (snapshot/name).exists():shutil.copy2(B/name,snapshot/name)
    first = max([int(f.name.split('_')[1]) for f in B.glob('batch_*') if f.is_dir()] or [0]) + 1
    batches = []
    for offset in range(0, len(rows), 50):
        number = first + offset // 50;papers=rows[offset:offset+50];folder=B/f"batch_{number:03d}";folder.mkdir()
        inbox=ROOT/f"data/raw/papers/manual_pdf_inbox/luna_fulltext_browser_manual_after_full_pass/batch_{number:03d}";inbox.mkdir(parents=True,exist_ok=True)
        for i,r in enumerate(papers,1):r.update(batch_number=number,batch_position=i,recovery_rank=offset+i)
        write_json(folder/'manifest.json', {'batch_number':number,'status':'prepared_not_yet_opened','paper_count':len(papers),'created_at_utc':datetime.now(timezone.utc).isoformat(),'download_inbox':str(inbox),'papers':papers})
        csv_write(folder/'papers.csv',papers)
        (folder/'urls.txt').write_text('\n'.join(r['doi_url'] for r in papers)+'\n')
        (folder/'index.html').write_text(batch_page(number,papers,inbox))
        (inbox/'README.txt').write_text(f'Batch {number:03d}: save complete main-article PDFs here. The batch is prepared, not opened or reviewed. Files require identity validation and conversion before extraction.\n')
        batches.append({'batch_number':number,'papers':len(papers),'index':str(folder/'index.html'),'status':'prepared_not_yet_opened'})
    assert len(rows)==len({r['doi'] for r in rows}) and not set(queue)&assigned
    csv_write(B/'ranked_remaining.csv',rows)
    report={'status':'manual_batches_ready','prepared_papers':len(rows),'prepared_batches':len(batches),'batch_size':50,'next_batch':first,'previously_assigned_unique_papers':len(assigned),'input_existing_queue':len(old),'input_pcp_queue':len(increment),'origins':{str(k):int(v) for k,v in pd.Series([r['origin'] for r in rows]).value_counts().items()},'skipped':{k:len(set(v)) for k,v in skipped.items()},'batches':batches,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model_calls':0,'extraction_jobs_submitted':0,'screening_decisions_changed':0}
    write_json(OUT/'skipped_records.json',skipped)
    write_json(OUT/'batch_manifest.json',report)
    write_json(B/'prepared_batch_index.json',report)
    write_json(B/'next_batch.json',batches[0] if batches else {})
    write_json(B/'ranking_method.json',{'method':'Preserved existing browser-observation ranking; new PCP records ranked from saved OA metadata and transfer-failure evidence. Earlier browser batches excluded by existing manifests/progress. Current retained selection and usable-text sources checked mechanically. No scientific rescreening. Scores are not calibrated success probabilities.','source_worklist':str(OUT/'worklist.parquet'),'updated_at_utc':report['generated_at_utc']})
    links=''.join(f"<li><a href='batch_{v['batch_number']:03d}/index.html'>Batch {v['batch_number']:03d}</a> — {v['papers']} papers</li>" for v in batches)
    (B/'ready_batches.html').write_text(f"<!doctype html><html lang='en'><meta charset='utf-8'><title>Manual PDF batches ready</title><style>body{{font:17px system-ui;max-width:850px;margin:40px auto;line-height:1.6}}a{{color:#075a9c}}</style><h1>Manual PDF recovery batches</h1><p>{len(rows):,} unreviewed papers in {len(batches)} batches, up to 50 per batch. Continue at batch {first:03d}. The 100 papers from your first two batches are kept separate; their saved downloads/outcomes can still be reconciled.</p><p>Open the DOI/publisher page, download the complete main article, and save it in the batch inbox shown on the checklist. These batches are prepared; no new Chrome tabs have been opened.</p><ul>{links}</ul></html>")
    with (B/'README.md').open('a') as handle:handle.write(f'\n\nPCP refresh: automated recovery/conversion and provisional input refresh completed. {len(rows)} unassigned papers prepared in batches {first:03d}–{batches[-1]["batch_number"]:03d}. See ready_batches.html and prepared_batch_index.json; open the earliest prepared batch when requested. Do not run the older prepare_batch.py to regenerate its pre-PCP queue. Preserve progress.csv and batch_001/batch_002; prepared does not mean opened.\n')
    print(json.dumps({k:v for k,v in report.items() if k!='batches'},default=int))


if __name__ == '__main__':
    main()
