"""Build one evidence profile per seed company, with explicit source/identity limits."""
from __future__ import annotations
import argparse,collections,json,re,sqlite3
from pathlib import Path
import audit_tariff_quality as a
import research_tariffs as t
import research_company_tariffs as c
import finalize_tariff_quality_audit as quality
ROOT=c.ROOT;OUT=c.OUT;V2=ROOT/'outputs/tariffs/quality-audit-v2-2026-09-10'

def rows(path):
    with path.open() as f:return [json.loads(line) for line in f]
def normalized(text):return ' '+re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()+' '
def identity_scope(company,claim):
    aliases={normalized(c.normalize_name(x)) for x in company['search_aliases'] if len(c.normalize_name(x))>=2}
    quoted=normalized(claim['statement']);field=normalized(c.normalize_name(claim['fields'].get('company') or ''))
    if field in aliases or any(alias in quoted and (len(alias.strip())>=4 or re.search(r'(?<!\w)'+re.escape(alias.strip().upper())+r'(?!\w)',claim['statement'])) for alias in aliases):return 'company_name_matches_cached_evidence'
    # Broad names remain leads; do not merge parent/subsidiary identities.
    first=c.normalize_name(company['company_name']).split()[0]
    if (len(first)>=4 or first in {'kia','bmw','zf'}) and first not in {'first','great','global','southern','superior','thermal','north','blue','down','american'} and normalized(first) in quoted:return 'potential_company_or_group_context'
    return None

