import json
from pathlib import Path
import pandas as pd
from pipeline.publish.export_evidence_payload import load_findings, detail_bootstrap_payload, OPTIONAL_COGNITIVE_OBSERVATION_FIELDS


def test_raw_native_cognitive_values_reach_public_detail_without_replacing_effect_description(tmp_path):
 rows=json.loads((Path(__file__).parent/"fixtures/cognitive_observation_saved_rows.json").read_text())
 native=next(r for r in rows if r['study_doi']=='10.1056/nejmoa2302399')
 pd.DataFrame([{"finding_id":"cognitive","paper_id":"paper","source_name":"routed_extractions","study_doi":native['study_doi'],
  "domain":"cognitive_behavioral","compound":"Ketamine versus ECT","entity_label":"Verbal memory","raw_row_json":json.dumps(native)}]).to_parquet(tmp_path/'findings.parquet',index=False)
 payload=detail_bootstrap_payload(load_findings(tmp_path,require_author_identities=False),'2026-10-31',tmp_path,'primary')
 row={k:payload['values'][v] for k,v in zip(payload['fields'],payload['rows'][0])}
 for field in OPTIONAL_COGNITIVE_OBSERVATION_FIELDS:assert row[field]==native[field]
 assert '-0.9±1.1' in row['statistic_or_value'] and '-9.7±1.2' in row['statistic_or_value']
 assert row['effect_size']==native['effect_size']
 assert 'raw_row_json' not in row
