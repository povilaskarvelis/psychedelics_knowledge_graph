"""Explicit Codex review decisions; preserve every raw Luna judgment."""
from collections import defaultdict
import argparse
from pipeline.validate import luna_extraction_comparison as e


def review_error(pid, error):
    text=error['description'].lower()
    if pid.endswith('10.1017/s1461145708008481') and ('n values' in text or 'antagonist effects varied' in text):
        return 'minor', 'Direct source check: the candidate correctly lists n=14/15 for 0.3 mM and n=20/20 for 3 mM. Its antagonist summary explicitly says effects vary by condition and does not assert antagonism of every combined-drug condition. The alleged material error is not established.'
    if pid.endswith('10.1016/j.toxrep.2025.102018') and 'mdmb' in text:
        return 'minor', 'The cannabinoid-only findings were explicitly removed from required coverage by the logged scope errata. Excluding that unrelated compound is not a material extraction error.'
    if pid.endswith('10.3390/cells12101360') and ('kir4.1' in text or 'binding' in text):
        return 'minor', 'Both outputs explicitly describe functional Ba-sensitive currents attributed to Kir4.1 and disclaim direct binding. The source also reports Kir4.1 surface-density changes; a functional target relationship does not require a binding assay.'
    if pid.endswith('10.4103/1673-5374.268929') and error['error_type']=='scope':
        return 'minor', 'The paper explicitly studies neonatal ketamine neurotoxicity. Apoptosis and later cognitive impairment can be adverse preclinical outcomes as well as molecular/behavioral readouts; a separate formal safety trial is not required.'
    if pid.endswith('10.3389/fphar.2012.00172') and ('sensory memory' in text or 'false-alarm' in text or 'false alarm' in text):
        return 'minor', 'The complete item preserves the H-HD/gum-context limitation and explicitly says the nicotine accuracy benefit was absent with ketamine. The grader allegation overlooks those qualifications.'
    if pid.endswith('10.1093/jat/28.6.481') and ('collection' in text or 'collected' in text):
        return 'indeterminate', 'Exact blood-collection timing is not reported. Emergency-presentation wording is an unverified context field, not a demonstrated false MDMA concentration or time-course result.'
    if pid.endswith('10.1016/j.drugalcdep.2025.112699') and 'which estimates' in text:
        return 'minor', 'The output conservatively leaves a statistical pairing unresolved. This is lost specificity/coverage, rather than a fabricated or wrongly assigned estimate.'
    if pid.endswith('10.1002/hup.960') and ('cortisol' in text or 'prolactin' in text):
        return 'minor', 'Endocrine concentrations fit the molecular-readout scope. Generic biochemical assessment during the infusion is source-supported; an unspecified assay does not establish a material false finding.'
    if pid.endswith('10.1016/j.bbrc.2006.08.082') and ('sb203580' in text or 'pd98059' in text):
        return 'minor', 'The abstract does not spell out inhibitor-to-kinase identity. This is unverified explanatory annotation, while the inhibitor-sensitive measured finding is retained; do not count it as a proven false measured result.'
    if pid.endswith('10.1016/j.forsciint.2023.111597') and 'mixture' in text:
        return 'minor', 'The output uses collective mixture wording and does not explicitly assert that every tablet contained every listed substance.'
    if pid.endswith('10.1016/j.toxrep.2025.102018') and 'mortality' in text and ('collectively' in text or 'separate' in text):
        return 'indeterminate', 'The source states 100% mortality for ketamine derivatives collectively. Separate-derivative attribution is unresolved in the available rendering, not established as false.'
    if pid.endswith('10.1159/000136416') and 'therapeutic index' in text:
        return 'minor', 'The record explicitly preserves the rat LD50/human MED50 ratio. Its safety grouping does not assert a directly measured human adverse-event rate.'
    if pid.endswith('10.1177/0269881106060764') and 'influenc' in text:
        return 'minor', 'The output preserves the source authors wording within an explicitly identified survey. It does not establish an experimental causal mechanism.'
    if pid.endswith('10.17159/sajs.2016/20150425') and 'paired' in text:
        return 'minor', 'The source compares the same participants before and after follow-up using chi-square tests. Calling the data paired does not assert an unreported named statistical procedure.'
    if pid.endswith('10.3109/00952990.2014.973961') and 'denominator' in text:
        return 'indeterminate', 'The abstract gives one clinic sample and its substance-use percentages. A different denominator is not established; report this source limitation rather than a proven numerical error.'
    if pid.endswith('10.3389/fpsyg.2025.1533055') and ('improv' in text or 'direction' in text):
        return 'indeterminate', 'The source abstract/outcome coding and detailed prose conflict on direction. Neither output direction can be adjudicated as a proven factual error from these materials.'
    if pid.endswith('10.1002/hbm.23234') and ('75' in text or 'dose' in text):
        return 'indeterminate', 'Source-unit conflict in metadata versus extracted packet; do not resolve the dose from outside the frozen materials.'
    if 'no material' in text or 'this matches' in text or 'this item matches' in text or 'does not actually assign' in text:
        return 'minor', 'The grader explanation itself concedes accuracy or fails to establish the alleged material assertion.'
    return error['severity'], 'Retained after Codex inspection of the flagged assertion and available source context. This reviews flagged issues, not every unflagged claim.'


