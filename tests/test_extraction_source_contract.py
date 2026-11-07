import json

from pipeline.extract.build_extraction_tasks import source_fingerprint_for_task
from pipeline.extract.io_utils import source_text_hashes, task_text_hashes
from pipeline.identity.evidence import text_sha256
from pipeline.ingest.candidate_status import clean
from pipeline.extract.run_route_extraction import article_or_abstract_text_for_task
from pipeline.kg.convert_routed_extractions_to_evidence_rows import evidence_row_for_item,task_lookup


def test_curated_abstract_is_in_actual_article_input_and_its_identity():
    packet={'packet_id':'p','paper_metadata':{'abstract':''},'llm_chunks':[{'text':'Original Results section.'}]}
    metadata={'study_title':'A study','abstract':'Curated complete abstract with additional measured results.'}
    source={'mode':'full_text_packet'}
    fp=source_fingerprint_for_task(text_source=source,metadata=metadata,packet=packet)
    altered={**metadata,'abstract':'A changed verified abstract with different evidence.'}
    assert fp!=source_fingerprint_for_task(text_source=source,metadata=altered,packet=packet)
    task={'extraction_contract':{'access_level':'full_text_seen'},'route_context':{'access_tier':'full_text_available'},
          'text_source':{'mode':'full_text_packet','source_fingerprint':fp},'paper_metadata':metadata,'content':{'title':metadata['study_title'],'abstract':metadata['abstract'],'packet':packet}}
    label,text=article_or_abstract_text_for_task(task)
    assert label=='ARTICLE_TEXT' and metadata['abstract'] in text and 'Original Results section.' in text


def test_unusable_abstract_never_produces_unqualified_effect_edge(tmp_path):
    task={'task_id':'t','study_doi':'10.1000/nav','paper_metadata':{'abstract':'ADVERTISEMENT RETURN TO ISSUE Article Views Altmetric Abstract'},
          'text_source':{'mode':'abstract'}}
    path=tmp_path/'tasks.jsonl';path.write_text(json.dumps(task)+'\n')
    item={'compound_or_exposure':'Ketamine','brain_region':'Prefrontal cortex','primary_graph_anchor_kind':'brain_region',
          'finding_summary':'A title-only assertion.','evidence_role':'descriptive_measurement','source_contribution':'unclear'}
    row=evidence_row_for_item(output_row={'task_id':'t'},result={'task_id':'t','study_doi':task['study_doi'],'domain_route':'brain_system','text_depth':'abstract_only'},
          item=item,item_kind='primary_item',item_index=1,tasks=task_lookup(path))
    assert row['graph_admission_reason']=='unusable_abstract_extraction_source'
    assert row['graph_admission_status']=='paper_detail'
    assert row['evidence_role']=='descriptive_measurement' and row['source_contribution']=='unclear'
    assert row['finding_summary']==item['finding_summary']


def test_packet_file_hash_names_the_text_without_changing_task_identity():
    packet={'packet_id':'p','llm_chunks':[{'text':'Results.'}],'fulltext_provenance':{'artifact_path':'a.json'}}
    metadata={'study_title':'A study','abstract':'An abstract.'}
    source={'mode':'full_text_packet'}
    hashed={**packet,'fulltext_provenance':{**packet['fulltext_provenance'],'artifact_sha256':'a'*64}}
    assert source_fingerprint_for_task(text_source=source,metadata=metadata,packet=packet)==\
        source_fingerprint_for_task(text_source=source,metadata=metadata,packet=hashed)
    # The abstract is named as stored, before whitespace is collapsed for the prompt.
    stored=' An  abstract.\n'
    assert source_text_hashes(stored,hashed)=={'artifact_sha256':'a'*64,'abstract_sha256':text_sha256(clean(stored))}
    assert source_text_hashes(float('nan'),None)=={'artifact_sha256':'','abstract_sha256':''}


def test_finding_rows_name_their_text_only_for_the_task_that_produced_them(tmp_path):
    task={'task_id':'t','study_doi':'10.1000/x','paper_metadata':{'abstract':'An abstract.'},
          'text_source':{'mode':'full_text_packet','artifact_sha256':'a'*64,'abstract_sha256':'b'*64}}
    path=tmp_path/'tasks.jsonl';path.write_text(json.dumps(task)+'\n')
    tasks=task_lookup(path)
    item={'compound_or_exposure':'Ketamine','brain_region':'Prefrontal cortex','primary_graph_anchor_kind':'brain_region',
          'finding_summary':'A finding.'}
    result={'task_id':'t','study_doi':'10.1000/x','domain_route':'brain_system','text_depth':'article_text'}
    row=evidence_row_for_item(output_row={'task_id':'t'},result=result,item=item,item_kind='primary_item',item_index=1,tasks=tasks)
    assert (row['source_artifact_sha256'],row['source_abstract_sha256'])==('a'*64,'b'*64)
    # An older output matched to the current task by DOI and domain may have read another text.
    tasks['old']=tasks['t']
    row=evidence_row_for_item(output_row={'task_id':'old'},result={**result,'task_id':'old'},item=item,
                              item_kind='primary_item',item_index=1,tasks=tasks)
    assert (row['source_artifact_sha256'],row['source_abstract_sha256'])==('','')
    secondary={'task_id':'reviewrel:1','source':{'artifact_sha256':'a'*64,'abstract_sha256':''}}
    assert task_text_hashes(secondary,'reviewrel:1')=={'source_artifact_sha256':'a'*64,'source_abstract_sha256':''}
    assert task_text_hashes(secondary,'reviewrel:0')=={'source_artifact_sha256':'','source_abstract_sha256':''}
