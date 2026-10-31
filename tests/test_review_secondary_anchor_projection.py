from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import convert_bundles


def test_secondary_named_objects_preserve_combination_and_qualification():
    statement='The combined treatment may affect 5-HT2A and BDNF; evidence is preliminary.'
    relationship=dict(item_id='R1',relationship_statement=statement,relationship_kind='review_synthesis',
        paper_prominence='paper_defining',graph_eligibility='main_graph',graph_form='combination',
        direction_or_tone='supports',domain_labels=['molecular_target','molecular_pathway_readout'],
        limitations=['Preliminary evidence'],anchors=[
            dict(role='compound',label='Psilocybin',anchor_type='named_entity'),
            dict(role='co_intervention',label='Mindfulness',anchor_type='context'),
            dict(role='target',label='5-HT2A',anchor_type='named_entity'),
            dict(role='pathway_or_process',label='BDNF',anchor_type='named_entity'),
            dict(role='population',label='Healthy adults',anchor_type='named_entity'),
            dict(role='comparator',label='Placebo',anchor_type='named_entity')])
    bundles=[dict(status='ok',study_doi='10.example/review',text_depth='abstract_only',
        result=dict(paper_frame={},relationships=[relationship]))]
    tasks=[dict(study_doi='10.example/review',paper_metadata=dict(study_title='Psilocybin and mindfulness'))]
    registry=dict(compounds=[dict(label='Psilocybin',aliases=[])],targets=[],disorders=[])
    base,_=convert_bundles(bundles,tasks,registry,active_candidate_dois={'10.example/review'},project_secondary_named_anchors=False)
    repaired,_=convert_bundles(bundles,tasks,registry,active_candidate_dois={'10.example/review'},project_secondary_named_anchors=True)
    current_default,_=convert_bundles(bundles,tasks,registry,active_candidate_dois={'10.example/review'})
    assert len(base)==1 and len(repaired)==2
    assert current_default==repaired
    assert {r['graph_entity_label'] for r in repaired}=={'5-HT2A','BDNF'}
    assert all(r['support']==statement and r['notes']=='Preliminary evidence' for r in repaired)
    assert all(r['graph_subject_label']=='Psilocybin + Mindfulness' for r in repaired)
    assert {r['entity_role'] for r in repaired}.isdisjoint({'population','comparator'})
