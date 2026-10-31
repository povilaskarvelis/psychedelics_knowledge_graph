"""Append observed browser outcomes; never infer access from download failures."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/provider_browser_pass_20261020'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('doi')
    p.add_argument('status')
    p.add_argument('provider')
    p.add_argument('evidence')
    p.add_argument('--file')
    args = p.parse_args()
    frozen = pd.read_csv(RUN / 'frozen_candidates.csv').fillna('')
    assert args.doi in set(frozen.doi), args.doi
    event = dict(doi=args.doi, status=args.status, provider=args.provider,
                 evidence=args.evidence, model_calls=0,
                 at_utc=datetime.now(timezone.utc).isoformat())
    if args.file:
        f = Path(args.file).resolve()
        assert f.is_file() and f.read_bytes()[:5] == b'%PDF-', str(f)
        event.update(saved_file=str(f), bytes=f.stat().st_size,
                     sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    elif args.status.startswith('pdf_saved'):
        raise ValueError('Saved status requires a verified local PDF')
    with (RUN / 'events.jsonl').open('a') as h:
        h.write(json.dumps(event, ensure_ascii=False)+'\n')
    latest = {}
    for line in (RUN / 'events.jsonl').read_text().splitlines():
        e = json.loads(line)
        latest[e['doi']] = e
    pd.DataFrame(latest.values()).to_csv(RUN / 'progress.csv', index=False)
    counts = pd.Series([e['status'] for e in latest.values()]).value_counts().to_dict()
    summary = dict(scope=len(frozen), attempted=len(latest),
                   remaining=len(frozen)-len(latest), counts={k:int(v) for k,v in counts.items()},
                   saved_bytes=sum(e.get('bytes',0) for e in latest.values()),
                   model_calls=0, at_utc=event['at_utc'])
    (RUN / 'progress_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