def collect(out=OUT):
    companies=rows(out/'companies.jsonl');cached=V2/'claims.v2.jsonl'
    if not cached.exists():raise ValueError('Complete cached v2 cleanup before company profile export')
    claims=rows(cached);claimmap={r['claim_id']:r for r in claims};origin={r['claim_id']:str(c.BASE) for r in claims};seen=set(origin)
    web=out/'web-run';queries=[];states=[];docs=[];answers=[];usage={'request_attempts':0,'estimated':0,'reported':0}
    if (web/'corpus.sqlite').exists():
        db=sqlite3.connect((web/'corpus.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.execute('BEGIN')
        queries=a.read_rows(db,'queries');states=a.read_rows(db,'query_state');docs=a.read_rows(db,'documents');answers=a.read_rows(db,'answers')
        for claim in a.read_rows(db,'claims'):
            # Same claim ID means same source quote. Prefer the newer collection's metadata;
            # retain the cached v2 field corrections when the exact quote already existed.
            if claim['claim_id'] not in seen:
                claims.append(claim);origin[claim['claim_id']]=str(web);seen.add(claim['claim_id']);claimmap[claim['claim_id']]=claim
            else:
                existing=claimmap[claim['claim_id']];existing['query_ids']=sorted(set(existing['query_ids']+claim['query_ids']))
        count,estimated,reported=db.execute('SELECT COUNT(*),SUM(estimated),SUM(reported) FROM requests').fetchone();usage={'request_attempts':count,'estimated':estimated or 0,'reported':reported or 0};db.close()
    qmap={q['query_id']:q for q in queries};bycompany=collections.defaultdict(list)
    for q in queries:
        if q.get('company_id'):bycompany[q['company_id']].append(q['query_id'])
    statemap={s['query_id']:s for s in states};ansmap={s['query_id']:s for s in answers};evidence=[];summaries=[];profiles=[]
    lex=json.loads((ROOT/'data/tariffs/targeted_terms.json').read_text());terms=lex['tariff_terms']+['tariffs','duties','levy','levies','duty','AD/CVD']
    (out/'companies').mkdir(exist_ok=True)
    for company in companies:
        cid=company['company_id'];links=[]
        for claim in claims:
            scope=identity_scope(company,claim)
            if not scope:continue
            tariff=any(a.matches(term,claim['statement']) for term in terms) or bool(claim['fields'].get('tariff_program') or claim['fields'].get('duty_rate'))
            if scope=='potential_company_or_group_context' and not tariff:continue
            isquery=any(qid in bycompany[cid] for qid in claim['query_ids'])
            links.append((scope,tariff,isquery,claim))
        links.sort(key=lambda x:(x[0]!='company_name_matches_cached_evidence',not x[1],not x[2],x[3]['evidence_kind']!='full_document',x[3]['claim_id']))
        # Full relationship export is retained; pages show a bounded representative set.
        ce=[]
        for scope,tariff,isquery,claim in links:
            flags=quality.scan(claim);r={'company_id':cid,'company_name':company['company_name'],'claim_id':claim['claim_id'],'evidence_scope':scope,'tariff_related':tariff,'retrieved_by_company_query':isquery,'company_identity_verified':False,'facility_applicability':'not_established','current_legal_applicability':'not_established','statement':claim['statement'],'source_url':claim['source_url'],'document_id':claim['document_id'],'chunk_id':claim['chunk_id'],'evidence_kind':claim['evidence_kind'],'source_corpus':origin[claim['claim_id']],'source_text_path':str(Path(origin[claim['claim_id']])/claim['text_path']),'source_reported_fields':claim['fields'],'field_screening_flags':flags,'quality_metadata':claim.get('quality_audit',{}),'query_ids':claim['query_ids']}
            ce.append(r);evidence.append(r)
        qids=bycompany[cid];completed=sum(statemap.get(q,{}).get('status') in {'complete','insufficient_evidence'} for q in qids);failed=sum(statemap.get(q,{}).get('status')=='failed' for q in qids)
        direct=[e for e in ce if e['evidence_scope']=='company_name_matches_cached_evidence'];tariffdirect=[e for e in direct if e['tariff_related']]
        status='company_named_tariff_evidence_candidates' if tariffdirect else 'company_context_only' if direct else 'potential_group_context_only' if ce else 'no_matching_evidence_found'
        summary={'company_id':cid,'company_name':company['company_name'],'seed_row_ids':company['seed_row_ids'],'seed_locations':company['seed_locations'],'sector_hints':company['sector_hints'],'evidence_status':status,'direct_name_claims':len(direct),'direct_name_tariff_claims':len(tariffdirect),'potential_group_claims':len(ce)-len(direct),'full_text_direct_tariff_claims':sum(e['evidence_kind']=='full_document' for e in tariffdirect),'web_queries_planned':2,'web_queries_completed':completed,'web_queries_failed':failed,'web_research_status':'completed' if completed==2 else 'in_progress_or_pending','current_policy_verified':False,'facility_exposure_verified':False,'profile_path':'companies/'+cid+'.md'}
        summaries.append(summary);profile={**company,**summary,'query_ids':qids,'evidence':ce,'remaining_gaps':['Verify entity/parent/subsidiary identity and each facility against reliable sources.','Establish actual imported products/materials and origin; seed labels do not establish them.','Match HTS/product scope, entry date, rate components and exclusions to current authority.','Separate company-wide effects from any Georgia facility exposure.']};profiles.append(profile)
        text='# '+company['company_name']+' — tariff evidence\n\n'
        text+=f'Seed company ID: `{cid}`. Original rows: '+', '.join(company['seed_row_ids'])+'.\n\n'
        text+='Seed locations (unverified): '+('; '.join(company['seed_locations']) or 'Not supplied')+'.\n\n'
        text+=f'Web queries completed: {completed}/2. Evidence status: **{status}**. Direct-name tariff candidates: {len(tariffdirect)}; broader group leads: {len(ce)-len(direct)}. Name matching does not establish legal-entity identity or facility exposure.\n\n'
        for i,e in enumerate(ce[:25],1):
            text+=f'## Evidence {i}: {e["evidence_scope"]}\n\n> '+e['statement'].replace('\n','\n> ')+f'\n\n[Source]({e["source_url"]}); `{e["claim_id"]}`; `{e["chunk_id"]}`; {e["evidence_kind"]}. Current applicability: not established.\n\n'
            if e['field_screening_flags']:text+='Field review flags: '+', '.join(e['field_screening_flags'])+'.\n\n'
        if not ce:text+='No company-name-matching evidence was found in the processed sources. This is a research gap, not evidence of zero tariff exposure.\n\n'
        if len(ce)>25:text+=f'This page displays 25 of {len(ce)} evidence relationships. All are retained in company_evidence.jsonl.\n\n'
        text+='## Remaining verification\n\n'+'\n'.join('- '+gap for gap in profile['remaining_gaps'])+'\n'
        (out/summary['profile_path']).write_text(text)
    facilities=[]
    for e in evidence:
        fields=e['source_reported_fields']
        if e['evidence_scope']=='company_name_matches_cached_evidence' and any(fields.get(k) for k in ['facility','street_address','city','county']):
            facilities.append({'facility_evidence_id':t.sid('facility_evidence',e['company_id'],e['claim_id']),'company_id':e['company_id'],'claim_id':e['claim_id'],'source_url':e['source_url'],'chunk_id':e['chunk_id'],'source_reported_location':{k:fields.get(k) for k in ['company','facility','street_address','city','county','state','country']},'field_screening_flags':e['field_screening_flags'],'status':'source_reported_location_not_independently_verified','seed_location_assignment':'not_assigned'})
    a.write_jsonl(out/'company_facility_evidence.jsonl',facilities)
    a.write_jsonl(out/'company_evidence.jsonl',evidence);a.write_jsonl(out/'company_profiles.jsonl',profiles);a.write_csv(out/'company_summary.csv',summaries)
    result={'updated_at':t.now(),'companies':len(companies),'seed_rows':sum(len(c['seed_row_ids']) for c in companies),'companies_with_name_matched_tariff_candidates':sum(bool(r['direct_name_tariff_claims']) for r in summaries),'companies_with_only_context_or_no_evidence':sum(not r['direct_name_tariff_claims'] for r in summaries),'companies_with_both_web_queries_completed':sum(r['web_queries_completed']==2 for r in summaries),'evidence_relationships':len(evidence),'web_queries_processed':len(answers),'web_queries_failed':sum(s['status']=='failed' for s in states),'shared_policy_queries_processed':sum(qmap.get(a['query_id'],{}).get('query_purpose')=='shared_policy_verification' for a in answers),'usage':usage,'credit_cap':500,'all_current_legal_applicability_verified':False,'status':'collection_complete_with_evidence_gaps' if sum(r['web_queries_completed']==2 for r in summaries)==len(companies) and sum(qmap.get(a['query_id'],{}).get('query_purpose')=='shared_policy_verification' for a in answers)==20 else 'in_progress'}
    t.dump(out/'company_progress.json',result)
    (out/'index.md').write_text('# Company tariff evidence\n\n'+json.dumps(result,indent=2)+'\n\n[Research plan](research_plan.md) · [Company summary CSV](company_summary.csv) · [Full evidence JSONL](company_evidence.jsonl)\n\n'+ '\n'.join(f'- [{r["company_name"]}]({r["profile_path"]}) — {r["evidence_status"]}; {r["web_queries_completed"]}/2 web queries completed' for r in summaries)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=OUT);args=p.parse_args();print(json.dumps(collect(args.out),indent=2))
