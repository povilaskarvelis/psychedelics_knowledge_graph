import json

from pipeline.extract.build_extraction_tasks import source_fingerprint_for_task
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
          'text_source':{'mode':'full_text_packet'},'content':{'title':metadata['study_title'],'abstract':metadata['abstract'],'packet':packet}}
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
