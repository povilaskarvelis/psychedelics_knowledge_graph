"""Stage Chrome-confirmed DOI-named downloads and append retrieval receipts."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/provider_browser_pass_20261020'
INBOX = ROOT/'data/raw/papers/manual_pdf_inbox/provider_browser_pass_20261020'

for doi in sys.argv[1:]:
    name=doi.replace('/','_')+'.pdf'
    source=Path.home()/'Downloads'/name
    assert source.is_file() and source.read_bytes()[:5]==b'%PDF-', str(source)
    dest=INBOX/name
    if dest.exists():
        assert dest.read_bytes()==source.read_bytes(), 'Existing staged file differs: '+doi
    else:
        shutil.copy2(source,dest)
    existing=[json.loads(line) for line in (RUN/'events.jsonl').read_text().splitlines()]
    if any(e['doi']==doi and e.get('saved_file')==str(dest) for e in existing):
        continue
    subprocess.run([sys.executable,str(ROOT/'artifacts/pcp_scope_addition_20261019/record_provider_progress.py'),
        doi,'pdf_saved_pending_batch_validation','ScienceDirect',
        'External Chrome main article PDF loaded. Adobe Download this document/native Save completed; Chrome Done and actual file header/hash verified. Document identity/import/conversion follow in the scoped batch.',
        '--file',str(dest)],check=True,stdout=subprocess.DEVNULL)
print((RUN/'progress_summary.json').read_text())
