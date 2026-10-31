"""Reconcile a retrieval checkpoint into the existing manual-recovery owner."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/provider_browser_pass_20261020'
OWNER = ROOT / 'data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/manual_chrome_batches_20261019'

def main():
    results = pd.read_csv(RUN/'progress.csv').fillna('').set_index('doi').to_dict('index')
    frozen = pd.read_csv(RUN/'frozen_candidates.csv').fillna('').set_index('doi').to_dict('index')
    imports, conversions = {}, {}
    held_review_proofs = {}
    held_import_reviews = []
    for proof_path in sorted(RUN.glob('source_identity_hold_*.json')):
        proof = json.loads(proof_path.read_text())
        if (proof.get('decision') == 'hold_source_identity'
                and proof.get('canonical_import_for_requested_record') is False):
            held_review_proofs[proof['downloaded_pdf_sha256']] = (proof_path, proof)
    for receipt in sorted(RUN.glob('import_applied_*.json')):
        suffix = receipt.stem.removeprefix('import_applied_')
        conversion_path = RUN/f'conversion_{suffix}.json'
        if not conversion_path.exists():
            continue
        report = json.loads(receipt.read_text())
        assert report['counts']['conflicts'] == 0
        if report['counts']['needs_review']:
            # A reviewed wrong-source file remains withheld even when a later
            # download recovers the correct report. Keep the raw import receipt.
            reviews = report['review']
            assert len(reviews) == report['counts']['needs_review']
            for review in reviews:
                digest = review['source_sha256']
                assert digest in held_review_proofs, (receipt, review)
                proof_path, proof = held_review_proofs[digest]
                held_file = Path(review['file'])
                assert held_file.name == proof['requested_doi'].replace('/', '_') + '.pdf'
                assert hashlib.sha256(held_file.read_bytes()).hexdigest() == digest
                assert all(r['source_sha256'] != digest for r in report['imported'])
                held_import_reviews.append(dict(receipt=str(receipt), file_sha256=digest,
                                                source_identity_hold=str(proof_path)))
        imports.update({r['doi']:r for r in report['imported']
                        if results.get(r['doi'], {}).get('status') in
                        {'pdf_saved_pending_batch_validation', 'article_pdf_recovered', 'pdf_saved_language_review'}})
        c = json.loads(conversion_path.read_text())
        assert c['counts']['selected'] == c['counts']['with_success']
        conversions.update({r['study_doi']:r for r in c['records']
                            if r.get('write_status') == 'successful extraction with verified source identity'
                            and int(r.get('best_char_count', 0)) > 0
                            and Path(r.get('artifact_path', '')).is_file()})
    saved = {d:r for d,r in results.items() if r['status'] in {'pdf_saved_pending_batch_validation','article_pdf_recovered','pdf_saved_language_review'}}
    assert set(imports) == set(conversions) and set(imports) <= set(saved), (len(saved),len(imports),len(conversions))
    language_holds = {d for d,r in saved.items() if r['status'] == 'pdf_saved_language_review'}
    verified = {}
    for doi in imports:
        r = saved[doi]
        f = Path(imports[doi]['destination'])
        assert f.read_bytes()[:5] == b'%PDF-'
        assert hashlib.sha256(f.read_bytes()).hexdigest() == r['sha256']
        if doi not in language_holds:
            verified[doi] = str(f)

    display = pd.DataFrame([dict(doi=d,**r) for d,r in results.items()])
    display['verification_status'] = display.doi.map(lambda d:'identity_verified_imported_converted' if d in verified else 'retrieval_observation')
    display['canonical_pdf_path'] = display.doi.map(verified).fillna('')
    display.to_csv(RUN/'progress.csv',index=False)

    backup = RUN/'manual_owner_before'
    backup.mkdir(exist_ok=True)
    if not (backup/'progress.csv').exists(): shutil.copy2(OWNER/'progress.csv',backup/'progress.csv')
    progress = pd.read_csv(OWNER/'progress.csv').fillna('').set_index('doi').to_dict('index')
    for doi, result in results.items():
        row = progress.get(doi,dict(frozen[doi]))
        row['manual_status'] = 'article_pdf_recovered' if doi in verified else result['status']
        row['manual_notes'] = ('Recovered in external Chrome, document identity verified, imported and converted locally. Do not download again.'
                               if doi in verified else result['evidence'])
        if doi in verified: row.update(canonical_pdf_path=verified[doi],saved_pdf_path=verified[doi])
        progress[doi] = row
    pd.DataFrame([dict(doi=d,**r) for d,r in progress.items()]).to_csv(OWNER/'progress.csv',index=False)

    checkpoint_path = RUN/f'checkpoint_{len(results):03d}.json'
    changed, prepared = [], {}
    for folder in sorted(OWNER.glob('batch_[0-9][0-9][0-9]')):
        if int(folder.name[-3:]) < 3: continue
        mf = folder/'manifest.json'
        manifest = json.loads(mf.read_text())
        for row in manifest['papers']: prepared[row['doi']] = row
        touched = [r for r in manifest['papers'] if r['doi'] in results]
        if not touched: continue
        dest = backup/folder.name; dest.mkdir(exist_ok=True)
        for name in ['manifest.json','papers.csv','index.html']:
            if not (dest/name).exists(): shutil.copy2(folder/name,dest/name)
        defaults = {}
        for row in touched:
            d = row['doi']; r = progress[d]
            for k in ['manual_status','manual_notes','canonical_pdf_path','saved_pdf_path']:
                if k in r: row[k] = r[k]
            if d in verified or r['manual_status']=='publisher_paywall_observed':
                defaults[d] = dict(handled=True,note=r['manual_notes'])
        manifest['recovered_pdf_count'] = sum(r.get('manual_status')=='article_pdf_recovered' for r in manifest['papers'])
        manifest['publisher_paywall_observed_count'] = sum(r.get('manual_status')=='publisher_paywall_observed' for r in manifest['papers'])
        manifest['provider_recovery_checkpoint'] = str(checkpoint_path)
        mf.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        pd.DataFrame(manifest['papers']).to_csv(folder/'papers.csv',index=False)
        page = (folder/'index.html').read_text()
        for row in touched:
            d=row['doi']; label = ('PDF recovered and converted' if d in verified else
                                    'Publisher purchase/access barrier observed' if row['manual_status']=='publisher_paywall_observed' else
                                    'Browser follow-up remains: '+row['manual_status'])
            pattern = r'(<article data-doi="'+re.escape(html.escape(d,quote=True))+r'">)'
            page=re.sub(pattern+r'<p data-provider-recovery="20261020">.*?</p>',lambda m:m[1],page,count=1,flags=re.S)
            page, n = re.subn(pattern,lambda m:m[1]+'<p data-provider-recovery="20261020"><strong>'+html.escape(label)+'</strong></p>',page,count=1)
            assert n==1, (folder,d)
        encoded = json.dumps(defaults,ensure_ascii=False).replace('<','\\u003c')
        script = "const providerRecoveryDefaults="+encoded+";for(const [doi,value] of Object.entries(providerRecoveryDefaults)){if(!saved[doi])saved[doi]=value;}\n"
        marker = "document.querySelectorAll('article').forEach"
        assert marker in page
        page=re.sub(r'const providerRecoveryDefaults=.*?\n', '',page,count=1)
        page=page.replace(marker,script+marker,1)
        (folder/'index.html').write_text(page)
        changed.append(folder.name)

    assert set(verified) <= set(prepared)
    recovered_prepared = {d for d,r in prepared.items() if r.get('manual_status')=='article_pdf_recovered'}
    checkpoint = dict(at_utc=datetime.now(timezone.utc).isoformat(),status='in_progress',
                      frozen_scope=len(frozen),checked=len(results),not_yet_checked=len(frozen)-len(results),
                      new_verified_usable_fulltexts=len(verified),new_verified_pdf_bytes=sum(int(saved[d]['bytes']) for d in verified),
                      downloaded_pending_verification=len(saved)-len(verified)-len(language_holds),
                      source_language_holds=len(language_holds),
                      outcomes=pd.Series([r['status'] for r in results.values()]).value_counts().astype(int).to_dict(),
                      prepared_records=len(prepared),prepared_recovered=len(recovered_prepared),
                      prepared_not_yet_recovered=len(prepared)-len(recovered_prepared),
                      changed_manual_batches=changed,previous_user_batches_preserved=[1,2],model_calls=0,
                      explicitly_withheld_import_reviews=held_import_reviews,
                      canonical_pdf_paths=verified)
    state_path=ROOT/'data/processed/corpus/model_pipeline_state.json'
    state=json.loads(state_path.read_text())
    if not (RUN/'model_pipeline_state_before.json').exists(): shutil.copy2(state_path,RUN/'model_pipeline_state_before.json')
    state['manual_fulltext_recovery_handoff'].update(
        new_verified_fulltexts_since_input_refresh=len(recovered_prepared),
        latest_recovery_receipt=str(checkpoint_path),
        remaining_unresolved_prepared_papers=len(prepared)-len(recovered_prepared))
    state['extraction_input_status']='provisional_manual_fulltext_pending_refresh'
    state_path.write_text(json.dumps(state,ensure_ascii=False)+'\n')
    route=ROOT/'data/processed/corpus/paper_domain_routing.parquet'
    checkpoint['canonical_screening_sha256']=hashlib.sha256(route.read_bytes()).hexdigest()
    assert checkpoint['canonical_screening_sha256']==state['screening_table_sha256']
    checkpoint_path.write_text(json.dumps(checkpoint,indent=2,ensure_ascii=False)+'\n')
    (RUN/'latest_checkpoint.json').write_text(json.dumps(checkpoint,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in checkpoint.items() if k not in ['canonical_pdf_paths','changed_manual_batches']},indent=2))

if __name__=='__main__': main()
