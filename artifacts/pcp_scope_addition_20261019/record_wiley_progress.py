"""Persist browser-observed recovery outcomes and verify saved file bytes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import html
import json
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.ingest.metadata_utils import pdf_filename_for_doi

RUN = ROOT / "data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/wiley_viewer_retry_20261019"
INBOX = ROOT / "data/raw/papers/manual_pdf_inbox/wiley_viewer_retry_20261019"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--paywall', nargs='*', default=[])
    parser.add_argument('--followup', nargs='*', default=[])
    parser.add_argument('--download', nargs=2, action='append', default=[])
    args = parser.parse_args()
    frozen = pd.read_csv(RUN / 'frozen_candidates.csv').fillna('')
    updates = json.loads((RUN / 'browser_results.json').read_text())
    INBOX.mkdir(exist_ok=True)
    for doi in args.paywall:
        updates[doi] = {'status':'publisher_paywall_observed', 'evidence':'Publisher PDF UI explicitly offers Get access to the full version, Institutional Login, and Purchase Instant Access. No scientific screening decision changed.'}
    for doi in args.followup:
        if updates.get(doi, {}).get('status') != 'pdf_saved_pending_batch_validation':
            updates[doi] = {'status':'viewer_followup_needed', 'evidence':'Viewer/page-count readiness or access routing needs follow-up. No closed-access conclusion made.'}
    for doi, filename in args.download:
        source = Path.home() / 'Downloads' / filename
        assert source.is_file(), str(source)
        with source.open('rb') as handle:
            assert handle.read(5) == b'%PDF-'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target = INBOX / pdf_filename_for_doi(doi)
        if not target.exists():
            shutil.copy2(source, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        updates[doi] = {'status':'pdf_saved_pending_batch_validation', 'download_path':str(source), 'staged_pdf_path':str(target), 'bytes':source.stat().st_size, 'sha256':digest, 'evidence':'Browser downloadMedia returned a saved path; file exists with PDF header. Full identity/body validation pending batch pass.'}
    assert set(updates) <= set(frozen.doi)
    (RUN / 'browser_results.json').write_text(json.dumps(updates, indent=2, ensure_ascii=False)+'\n')
    rows=[]
    for row in frozen.to_dict('records'):
        result=updates.get(row['doi'], {})
        rows.append({'doi':row['doi'], 'title':row['title'], 'status':result.get('status','not_yet_attempted'), 'bytes':result.get('bytes',''), 'saved_file':result.get('staged_pdf_path',''), 'evidence':result.get('evidence',''), 'source_url':row['observed_stable_pdf_url'] or row['recommended_open_url']})
    pd.DataFrame(rows).to_csv(RUN / 'progress.csv', index=False)
    counts={str(k):int(v) for k,v in pd.Series([r['status'] for r in rows]).value_counts().items()}
    summary={'counts':counts,'verified_saved_pdf_bytes':sum(r.get('bytes',0) for r in updates.values()),'scope':len(frozen),'at_utc':datetime.now(timezone.utc).isoformat(),'model_calls':0}
    (RUN / 'progress_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    cards=''.join('<tr>'+''.join(f'<td>{html.escape(str(row[k]))}</td>' for k in ['doi','title','status','evidence'])+'</tr>' for row in rows)
    (RUN / 'progress.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Wiley recovery progress</title><style>body{font:15px system-ui;margin:30px}td,th{padding:10px;border:1px solid #ddd;text-align:left}table{border-collapse:collapse}h1{font-size:26px}</style><h1>Wiley recovery: saved files and access outcomes</h1><p>'+html.escape(json.dumps(counts))+'</p><p>Saved means a real PDF file exists on disk. Full identity/body validation follows in one batch. Publisher paywalls and technical follow-ups remain distinct.</p><table><tr><th>DOI</th><th>Paper</th><th>Outcome</th><th>Evidence</th></tr>'+cards+'</table></html>')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
