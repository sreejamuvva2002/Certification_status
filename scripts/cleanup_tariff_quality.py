"""Review remaining v1 flags from cached text and save a separate v2 revision."""
from __future__ import annotations
import argparse,collections,copy,json,re,sqlite3
from pathlib import Path
import audit_tariff_quality as a
import research_tariffs as t
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'outputs/tariffs/pilot-2026-09-09';V1=ROOT/'outputs/tariffs/quality-audit-v1-2026-09-10';OUT=ROOT/'outputs/tariffs/quality-audit-v2-2026-09-10'
FIELD_MAP={'company_field_non_company_candidate':'company','effective_date_may_be_publication_update':'effective_date','effective_date_relative_without_anchor':'effective_date','county_in_city_field':'city','hts_jurisdiction_unverified':'hts_code'}

def read_jsonl(path):
    with path.open() as f:return [json.loads(line) for line in f]
def context(text,quote,radius=650):
    match=re.search(r'\s+'.join(re.escape(w) for w in quote.split()),text) if quote else None
    pos=match.start() if match else 0;end=match.end() if match else min(1000,len(text))
    return text[max(0,pos-radius):min(len(text),end+radius)]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=OUT);args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if out in {BASE,V1} or BASE in out.parents or V1 in out.parents:raise ValueError('Use a separate revision directory')
    manifestpath=out/'input_manifest.json'
    if not manifestpath.exists():t.dump(manifestpath,{'created_at':t.now(),'original_file_hashes':a.manifest(BASE),'v1_file_hashes':a.manifest(V1)})
    data=read_jsonl(V1/'claims.v1.jsonl');claims={c['claim_id']:c for c in data};flags=read_jsonl(V1/'screening_flags.jsonl');allpairs=read_jsonl(V1/'conflict_review.jsonl');pairs=[r for r in allpairs if r['classification'] in {'apparent_same_scope_conflict','insufficient_scope'}]
    db=sqlite3.connect((BASE/'corpus.sqlite').as_uri()+'?mode=ro',uri=True);chunks={c['chunk_id']:c for c in a.read_rows(db,'chunks')};db.close()
    model=a.LocalModel(out,'http://localhost:11434','qwen3.5:35b-a3b')
    folder=out/'field_reviews';folder.mkdir(exist_ok=True)
    for start in range(0,len(flags),8):
        group=flags[start:start+8];path=folder/f'batch_{start:04d}.json'
        if path.exists() and json.loads(path.read_text()).get('status')=='reviewed':continue
        items=[];props={}
        for r in group:
            c=claims[r['claim_id']];fields=sorted({FIELD_MAP[f] for f in r['flags']});text=chunks[c['chunk_id']]['text']
            items.append({'claim_id':c['claim_id'],'quote':c['statement'],'source_url':c['source_url'],'fields':[{'field':f,'value':c['fields'][f],'support':c['field_support'].get(f),'source_context':context(text,c['field_support'].get(f,''))} for f in fields]})
            props[c['claim_id']]=a.obj({f:a.obj({'decision':a.enum(['retain','clear','needs_external_verification']),'reason':{'type':'string','maxLength':350}}) for f in fields})
        schema=a.obj({'reviews':a.obj(props)})
        try:
            result=model.call('remaining_fields_'+str(start),'Review ONLY flagged field assignments using their cached support and surrounding text. Use retain when the exact field role is supported, clear when misclassified/unsupported, needs_external_verification when the cached material cannot establish it. Company must be a named business, not an agency, government, country, official, generic industry category or the pronoun we. A county in city is misclassified. Update/publication/ruling dates are not automatically tariff effective dates; relative now/today without an absolute anchor is insufficient. A foreign or unspecified HS jurisdiction does not establish US HTS. The audit date is September 10, 2026; 2024/2025 and earlier-2026 dates are historical. Do not invent replacements or claim current law verified.',{'audit_date':'2026-09-10','claims':items},schema)
            if set(result['reviews'])!=set(props):raise ValueError('Missing field review')
            for cid,values in result['reviews'].items():
                if set(values)!=set(props[cid]['properties']) or any(v['decision'] not in ['retain','clear','needs_external_verification'] for v in values.values()):raise ValueError('Invalid field decisions')
            t.dump(path,{'status':'reviewed','reviews':result['reviews']})
        except Exception as e:t.dump(path,{'status':'failed','error':type(e).__name__})
        print('field review',min(start+8,len(flags)),len(flags),json.loads(path.read_text())['status'],flush=True)
    folder=out/'conflict_reviews';folder.mkdir(exist_ok=True)
    for start in range(0,len(pairs),5):
        group=pairs[start:start+5];path=folder/f'batch_{start:04d}.json'
        if path.exists() and json.loads(path.read_text()).get('status')=='reviewed':continue
        evidence=[]
        for r in group:
            evidence.append({'pair_id':r['pair_id'],'previous_classification':r['classification'],'claims':[{'claim_id':cid,'quote':claims[cid]['statement'],'fields':{k:v for k,v in claims[cid]['fields'].items() if v},'url':claims[cid]['source_url'],'context':context(chunks[claims[cid]['chunk_id']]['text'],claims[cid]['statement'],750)} for cid in r['claim_ids']]})
        schema=a.obj({'pairs':a.obj({r['pair_id']:a.obj({'classification':a.enum(a.PAIR_STATUSES),'reason':{'type':'string','maxLength':550},'verification_question':{'type':'string','maxLength':350}}) for r in group})})
        try:
            result=model.call('remaining_conflicts_'+str(start),'Reassess apparent conflicts using the added cached source context. Choose complementary_or_no_conflict for identical/complementary text; different_dates_or_policy_stages for sequential measures or conditional expiry followed by renewal; different_products_origins_or_programs for differing product/origin/program/rate components; insufficient_scope when equal scope/date cannot be established; apparent_same_scope_conflict only for incompatible statements about the same scope and aligned date. Current audit date September 10, 2026: 2024, 2025 and earlier-2026 dates are not future as of this audit. A general rule and exception, general duty and additional surcharge, investigation and final order are not automatically contradictory. Do not verify current law from memory. Give a precise outstanding verification question if needed.',{'audit_date':'2026-09-10','pairs':evidence},schema)
            if set(result['pairs'])!={r['pair_id'] for r in group} or any(r['classification'] not in a.PAIR_STATUSES for r in result['pairs'].values()):raise ValueError('Invalid pair coverage')
            t.dump(path,{'status':'reviewed','pairs':result['pairs']})
        except Exception as e:t.dump(path,{'status':'failed','error':type(e).__name__})
        print('conflict review',min(start+5,len(pairs)),len(pairs),json.loads(path.read_text())['status'],flush=True)
    reviews={};pairreviews={}
    for folder,key,dest in [('field_reviews','reviews',reviews),('conflict_reviews','pairs',pairreviews)]:
        for f in (out/folder).glob('*.json'):
            r=json.loads(f.read_text())
            if r['status']!='reviewed':raise ValueError('Local review failed; resume before exporting')
            dest.update(r[key])
    if set(reviews)!={r['claim_id'] for r in flags} or set(pairreviews)!={r['pair_id'] for r in pairs}:raise ValueError('Incomplete review coverage')
    changes=[]
    for cid,fields in reviews.items():
        c=claims[cid];c['quality_audit']['v2_field_review']=fields
        for field,result in fields.items():
            changes.append({'claim_id':cid,'field':field,'old_value':c['fields'][field],'old_support':c['field_support'].get(field),'decision':result['decision'],'reason':result['reason'],'source_url':c['source_url'],'source_chunk_id':c['chunk_id'],'review_method':result.get('review_method','local_Qwen_cached_context_review'),'original_model_decision':result.get('original_model_decision'),'current_applicability_verified':False})
            if result['decision']!='retain':c['fields'][field]=None;c['field_support'].pop(field,None)
        c['quality_audit']['screening_flags_reviewed_in_v2']=c['quality_audit'].get('screening_flags',[]);c['quality_audit']['screening_flags']=[]
    for c in data:c['quality_audit']['record_version']='quality-v2-2026-09-10';c['quality_audit']['parent_revision']=str(V1)
    for r in allpairs:
        if r['pair_id'] in pairreviews:
            r['v1_classification']=r['classification'];r.update(pairreviews[r['pair_id']]);r['review_status']='Qwen_review_with_added_cached_context';r['resolved']=False
    answers=read_jsonl(V1/'answers.v1.jsonl')
    for r in answers:r['quality_audit']['record_version']='quality-v2-2026-09-10';r['quality_audit']['field_revision_path']=str(out/'claims.v2.jsonl')
    a.write_jsonl(out/'claims.v2.jsonl',data);a.write_jsonl(out/'answers.v2.jsonl',answers);a.write_jsonl(out/'field_review.jsonl',changes);a.write_csv(out/'field_review.csv',changes);a.write_jsonl(out/'conflict_review.jsonl',allpairs);a.write_csv(out/'conflict_review.csv',allpairs)
    manifest=json.loads(manifestpath.read_text())
    if manifest['original_file_hashes']!=a.manifest(BASE) or manifest['v1_file_hashes']!=a.manifest(V1):raise ValueError('Input preservation check failed')
    counts=collections.Counter(r['decision'] for r in changes);pc=collections.Counter(r['classification'] for r in allpairs)
    summary={'completed_at':t.now(),'flagged_claims_reviewed':len(reviews),'field_decisions':dict(counts),'previous_unresolved_pairs_reviewed':len(pairreviews),'all_pair_classifications':dict(pc),'original_and_v1_hashes_match':True,'tavily_calls':0,'current_legal_applicability_verified':False,'claims_exported':len(data),'answers_exported':len(answers),'manual_review_required':'Local Qwen judgments are provisional; cleared/quarantined values remain in the correction history.'}
    t.dump(out/'summary.json',summary);(out/'report.md').write_text('# Cached quality cleanup v2\n\n'+json.dumps(summary,indent=2)+'\n\nAll 173 flagged claim records and 57 remaining pair cases received cached-context review. Unsupported or uncertain flagged fields are cleared in v2, with their originals and reasons preserved in field_review.csv. Retained fields still do not establish current policy. Changed pair classifications explain cached wording; current applicability remains unverified. Both the original corpus and v1 are unchanged.\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
