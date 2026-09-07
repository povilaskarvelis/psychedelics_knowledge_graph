"""Read-only corpus/source scan used for the September 2026 pipeline audit."""
from pathlib import Path
from collections import Counter
import json, hashlib, subprocess, xml.etree.ElementTree as ET, sys
import duckdb
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from pipeline.fulltext.build_llm_evidence_packets import best_extraction, extract_tables_and_figures
active=json.loads((root/'data/processed/extraction/active_routed_run.json').read_text());kg=root/active['kg_dir']
c=duckdb.connect()
c.read_parquet(str(root/'data/processed/corpus/candidate_papers.parquet')).create_view('candidate')
c.read_parquet(str(kg/'findings.parquet')).create_view('finding')
queries={
'candidate_integrity': "SELECT count(*) records, count(distinct doi) unique_dois, count(*) FILTER (WHERE doi IS NULL OR doi='') missing_dois FROM candidate",
'findings_by_family': "SELECT source_family, count(*) findings, count(distinct study_doi) reports FROM finding GROUP BY 1 ORDER BY 1",
'active_ineligible': "SELECT count(distinct c.doi) reports FROM candidate c JOIN finding f ON c.doi=f.study_doi WHERE NOT c.retained_for_extraction_candidate OR c.post_retrieval_decision='exclude'",
'condition_split': "SELECT count(*) findings, count(distinct study_doi) reports FROM finding WHERE endpoint_label_source='condition_text_split'",
'corrupt_dose': "SELECT count(*) findings, count(distinct study_doi) reports FROM finding WHERE regexp_matches(dose, '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]')",
'corrupt_effect_size': "SELECT count(*) findings, count(distinct study_doi) reports FROM finding WHERE regexp_matches(effect_size, '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]')",
'primary_quotes': "SELECT count(*) findings, count(*) FILTER (WHERE supporting_quote IS NULL OR supporting_quote='') without_quote FROM finding WHERE source_family='primary_study'",
'no_abstract_screening': "SELECT prescreen_actions, count(*) records, count(*) FILTER (WHERE flag_has_local_pdf) flagged_local_pdf FROM candidate WHERE prescreen_actions LIKE '%abstract%' GROUP BY 1 ORDER BY 2 DESC",
'status_distribution': "SELECT graph_inclusion_status, count(*) records FROM candidate GROUP BY 1 ORDER BY 2 DESC"
}
results={}
for name,sql in queries.items():
 cur=c.execute(sql);results[name]={'sql':sql,'rows':[dict(zip([col[0] for col in cur.description],row)) for row in cur.fetchall()]}
active_dois={row[0] for row in c.execute('SELECT DISTINCT study_doi FROM finding').fetchall()}
audit=json.loads((root/'data/processed/fulltext/source_identity_audit.json').read_text())
counts=Counter();examples=[];jats_dois=set()
for row in audit['rows']:
 if row.get('best_backend') not in ('europepmc_fulltext_xml','pmc_oai_xml'):continue
 p=Path(row['artifact_path']);artifact=json.loads(p.read_text());xml=best_extraction(artifact).get('text','');tree=ET.fromstring(xml)
 elements=list(tree.iter());local=lambda e:e.tag.rsplit('}',1)[-1]
 figs=[e for e in elements if local(e)=='fig'];wraps=[e for e in elements if local(e)=='table-wrap']
 caps=[e for e in wraps if any(local(x)=='caption' for x in e)];notes=[e for e in wraps if any(local(x)=='table-wrap-foot' for x in e)]
 tables,figures=extract_tables_and_figures(xml);doi=artifact.get('study_doi','');jats_dois.add(doi)
 for key,value in [('jats_artifacts',1),('jats_with_figures',bool(figs)),('source_jats_figures',len(figs)),('jats_with_table_captions',bool(caps)),('source_table_captions',len(caps)),('jats_with_table_notes',bool(notes)),('source_table_notes',len(notes)),('current_parser_figures',len(figures))]:counts[key]+=value
 if doi in active_dois:
  counts['active_reports_with_jats_artifact']+=1;counts['active_reports_with_jats_figures']+=bool(figs);counts['active_reports_with_jats_table_captions']+=bool(caps)
 if len(examples)<8 and figs and caps:
  examples.append({'doi':doi,'artifact':str(p.relative_to(root)),'source_figures':len(figs),'parsed_figures':len(figures),'table_captions':len(caps),'parsed_caption_sample':[t['caption'] for t in tables[:3]],'represented_in_active_findings':doi in active_dois})
packet_counts=Counter()
for line in (root/'data/processed/extraction/fulltext_packets.jsonl').open():
 packet=json.loads(line)
 if packet.get('study_doi') not in jats_dois:continue
 packet_counts['saved_jats_packets']+=1;packet_counts['saved_jats_packets_with_figures']+=bool(packet.get('figures'))
 packet_counts['saved_jats_tables']+=len(packet.get('tables',[]));packet_counts['saved_jats_tables_with_caption']+=sum(bool(t.get('caption')) for t in packet.get('tables',[]))
files=['data/processed/extraction/active_routed_run.json','data/processed/graph_payload_active.json','data/processed/corpus/candidate_papers.parquet',str((kg/'findings.parquet').relative_to(root)),'data/processed/extraction/fulltext_packets.jsonl']
snapshots=[]
for rel in files:
 p=root/rel;h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 snapshots.append({'path':rel,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
out={'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'active_run':active,'read_only_queries':results,'jats_source_scan':{'counts':dict(counts),'saved_packet_counts':dict(packet_counts),'examples':examples},'input_snapshots':snapshots}
# Print-only scan: no corpus or release artifacts are written.
print(json.dumps(out,indent=2))
