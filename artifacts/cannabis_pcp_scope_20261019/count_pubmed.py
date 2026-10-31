"""Bounded, public PubMed count checks; no record ingestion or model calls."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import time

import requests

P = Path(__file__).resolve().parent
ROOT = P.parents[1]
endpoint = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
window = '("1800/01/01"[Date - Publication] : "2026/10/19"[Date - Publication])'
pcp = '("Phencyclidine"[MeSH Terms] OR phencyclidine[Title/Abstract])'
plant = '("Cannabis"[MeSH Terms] OR cannabis[Title/Abstract] OR marijuana[Title/Abstract])'
family = ('("Cannabis"[MeSH Terms] OR "Cannabinoids"[MeSH Terms] OR '
          'cannabis[Title/Abstract] OR marijuana[Title/Abstract] OR '
          'cannabinoid*[Title/Abstract] OR tetrahydrocannabinol*[Title/Abstract] OR cannabidiol[Title/Abstract])')
queries = {
    'pcp_precise': pcp,
    'pcp_precise_english_abstract': f'{pcp} AND english[Language] AND hasabstract',
    'pcp_bare_acronym': 'PCP[Title/Abstract]',
    'cannabis_plant': plant,
    'cannabis_cannabinoids': family,
    'cannabis_cannabinoids_english_abstract': f'{family} AND english[Language] AND hasabstract',
    'cannabis_and_pcp': f'{family} AND {pcp}',
}
email = ''
config = ROOT / 'pipeline/config.local.yaml'
if config.exists():
    match = re.search(r'^\s*(?:contact_email|email):\s*[\"\']?([^\s\"\'#]+@[^\s\"\'#]+)', config.read_text(), re.M)
    if match:
        email = match[1]
results = []
for name, concept in queries.items():
    out = P / f'pubmed_count_{name}.json'
    if out.exists():
        response = json.loads(out.read_text())
        results.append(response)
        print(name, response.get('count'), '(saved)', flush=True)
        continue
    term = f'({concept}) AND {window}'
    params = dict(db='pubmed', term=term, retmax=0, retmode='json', tool='psychedelics_kg_scope_audit')
    if email:
        params['email'] = email
    attempts = []
    for attempt in range(3):
        try:
            r = requests.get(endpoint, params=params, timeout=25)
            attempts.append({'attempt': attempt + 1, 'status_code': r.status_code})
            r.raise_for_status()
            data = r.json()
            count = int(data['esearchresult']['count'])
            break
        except (requests.RequestException, ValueError, KeyError) as exc:
            attempts.append({'attempt': attempt + 1, 'error_type': type(exc).__name__})
            if attempt == 2:
                count, data = None, {'error': type(exc).__name__}
                break
            time.sleep(2 ** attempt)
    text = json.dumps(data, ensure_ascii=False)
    raw = P / f'pubmed_count_{name}_raw.json'
    raw.write_text(text + '\n')
    record = {
        'query_name': name, 'endpoint': endpoint, 'term': term,
        'date_accessed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'parameters': {k: v for k, v in params.items() if k != 'email'},
        'contact_email_provided': bool(email), 'count': count,
        'query_translation': data.get('esearchresult', {}).get('querytranslation'),
        'warnings': data.get('esearchresult', {}).get('warninglist'),
        'errors': data.get('esearchresult', {}).get('errorlist'),
        'attempts': attempts, 'raw_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
        'interpretation': 'Broad database hits, not eligible papers, independent studies, corpus additions, or a recall denominator.',
    }
    out.write_text(json.dumps(record, indent=2) + '\n')
    results.append(record)
    print(name, count, flush=True)
    time.sleep(0.5)
(P / 'pubmed_count_summary.json').write_text(json.dumps(results, indent=2) + '\n')
