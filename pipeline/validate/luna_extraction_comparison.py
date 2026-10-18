"""Frozen Luna-only extraction experiment. Never promotes production evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import copy
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from jsonschema import Draft7Validator
from pipeline import llm
from pipeline.extract import route_extraction_profiles as profiles
from pipeline.extract import run_route_extraction as primary
from pipeline.extract import run_review_relationship_extraction as review
from pipeline.extract import run_meta_analysis_v2_batch_api as meta
from pipeline.extract.io_utils import text_parts_from_packet

OUT = ROOT / 'data/processed/evaluation/luna_extraction_comparison_20261017'
AUDIT = ROOT / 'data/processed/evaluation/extraction_design_audit_20261017'


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text())
def rows(path): return [json.loads(s) for s in Path(path).open() if s.strip()]
def save(path, value): llm.atomic_json(path, value)
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def write_rows(path, data):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data))


def object_schema(props):
    return dict(type='object',properties=props,required=list(props),additionalProperties=False)


STR={'type':'string'}
STRINGS={'type':'array','items':STR}
FACT_SCHEMA=object_schema(dict(fact_id=STR, domains=STRINGS, statement=STR, source_excerpt=STR,
    source_locator=STR, attribution_details=STR, essential_qualification=STR,
    importance={'type':'string','enum':['central','material_qualification']},
    evidence_status={'type':'string','enum':['empirical','synthesis','descriptive','hypothesis','recommendation','gap']}))
REFERENCE_SCHEMA=object_schema(dict(source_identity=STR, paper_purpose=STR,
    eligible_for_requested_family={'type':'boolean'}, source_limitations=STRINGS,
    central_facts={'type':'array','items':FACT_SCHEMA,'maxItems':10},
    domains_without_reported_findings=STRINGS, ambiguities=STRINGS))

REFERENCE_INSTRUCTION='''Read the supplied research source and create an evaluation reference inventory before any candidate extraction outputs exist. You receive the requested evidence family and domains, the domain definitions, bibliographic metadata, and the exact available source text. Use only the supplied source.

Identify the paper's purpose and up to ten central eligible findings or conclusion-changing qualifications. The inventory must cover the requested domains when the source actually reports findings in them. For primary research, retain original measured findings, including null, qualitative and descriptive results; exclude background and cited results. For reviews, preserve the central synthesis, proposal, uncertainty or research need without converting it into an established causal effect. For quantitative syntheses, preserve distinct main comparisons and their uncertainty. For guidelines, preserve recommendations as recommendations, their strength, scope and evidence limitations.

Each fact must be a complete, narrow proposition with one short contiguous verbatim source excerpt and its locator. Preserve the compound or complete package, outcome or entity, population, comparator, timepoint and analyzed denominator when they matter. Put necessary analysis details in attribution_details; a general study sample size must not become the denominator for every endpoint. Separate the direction of a measured change from whether it is beneficial. Distinguish baseline comparisons from control comparisons and association from causation. Preserve reported ranges without inventing separate estimates. If a qualification materially changes the main conclusion, represent it as a fact or in essential_qualification. Use several applicable domain labels for the same fact rather than duplicate it.

Use an empty central_facts array if the source has no eligible findings for the requested family/domains; explain source limitations or ambiguity. The review unit is the supplied text: absent tables and full text cannot be reconstructed. Each source_excerpt must be copied verbatim from the supplied source, without ellipses joining different passages. Return only the specified JSON.'''

CLARIFICATIONS={
'primary': '''## Finding identity and source attribution

Identify the original result before filling fields. Keep the full intervention package together when its components were not tested independently. Name the particular measured outcome or biological entity; use population and recruitment context as context rather than as a substitute for that outcome. A task, scale, pathway family and its measured construct or marker can be different entities.

Bind each reported statistic to its own outcome, comparison, population or experimental system, and assessment time. Use the analyzed subgroup denominator when given; keep the overall recruited sample separate in wording. Separate results when their comparisons, outcomes or conclusions differ. A longitudinal summary may retain several labeled timepoints only when their values and denominators remain unambiguous. Include central null results and conclusion-changing qualifications. Extract a nonpsychedelic comparator only as part of the relevant comparison, rather than as unrelated standalone evidence. Locators must point to the source of the original result.
''',
'review': '''## Entity and qualification checks

Preserve one anchor for each distinct named entity needed by the proposition. Several named hormones, receptors, networks, outcomes or adverse effects should have separate anchors rather than one comma-separated anchor. Keep a true combination or interaction as one proposition with all its participants. Use a class anchor when the source supports only a class conclusion.

Keep differences between named treatments, important null or mixed conclusions, and qualifications about uncontrolled, preclinical or preliminary evidence. Select paper importance by the review's own objective and conclusion: material that is interesting or lengthy is not automatically central. Interpret research themes as themes, proposals as proposals, and recommendations as recommendations. Check that all central aspects and necessary qualifications are represented before assigning graph importance.
''',
'meta': '''## Analysis identity and reported summaries

One effect-estimate object must describe one reported estimate for one outcome, comparison, population or subgroup, and assessment window. Separate ketamine-versus-midazolam from ketamine-versus-saline, and separate arm-specific response rates from between-arm contrasts. Never pack several labeled point estimates, bounds or p values into one scalar field. Heterogeneity components and evidence counts are context, not additional treatment effects.

If the source gives only a range across outcomes or timepoints, retain that range in the relationship statement and extraction_uncertainties. Leave the point estimate unset instead of inventing its assignment to a particular result. Each network comparison must populate its structured treatment_a and treatment_b/reference details, preserving whether the reference came from a different trial context. Use the reported analysis criterion and scale when interpreting estimates; preserve uncertainty even if the authors use optimistic wording.
''',
'guideline': '''## Recommendation attribution

Keep recommendations, consensus judgments and empirical findings distinct. Preserve the exact population, intervention or package, recommended action, recommendation strength and any condition or evidence limitation. Use one item per materially different recommendation. A recommended monitoring or care component is not evidence that the component independently improves clinical outcomes. Preserve uncertainty and do not infer a stronger recommendation from positive introductory wording.
'''}


def revised_instruction(base, family):
    scope='''## Substance and source eligibility

The evidence concerns classic psychedelics, MDMA and related entactogens, ketamine/esketamine/arketamine and their analogues, ibogaine/noribogaine, salvinorin A, and related psychedelic compounds. This list is illustrative. An unrelated stimulant, cannabinoid, drug-development experiment or generic receptor mechanism is not eligible solely through structural similarity or an NPS label. A mixed-drug study can provide eligible drug-specific or co-use findings, but group-level effects cannot be assigned to one component without support. Keep a nonpsychedelic comparator attached to its relevant comparison. For ketamine-class studies, apply the approved psychiatric, addiction, psychological-therapy or other psychedelic-related question; anesthesia, sedation, analgesia and veterinary anesthesia alone do not establish eligibility. Source preselection does not establish extractable evidence. Use the appropriate empty-output status when no eligible finding for this task is actually supported.

'''
    add=scope+CLARIFICATIONS[family]
    for heading in ['## Rules','## Final check','## Output']:
        if heading in base:
            return base.replace(heading,add+'\n'+heading,1)
    return base+'\n\n'+add


def strip_schema_descriptions(value, *, property_map=False):
    """Remove schema annotations without deleting a scientific description field."""
    if isinstance(value,list):
        for item in value:strip_schema_descriptions(item)
    elif isinstance(value,dict):
        if not property_map:value.pop('description',None)
        for key,item in value.items():strip_schema_descriptions(item,property_map=key=='properties')


def grounded_primary_instruction(base):
    """Development candidate: reorder the common contract; retain domain scope."""
    scope=base.split('## Scope',1)[1].split('## Extraction Outcome',1)[0].strip()
    return '''# Extract original psychedelic research findings

Read the supplied source and return source-supported original findings for the assigned domain using the supplied JSON schema.

## 1. Establish evidence eligibility before filling items
Task routing and prior screening do not establish eligibility. Verify that the source reports an original result about a psychedelic/entactogen exposure, its complete intervention package, its use context, or a directly tested related mechanism. Eligible exposures include classic psychedelics, MDMA and related entactogens, ketamine/esketamine/arketamine and their analogues, ibogaine/noribogaine, salvinorin A, and related psychedelic compounds. An unrelated stimulant, cannabinoid, generic receptor experiment, or drug-development trial does not qualify solely because it has an NPS label or appears in this task queue.

An experiment directly investigating an eligible drug's own effects, mechanisms, pharmacokinetics, toxicity or modification of those effects can qualify, including healthy volunteers, animal models, cells, and rescue or prevention of drug toxicity. It need not demonstrate psychiatric therapeutic benefit. Exclude a drug used merely as an assay reagent, radioligand, challenge probe or comparator to characterize a different nonpsychedelic treatment when its own effects are not a substantive question. A control drug does not make a genuine drug experiment peripheral.

Mixed-drug research can supply eligible drug-specific and co-use findings. Do not assign whole-group effects to one component. A nonpsychedelic comparator or mechanism belongs only within its relevant psychedelic comparison. Exclude ketamine-class work focused on anesthesia, sedation, analgesia/pain treatment or veterinary anesthesia; safety monitoring inside such an otherwise excluded study does not make it eligible. Include substantive psychiatric endpoints even around surgery, and direct research centered on the drug's own otherwise eligible mechanisms, exposure or nonmedical toxicity. Apply the research-purpose rule rather than requiring therapeutic benefit or excluding a paper because of its setting.

When no eligible original finding exists for this task, return an empty items array, the appropriate non-extracted status, and a short source-based warning. Do not fill the schema with unrelated results. Use wrong_source_type for a review or other non-primary source; not_relevant for clearly unrelated evidence; no_extractable_scoped_evidence when the paper is relevant but this domain has no usable original finding; human_review for unresolved source or scope ambiguity.

## 2. Apply the assigned scientific domain
'''+scope+'''

## 3. Preserve each finding's scientific identity
Extract the main original findings, including central null, qualitative and descriptive results and conclusion-changing qualifications. Keep a complete intervention package together when its components were not independently tested. Identify the actual measured outcome, entity, marker or construct rather than replacing it with a scale, assay, population or broad neighboring concept. Do not extract cited/background findings as original results.

Bind every statistic to its own outcome, contrast, experimental system, analyzed population and assessment time. Use an endpoint denominator only when the source identifies it; an overall sample size is study context, not automatically the denominator for every assay. Separate materially different comparisons or conclusions. Retain useful qualitative findings when numerical details are unavailable.

Use only the supplied source. If text extraction merges table columns, damages a value or creates conflicting units or directions, preserve the interpretable finding, leave the unresolved value not_reported and add a warning. Do not repair numbers from memory, infer missing table cells, or turn a reported range into guessed point estimates.

## 4. Check consistency before returning
The controlled fields must agree with the exact source wording and with the item's free text. Use mouse_model only for mice; use animal_model for other animal species when available. Measurements on isolated tissue or cells are ex_vivo/in_vitro as appropriate, even if the organism was dosed in vivo. Never replace an unavailable category with a biologically different one. Do not infer therapeutic benefit from the direction of a biological change, and preserve association, hypothesis, recommendation and empirical-effect distinctions.

## 5. Return the domain contract
Return exactly one JSON object matching the supplied schema. Use not_reported for unavailable details and not_applicable only for fields that do not apply. Keep statistics and locators concise. Use supplied locators for article text and Abstract for abstract-only evidence; do not reconstruct unavailable sections. Add abstract_only_limited_detail for abstract-only input and flag material uncertainty. For a non-extracted status, leave items empty and explain the reason briefly in warnings. Return JSON only.
'''


def freeze():
    if (OUT/'freeze.json').exists(): return read(OUT/'freeze.json')
    task_splits={s:rows(AUDIT/f'fresh_{s}_tasks.jsonl') for s in ['development','holdout']}
    paper_splits={s:rows(AUDIT/f'fresh_{s}_papers.jsonl') for s in task_splits}
    wanted={t['study_doi'] for ts in task_splits.values() for t in ts}
    packet_paths=set()
    for ts in task_splits.values():
        for t in ts:
            source=t.get('text_source',{}) or t.get('source',{})
            path=source.get('packet_source_path') or source.get('packet_path')
            if path: packet_paths.add(path)
    packets={}
    for path in sorted(packet_paths):
        with Path(path).open() as handle:
            for line in handle:
                packet=json.loads(line)
                doi=packet.get('study_doi') or packet.get('doi')
                if doi in wanted:
                    if packet.get('packet_id'): packets[packet['packet_id']]=packet
                    packets.setdefault(doi,packet)
    cases=[]; papers=[]
    for split, tasks in task_splits.items():
        paper_lookup={p['study_doi']:p for p in paper_splits[split]}
        grouped=defaultdict(list)
        for task in tasks:
            doi=task['study_doi']; family=paper_lookup[doi]['family']
            depth=primary.text_depth_for_task(task) if family in {'primary','guideline'} else task['text_depth']
            source_info=task.get('text_source',{}) or task.get('source',{})
            packet=packets.get(source_info.get('packet_id')) or packets.get(doi)
            if depth=='article_text' and packet is None: raise ValueError(f'Missing selected source: {doi}')
            if family in {'primary','guideline'}:
                frozen_task=copy.deepcopy(task)
                if packet: frozen_task.setdefault('content',{})['packet']=packet
                content=primary.build_contents(frozen_task)
                source=primary.article_or_abstract_text_for_task(frozen_task)[1]
                profile=primary.profile_for_task(task); domain=primary.domain_route_for_task(task)
                schema=profiles.schema_for_assigned_domain(profiles.load_schema_for_profile(profile,domain),domain)
                instruction=profiles.build_system_instruction(profile,schema,'native',domain_route=domain,text_depth=depth)
                schema=profiles.schema_for_native(schema)
            else:
                module=review if family=='review' else meta
                content=module.model_contents(task,packet); source=module.source_text_for_task(task,packet)
                schema=read(module.BUNDLE_SCHEMA if family=='review' else module.OUTPUT_SCHEMA)
                if family=='meta' and depth=='abstract_only': schema['definitions']['evidence_locator']['properties']['location']['enum']=['title','abstract']
                if family=='meta' and depth=='article_text': schema['definitions']['evidence_locator']['properties']['location'].pop('enum',None)
                schema=profiles.schema_for_native(schema)
                if family=='meta':
                    strip_schema_descriptions(schema)
                instruction=(module.FULL_TEXT_PROMPT if depth=='article_text' else module.ABSTRACT_PROMPT).read_text().strip()
                domain='all_paper_domains'
            if not source.strip():raise ValueError(f'Empty source: {doi}')
            c=dict(case_id=task['task_id'],paper_id=family+':'+doi,study_doi=doi,family=family,split=split,text_depth=depth,domain=domain,task=task,content=content,source_text=source,schema=schema,instructions=instruction,source_sha256=digest(source))
            cases.append(c);grouped[doi].append(c)
        for doi, group in grouped.items():
            source=group[0]['source_text']
            assert all(c['source_text']==source for c in group)
            domains=sorted({c['domain'] for c in group})
            scope='\n\n'.join(profiles.domain_prompt_path(d).read_text() for d in domains if profiles.domain_prompt_path(d))
            papers.append(dict(paper_id=group[0]['paper_id'],study_doi=doi,family=group[0]['family'],split=split,text_depth=group[0]['text_depth'],source_text=source,source_sha256=digest(source),domains=domains,scope=scope,metadata=group[0]['task'].get('paper_metadata',{})))
    assert len(papers)==192 and len(cases)==304 and len({p['study_doi'] for p in papers})==192
    write_rows(OUT/'cases.jsonl',cases);write_rows(OUT/'papers.jsonl',papers)
    manifest=dict(frozen_at=now(),papers=192,cases=304,cases_sha256=hashlib.sha256((OUT/'cases.jsonl').read_bytes()).hexdigest(),papers_sha256=hashlib.sha256((OUT/'papers.jsonl').read_bytes()).hexdigest(),model=llm.DEFAULT_MODEL,reasoning_effort='low',local_budget_usd=5,production_extraction=False)
    save(OUT/'freeze.json',manifest)
    for family,text in CLARIFICATIONS.items():(OUT/'contracts'/f'clarification_{family}.md').write_text(text)
    (OUT/'contracts/reference_instruction.txt').write_text(REFERENCE_INSTRUCTION)
    save(OUT/'contracts/reference_schema.json',REFERENCE_SCHEMA)
    return manifest


@contextmanager
def local_ledger():
    with (OUT/'cost.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        ledger=read(OUT/'cost.json') if (OUT/'cost.json').exists() else dict(limit_usd=5,entries={})
        yield ledger
        save(OUT/'cost.json',ledger)


def execute(stage, jobs, workers=8, *, result_transform=None):
    api=llm.client(primary.api_key_from_env(argparse.Namespace(env_file=str(ROOT/'.env'))))
    def one(job):
        key=job['key']; result_path=OUT/stage/'results'/(digest(key)[:24]+'.json')
        if result_path.exists():return read(result_path)
        config=llm.generation_config(system_instruction=job['instructions'],schema=job['schema'],max_output_tokens=job.get('max_output_tokens',16384))
        body=llm.request_body(model=llm.DEFAULT_MODEL,contents=job['content'],config=config)
        ceiling=llm.reservation_cost(body)
        local_key=stage+':'+key
        with local_ledger() as ledger:
            if local_key not in ledger['entries']:
                committed=sum(e.get('actual_usd',e['reserved_usd']) for e in ledger['entries'].values())
                if committed+ceiling>ledger['limit_usd']:raise RuntimeError('Local $5 evaluation budget would be exceeded')
                ledger['entries'][local_key]=dict(reserved_usd=ceiling,request_sha256=digest(body))
            elif ledger['entries'][local_key]['request_sha256']!=digest(body):raise ValueError('Frozen request changed; use a new stage')
        start=dt.datetime.now().timestamp()
        response=llm.generate_structured(api,model=llm.DEFAULT_MODEL,contents=job['content'],config=config,raw_path=OUT/stage/'responses'/(digest(key)[:24]+'.json'))
        result=json.loads(response.text)
        cost=llm.token_cost(response.usage)
        with local_ledger() as ledger:ledger['entries'][local_key]['actual_usd']=cost
        transport_metadata = {}
        if result_transform is not None:
            result, transport_metadata = result_transform(result, job)
        errors=[e.message for e in Draft7Validator(job['schema']).iter_errors(result)]
        record=dict(key=key,paper_id=job.get('paper_id'),case_id=job.get('case_id'),model=llm.DEFAULT_MODEL,result=result,raw_text=response.text,identity_transport=transport_metadata,schema_errors=errors,usage=response.usage,cost_usd=cost,latency_seconds=dt.datetime.now().timestamp()-start,request_sha256=digest(body),completed_at=now())
        save(result_path,record)
        return record
    errors=[];done=0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(one,job):job['key'] for job in jobs}
        for future in as_completed(pending):
            key=pending[future]
            try:future.result()
            except Exception as exc:
                errors.append(dict(key=key,error_type=type(exc).__name__,error=str(exc)[:1500]))
            done+=1
            if done%10==0 or done==len(jobs):
                with local_ledger() as ledger:spent=sum(e.get('actual_usd',0) for e in ledger['entries'].values())
                print(json.dumps(dict(stage=stage,done=done,total=len(jobs),errors=len(errors),spent_usd=round(spent,5))),flush=True)
    report=dict(stage=stage,expected=len(jobs),completed=sum(1 for j in jobs if (OUT/stage/'results'/(digest(j['key'])[:24]+'.json')).exists()),errors=errors,at=now())
    save(OUT/stage/'report.json',report)
    return report


def reference_jobs():
    for p in rows(OUT/'papers.jsonl'):
        content=json.dumps({k:p[k] for k in ['family','domains','scope','metadata']},ensure_ascii=False)+'\n\nSOURCE_TEXT:\n'+p['source_text']
        yield dict(key=p['paper_id'],paper_id=p['paper_id'],instructions=REFERENCE_INSTRUCTION,content=content,schema=REFERENCE_SCHEMA,max_output_tokens=6000)


def extract_jobs(split,variant):
    exclusions=read(OUT/'cohort_exclusions.json').get('paper_ids',[]) if (OUT/'cohort_exclusions.json').exists() else []
    for c in rows(OUT/'cases.jsonl'):
        if c['split']!=split or c['paper_id'] in exclusions:continue
        if variant=='grounded' and c['family']!='primary':continue
        instruction=c['instructions'] if variant=='baseline' else (grounded_primary_instruction(c['instructions']) if variant=='grounded' else revised_instruction(c['instructions'],c['family']))
        schema=copy.deepcopy(c['schema'])
        if variant=='structured':
            if c['family']!='meta':continue
            item=schema['properties']['synthesis_results']['items']
            estimate=item['properties']['effect_estimate']
            estimate['properties']['estimate']['pattern']=r'^[<>≤≥~≈]?\s*[-+]?(?:\d+(?:[.,]\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*%?$'
            item['properties']['result_representation']={'type':'string','enum':['single_estimate','reported_summary','non_estimate_finding']}
            item['required'].append('result_representation')
            instruction+='\n\n## Quantitative representation\nUse single_estimate for one estimate; estimate contains only its reported scalar value, including an inequality or percent if present. Keep units and metric in their own fields. Use reported_summary for a range or contrast whose individual estimates cannot be assigned from the source; retain exact wording in relationship_statement and extraction_uncertainties, leaving effect_estimate.estimate absent. Use non_estimate_finding for a material qualitative assessment. Never invent a point estimate to satisfy the schema. Create separate result objects for independently reported outcomes, comparisons, subgroups or assessment windows.'
        yield dict(key=c['case_id'],case_id=c['case_id'],paper_id=c['paper_id'],instructions=instruction,content=c['content'],schema=schema,max_output_tokens=24576 if c['family']=='meta' else 16384)


def paper_centered_jobs(split):
    grouped=defaultdict(list)
    for c in rows(OUT/'cases.jsonl'):
        if c['split']==split and c['family']=='primary':grouped[c['paper_id']].append(c)
    for key,group in grouped.items():
        output_props={c['domain']:c['schema'] for c in group}
        schema=object_schema(dict(domain_results=object_schema(output_props)))
        rules='\n\n'.join(c['instructions'] for c in group)
        instruction='Read this primary study once and return all requested domain outputs. Identify the original central findings across the paper, then fill each requested domain contract. Retain appropriate cross-domain findings in their requested domains without turning background or methods into results. Each domain must use its supplied task/route identity and its own scientific schema. The source is supplied only once; the domain instructions below govern their respective outputs.\n\n'+rules
        content=json.dumps(dict(domain_identities={c['domain']:primary.output_identity_for_task(c['task']) for c in group},paper_metadata=group[0]['task'].get('paper_metadata',{})),ensure_ascii=False)+'\n\nSOURCE_TEXT:\n'+group[0]['source_text']
        yield dict(key=key,paper_id=key,instructions=instruction,content=content,schema=schema,max_output_tokens=24576)


ERROR_SCHEMA=object_schema(dict(item_id=STR,severity={'type':'string','enum':['material','minor']},
    error_type={'type':'string','enum':['unsupported','wrong_attribution','overstated_causality_or_certainty','wrong_entity','wrong_number','lost_qualification','scope','other']},description=STR,source_excerpt=STR))
ARM_SCORE=object_schema(dict(covered_fact_ids=STRINGS,partially_covered_fact_ids=STRINGS,
    lost_qualification_fact_ids=STRINGS,errors={'type':'array','items':ERROR_SCHEMA},assessment=STR))
JUDGE_SCHEMA=object_schema(dict(X=ARM_SCORE,Y=ARM_SCORE,reference_issues=STRINGS))
JUDGE_INSTRUCTION='''Evaluate two anonymous extraction outputs, X and Y, against the supplied research source and the source-first reference inventory. Variant names, costs and generation settings are hidden. Score each output independently; an error in one does not excuse an error in the other. Equivalent scientific wording is acceptable. A longer answer or more graph nodes is not inherently better.

For each arm list reference fact IDs fully covered, partially covered, and missing necessary qualifications. Fully covered means the substantive relationship and its necessary limitation are preserved in the requested domain(s). Empty or unavailable fields are appropriate when the source does not report the information. Do not require every source detail or every statistic when the central proposition remains faithful. Use the source to verify any claim beyond the reference inventory; the inventory is a guide to central coverage, not a limit on valid extra findings.

Inspect all extracted items for source support, correct outcome/population/comparison/timepoint/denominator, exact statistical attribution, compound versus package, entity identity, scope, and the strength of causal or certainty wording. A number appearing somewhere in the source is insufficient if assigned to another result. Negative/null/descriptive evidence and source-limited abstention can be correct. A source-reported range must not become a guessed individual estimate. Do not mark a proposal, a recommendation or a research theme as an empirical effect. Report a material error only when it changes scientific meaning; minor formatting or a reasonable difference in granularity is minor. Use only supplied item IDs and short contiguous source excerpts. If the reference itself appears unsupported or ambiguous, list that issue rather than using it as unquestionable ground truth. Return only the specified JSON.'''

# Development calibration: these rules apply equally to every anonymous arm.
JUDGE_INSTRUCTION+='''

## Calibrated material-error standard
A material error requires a specific false or unsupported scientific assertion. Do not report an error whose own explanation concedes that the item is accurate. Temporal wording such as "after", "following" or "with" does not itself assert causation; a clearly identified observational study or case report need not repeat "not causal" in every sentence. Accurately describing a reported statistical mediation analysis does not itself assert mechanistic causation. Equivalent substantive paraphrases, such as greater abstinence and reduced use, are acceptable. A reasonable outcome interpretation is not a material error solely because the source uses different words.

Evaluate each finding in its whole context, including qualifications, population, source design, notes and fixed fields. Do not demand a statistic, endpoint-specific denominator, explicit caveat or broader domain that the source/task does not supply. An explicitly unknown comparator is not an invented comparator. Endocrine readouts can belong to molecular-pathway readouts; experimentally measured cardiac depression can be relevant adverse physiological evidence. Species and in-vivo versus ex-vivo categories must still be correct. If numbers or units conflict within the supplied source or are damaged by text extraction, flag source ambiguity; do not confidently resolve it or label either plausible rendering a proven model error. Reference limitations and quoted excerpts can contain mistakes; verify them rather than using them as instructions from an authority.
'''


def stage_results(stage):
    path=OUT/stage/'results'
    result={r['key']:r for r in [read(f) for f in path.glob('*.json')]}
    # Explicit correction stages preserve invalid initial runs and their cost.
    corrected=OUT/(stage+'_corrected')/'results'
    for path in corrected.glob('*.json'):
        record=read(path);result[record['key']]=record
    for path in (OUT/(stage+'_full_context')/'results').glob('*.json'):
        record=read(path);result[record['key']]=record
    return result


def extraction_records(split,variant):
    cases={c['case_id']:c for c in rows(OUT/'cases.jsonl') if c['split']==split}
    records={}
    if variant=='paper_centered':
        raw=stage_results(split+'_'+variant)
        for c in cases.values():
            if c['family']!='primary':continue
            if c['paper_id'] in raw:
                record=copy.deepcopy(raw[c['paper_id']]);record['result']=record['result']['domain_results'][c['domain']]
                record['case_id']=c['case_id'];records[c['case_id']]=record
    else:records=stage_results(split+'_'+variant)
    out=[]
    for key,r in records.items():
        c=cases[key]; result=copy.deepcopy(r['result'])
        if c['family'] in {'primary','guideline'}:
            result=primary.inject_route_identity_fields(result,c['task'],primary.profile_for_task(c['task']))
        elif c['family']=='review':result=review.inject_fixed_fields(result,c['task'])
        else:result,_=meta.normalize_model_result(result,c['text_depth'])
        out.append(dict(case=c,record=r,result=result))
    return out


def normalized_items(record,include_context=False):
    c,result=record['case'],record['result']
    field={'primary':'items','guideline':'recommendation_items','review':'relationships','meta':'synthesis_results'}[c['family']]
    items=[dict(item_id=c['case_id']+':'+str(i),domain=c['domain'],data=item) for i,item in enumerate(result.get(field,[]),1)]
    if include_context:
        identity={'schema_version','task_id','route_id','study_doi','domain_route','paper_type','text_depth','source_type'}
        context={k:v for k,v in result.items() if k!=field and k not in identity}
        if context:items.append(dict(item_id=c['case_id']+':context',domain=c['domain'],context=True,data=context))
    return items


def judge_jobs(split,variant):
    papers={p['paper_id']:p for p in rows(OUT/'papers.jsonl') if p['split']==split}
    references=stage_results('references_reviewed')
    baseline=defaultdict(list);candidate=defaultdict(list)
    for rec in extraction_records(split,'baseline'):baseline[rec['case']['paper_id']].extend(normalized_items(rec,include_context=True))
    for rec in extraction_records(split,variant):candidate[rec['case']['paper_id']].extend(normalized_items(rec,include_context=True))
    mapping=[]
    for pid,items in candidate.items():
        if pid not in baseline:raise ValueError('Missing paired baseline')
        p=papers[pid];swap=int(digest(pid+':'+variant)[:2],16)%2==1
        X,Y=(items,baseline[pid]) if swap else (baseline[pid],items)
        mapping.append(dict(paper_id=pid,X=variant if swap else 'baseline',Y='baseline' if swap else variant,
                            X_items=len(X),Y_items=len(Y)))
        content=json.dumps(dict(family=p['family'],requested_domains=p['domains'],reference=references[pid]['result'],X=X,Y=Y),ensure_ascii=False)+'\n\nSOURCE_TEXT:\n'+p['source_text']
        yield dict(key=pid,paper_id=pid,instructions=JUDGE_INSTRUCTION,content=content,schema=JUDGE_SCHEMA,max_output_tokens=6000)
    save(OUT/(split+'_judge_'+variant)/'blinding_key.json',mapping)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['freeze','references','extract','judge'])
    parser.add_argument('--split',choices=['development','holdout'],default='development')
    parser.add_argument('--variant',choices=['baseline','clarified','structured','paper_centered','grounded'],default='baseline')
    parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.command=='freeze':result=freeze()
    elif args.command=='references':result=execute('references',list(reference_jobs()),args.workers)
    else:
        if not (OUT/'references_frozen.json').exists():raise RuntimeError('Review and freeze source references before extracting variants')
        if args.split=='holdout' and not (OUT/'development_selection.json').exists():raise RuntimeError('Freeze development selection before opening holdout predictions')
        if args.command=='judge':result=execute(args.split+'_judge_'+args.variant,list(judge_jobs(args.split,args.variant)),args.workers)
        else:
            jobs=paper_centered_jobs(args.split) if args.variant=='paper_centered' else extract_jobs(args.split,args.variant)
            result=execute(args.split+'_'+args.variant,list(jobs),args.workers)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