def adjudicate(split, variant):
    path=e.OUT/(split+'_judge_'+variant)
    scores=e.read(path/'scores.json');refs=e.stage_results('references_reviewed')
    outputs={arm:defaultdict(list) for arm in ['baseline',variant]}
    for arm in outputs:
        for rec in e.extraction_records(split,arm):outputs[arm][rec['case']['paper_id']].extend(e.normalized_items(rec))
    decisions=[]
    for row in scores:
        for arm,score in row['arms'].items():
            errors=[];uncertain=[]
            for error in score['errors']:
                verdict,reason=review_error(row['paper_id'],error)
                decisions.append(dict(paper_id=row['paper_id'],arm=arm,item_id=error['item_id'],
                    original_severity=error['severity'],reviewed_verdict=verdict,reason=reason,error=error))
                if verdict=='material':errors.append(error)
                if verdict=='indeterminate':uncertain.append(error)
            # Frozen no-eligible-finding controls do not depend on the grader noticing scope.
            if not refs[row['paper_id']]['result']['eligible_for_requested_family']:
                existing={x['item_id'] for x in errors if x['error_type']=='scope'}
                for item in outputs[arm][row['paper_id']]:
                    if item['item_id'] not in existing:
                        errors.append(dict(item_id=item['item_id'],severity='material',error_type='scope',
                            description='Nonempty extraction in a Codex source-reviewed no-eligible-finding control.',source_excerpt='See frozen source and reference scope review.'))
            if row['paper_id']=='primary:10.1556/2054.2024.00381':
                for item in outputs[arm][row['paper_id']]:
                    if item['data'].get('real_world_use_context')=='Clinical care' and not any(x['item_id']==item['item_id'] for x in errors):
                        errors.append(dict(item_id=item['item_id'],severity='material',error_type='wrong_attribution',
                            description='Codex direct source check: a community/peer integration group is coded as Clinical care. The accurate qualitative summary does not correct this structured context field.',
                            source_excerpt='a community-based group that would be self-sustaining'))
            score['reviewed_material_errors']=errors
            score['reviewed_material_error_paper']=bool(errors)
            score['indeterminate_errors']=uncertain
    summary={}
    for family in ['all','primary','review','meta','guideline']:
        selected=[r for r in scores if family=='all' or r['family']==family]
        if not selected:continue
        summary[family]={}
        for arm in ['baseline',variant]:
            facts=sum(r['facts'] for r in selected)
            full=sum(r['arms'][arm]['full'] for r in selected);partial=sum(r['arms'][arm]['partial'] for r in selected)
            summary[family][arm]=dict(papers=len(selected),facts=facts,full=full,partial=partial,
                full_coverage_pct=100*full/facts if facts else None,
                weighted_coverage_pct=100*(full+.5*partial)/facts if facts else None,
                reviewed_material_issue_papers=sum(r['arms'][arm]['reviewed_material_error_paper'] for r in selected),
                indeterminate_issue_papers=sum(bool(r['arms'][arm]['indeterminate_errors']) for r in selected))
    result=dict(split=split,variant=variant,summary=summary,decisions=decisions,
        method='Codex review of flagged issues and frozen abstention controls. Unblinded; AI-assisted reference coverage; not independent human gold or exhaustive claim precision.')
    e.save(path/'codex_review.json',result);e.save(path/'reviewed_scores.json',scores)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--split',required=True);p.add_argument('--variant',required=True);a=p.parse_args()
    print(adjudicate(a.split,a.variant)['summary'])
