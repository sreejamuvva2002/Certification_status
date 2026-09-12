"""Create a separate, provenance-checked quality revision. No network calls."""
from __future__ import annotations
import argparse, collections, copy, itertools, json, re, sqlite3
from pathlib import Path
import audit_tariff_quality as a
import research_tariffs as t

VERSION='quality-v1-2026-09-10'
NONCOMPANIES={x.casefold() for x in ['White House','The White House','USTR','U.S. Trade Representative','United States Trade Representative','CBP','USITC','U.S. Customs and Border Protection','Department of Commerce','United States','U.S.','China','South Korea','Japan','European Union','President Trump','President Donald Trump','we']}

def apply_patch(claim,patch,chunk):
    result=copy.deepcopy(claim)
    for field in patch['clear_fields']:
        if field not in result['fields']:raise ValueError('Unknown field '+field)
        result['fields'][field]=None;result['field_support'].pop(field,None)
    for field,item in patch['set_fields'].items():
        if field not in result['fields']:raise ValueError('Unknown field '+field)
        if not t.norm(item['value']) or t.norm(item['value']) not in t.norm(item['excerpt']) or t.norm(item['excerpt']) not in t.norm(chunk['text']):raise ValueError('Unsupported correction '+field)
        result['fields'][field]=item['value'];result['field_support'][field]=item['excerpt']
    result['quality_audit']={'record_version':VERSION,'review_status':'manually_reviewed_cached_context','flags':patch['audit_flags'],'verdict':patch['audit_verdict'],'reason':patch['reason'],'current_applicability_verified':False}
    return result

def scan(claim):
    f=claim['fields'];flags=[]
    if (f.get('company') or '').casefold() in NONCOMPANIES:flags.append('company_field_non_company_candidate')
    if f.get('effective_date') and re.search(r'\b(updated|posted|published|last reviewed)\b',claim['field_support'].get('effective_date',''),re.I):flags.append('effective_date_may_be_publication_update')
    if re.fullmatch(r'(now|today|this year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',f.get('effective_date') or '',re.I):flags.append('effective_date_relative_without_anchor')
    if re.fullmatch(r'[A-Za-z .-]+ County',f.get('city') or ''):flags.append('county_in_city_field')
    if f.get('hts_code') and 'zauba.com' in claim['source_url']:flags.append('hts_jurisdiction_unverified')
    return flags

def draft_queries(queries,lex,year='2026'):
    """One focused sector/policy draft per original topic; named entities only from query text."""
    result=[];seen=set()
    for q in queries:
        sector=q['sectors'][0];terms=lex['sectors'][sector]
        product=next((x for x in terms if a.matches(x,q['original_query'])),terms[0])
        tariff={'automotive_and_trade':'Section 232 auto parts tariff HTS effective date','metals':'Section 232 metal content tariff exclusions','batteries_and_minerals':'Section 301 battery critical minerals tariff origin','pcbs_and_electronics':'printed circuit board HTS Section 301 exclusion','displays':'LCD OLED display module HTS customs ruling'}[sector]
        names=[name for name,aliases in lex['company_aliases'].items() if any(a.matches(x,q['original_query']) for x in aliases)]
        region='Southeast Georgia' if q['geography']=='southeast_georgia' else 'Georgia' if q['geography']=='statewide_georgia' else ''
        # Keep the full original scope (product, origin, facility and requested effect).
        # Topic-only regeneration would collapse distinct equipment/material questions.
        query=' '.join([q['original_query'].strip(),tariff,'effective date'])
        if not a.matches(year,query):query+=' '+year
        if region and not any(a.matches(x,query) for x in lex['geography_terms']):query+=' '+region
        key=t.norm(query).casefold()
        if key in seen:
            next(r for r in result if t.norm(r['query']).casefold()==key)['parent_query_ids'].append(q['query_id']);continue
        seen.add(key)
        result.append({'id':'targeted_'+str(len(result)+1),'query':query,'parent_query_ids':[q['query_id']],'sector':sector,'geography':q['geography'],'query_type':'company_context' if names else 'sector_policy','company_names':names,'company_exposure_established':False,'reason':'Insufficient original evidence; add explicit product/policy terminology.','execution_status':'not_executed'})
    return result

def table(rows,columns):
    return '\n'.join(['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']+['| '+' | '.join(str(r.get(k,'')) for k in columns)+' |' for r in rows])

def finalize(base,out,terms,allow_incomplete=False):
    base=base.resolve();out=out.resolve()
    if base==out or base in out.parents:raise ValueError('Revision must be outside original corpus')
    original=json.loads((out/'base_manifest.json').read_text());current=a.manifest(base)
    if original['file_sha256']!=current:raise ValueError('Original corpus changed; stop before revision')
    db=sqlite3.connect((base/'corpus.sqlite').as_uri()+'?mode=ro',uri=True)
    data={k:a.read_rows(db,k) for k in ['claims','answers','queries','chunks','documents']}
    ledger=list(db.execute('SELECT COUNT(*),SUM(estimated),SUM(reported) FROM requests').fetchone());db.close()
    if ledger!=original['request_ledger']:raise ValueError('Request ledger changed')
    recovery={r['query_id']:r for f in (out/'recovery').glob('*.json') for r in [json.loads(f.read_text())]}
    for review in json.loads((out/'manual_cause_review.json').read_text())['reviews']:
        row=recovery[review['query_id']]
        row['original_model_primary_cause']=row.get('primary_cause')
        row.update(review['updates'])
        row['manual_cause_review']=review['action']
    batchrows=[json.loads(f.read_text()) for f in sorted((out/'conflicts').glob('*.json'))]
    expected_queries={r['query_id'] for r in data['answers'] if r['status']=='insufficient_evidence'}
    expected_pairs={t.sid('conflict',tuple(sorted(pair))) for ans in data['answers'] for group in ans['conflicts'] for pair in itertools.combinations(group,2)}
    actual_pairs=[p['pair_id'] for batch in batchrows for p in batch['pairs']]
    failed=sum(r['status']!='reviewed' for r in recovery.values())+sum(r['status']!='reviewed' for r in batchrows)
    missing_queries=expected_queries-set(recovery);missing_pairs=expected_pairs-set(actual_pairs)
    if (failed or set(recovery)!=expected_queries or set(actual_pairs)!=expected_pairs or len(actual_pairs)!=len(expected_pairs)) and not allow_incomplete:raise ValueError(f'Local reviews incomplete: {failed} failed records/batches, {len(missing_queries)} missing queries, {len(missing_pairs)} missing pairs')
    claims={c['claim_id']:c for c in data['claims']};chunks={c['chunk_id']:c for c in data['chunks']};docs={d['document_id']:d for d in data['documents']}
    patches=json.loads((out/'manual_corrections.json').read_text())+json.loads((out/'additional_claim_corrections.json').read_text())
    changes=[]
    for patch in patches:
        old=claims[patch['claim_id']];new=apply_patch(old,patch,chunks[old['chunk_id']]);claims[old['claim_id']]=new
        changes.append({**patch,'record_version':VERSION,'old_fields':{k:old['fields'][k] for k in patch['clear_fields']+list(patch['set_fields'])},'new_fields':{k:new['fields'][k] for k in patch['clear_fields']+list(patch['set_fields'])},'source_url':old['source_url'],'chunk_id':old['chunk_id']})
    flags=[]
    for c in claims.values():
        c.setdefault('quality_audit',{'record_version':VERSION,'review_status':'not_manually_reviewed','current_applicability_verified':False})
        hits=scan(c)
        if hits:flags.append({'claim_id':c['claim_id'],'query_ids':c['query_ids'],'source_url':c['source_url'],'flags':hits,'status':'screening_flag_not_confirmed_error'})
        c['quality_audit']['screening_flags']=hits
        c['quality_audit']['source_base_directory']=str(base)
        c['quality_audit']['resolved_text_path']=str(base/c['text_path'])
    for c in claims.values():
        source_text=chunks[c['chunk_id']]['text']
        if t.norm(c['statement']) not in t.norm(source_text):raise ValueError('Claim quotation provenance mismatch')
        if not Path(c['quality_audit']['resolved_text_path']).is_file():raise ValueError('Missing original source text')
        for field,value in c['fields'].items():
            if value is None:continue
            excerpt=c['field_support'].get(field,'')
            if not excerpt or t.norm(value).casefold() not in t.norm(excerpt).casefold() or t.norm(excerpt) not in t.norm(source_text):raise ValueError('Revised field provenance mismatch '+c['claim_id']+' '+field)
    recovered=[]
    for r in recovery.values():
        for e in r.get('validated_recovery_evidence',[]):
            if t.norm(e['supporting_excerpt']) not in t.norm(chunks[e['chunk_id']]['text']):raise ValueError('Recovery quote mismatch')
            if e['document_id'] not in {s['document_id'] for s in chunks[e['chunk_id']]['sources']}:raise ValueError('Recovery document mismatch')
            if e['query_id']=='q_105':
                e={**e,'manual_relevance_review':'Context only: aluminum extrusion AD investigation scope does not establish Section 232 battery-tray coverage.','supports_requested_tariff_program':False}
            e={**e,'source_base_directory':str(base),'resolved_source_text_path':str(base/e['source_text_path'])}
            recovered.append(e)
    byq=collections.defaultdict(list)
    for e in recovered:byq[e['query_id']].append(e['recovery_claim_id'])
    patched={p['claim_id'] for p in patches};revised_answers=[]
    for original_answer in data['answers']:
        ans=copy.deepcopy(original_answer);qid=ans['query_id']
        ans['quality_audit']={'record_version':VERSION,'original_status_preserved':True,'current_legal_applicability_verified':False,'manually_reviewed_selected_claim_ids':sorted(set(ans['selected_claim_ids'])&patched),'recovery_claim_ids':byq[qid],'recovery_review_status':recovery.get(qid,{}).get('status','not_targeted'),'primary_insufficiency_cause':recovery.get(qid,{}).get('primary_cause'),'recovery_resolves_insufficiency':False,'note':'Statements remain source quotations; read corrected claim fields and audit flags before reuse.'}
        revised_answers.append(ans)
    conflicts=[p for batch in batchrows for p in batch['pairs']]
    manual_pairs={r['pair_id']:r for r in json.loads((out/'manual_conflict_review.json').read_text())['reviews']}
    for p in conflicts:
        p['source_urls']=[claims[cid]['source_url'] for cid in p['claim_ids']]
        p['original_model_classification']=p.get('classification')
        p['latest_local_model_classification']=p.get('classification')
        p['review_status']='model_review_provisional'
        if p['pair_id'] in manual_pairs:
            p.update(manual_pairs[p['pair_id']]);p['review_status']='manual_cached_context_review'
            p['assessment_method']='assistant_direct_source_context_review'
            for cid in p['claim_ids']:
                qa=claims[cid]['quality_audit']
                qa.setdefault('manual_conflict_review_ids',[]).append(p['review_id'])
                if qa['review_status']=='not_manually_reviewed':qa['review_status']='manually_reviewed_conflict_context'
        elif t.norm(claims[p['claim_ids'][0]]['statement'])==t.norm(claims[p['claim_ids'][1]]['statement']):
            p.update(classification='complementary_or_no_conflict',reason='Deterministic exact normalized quotation identity; current applicability remains unverified.',review_status='exact_quote_identity_check')
        p['resolved']=False
        p['model_label_reason_check_required']=bool(p.get('review_status')=='model_review_provisional' and (p.get('reason','').strip().lower() in {'true','false','yes','no'} or p.get('classification')=='apparent_same_scope_conflict' and re.search(r'not contradict|not contradictory|identical claims|not a conflict',p.get('reason',''),re.I)))
    lex=json.loads(terms.read_text());qmap={q['query_id']:q for q in data['queries']};amap={r['query_id']:r for r in data['answers']}
    coverage=[]
    for dimension,groups in [('sector',list(lex['sectors'])),('geography',sorted({q['geography'] for q in qmap.values()}))]:
        for group in groups:
            qs=[q for q in qmap.values() if group in q['sectors']] if dimension=='sector' else [q for q in qmap.values() if q['geography']==group]
            row={'dimension':dimension,'group':group,'queries':len(qs),'with_selected_evidence':0,'with_full_text_citation':0,'with_trade_authority_citation':0,'with_topic_location_term':0,'with_named_company_field':0,'insufficient':0,'with_recovery_quotes':0}
            for q in qs:
                cid=amap[q['query_id']]['selected_claim_ids'];cs=[claims[x] for x in cid]
                row['with_selected_evidence']+=bool(cs);row['with_full_text_citation']+=any(c['evidence_kind']=='full_document' for c in cs)
                row['with_trade_authority_citation']+=any(docs[c['document_id']]['publisher_type']=='official_trade_authority' for c in cs)
                terms_for_group=lex['sectors'][group] if dimension=='sector' else [x for x in lex['geography_terms'] if x!='Georgia'] if group=='southeast_georgia' else ['Georgia'] if group=='statewide_georgia' else []
                row['with_topic_location_term']+=any(a.matches(term,c['statement']) for c in cs for term in terms_for_group)
                row['with_named_company_field']+=any(c['fields'].get('company') and c['fields']['company'].casefold() not in NONCOMPANIES for c in cs)
                row['insufficient']+=amap[q['query_id']]['status']=='insufficient_evidence';row['with_recovery_quotes']+=bool(byq[q['query_id']])
            if dimension=='geography' and group=='national_international_context':row['with_topic_location_term']='not_applicable'
            coverage.append(row)
    drafts=draft_queries([qmap[qid] for qid in sorted(recovery,key=lambda x:int(x.split('_')[1]))],lex)
    a.write_csv(out/'targeted_query_drafts.csv',drafts)
    for name,rows in [('claims.v1',list(claims.values())),('answers.v1',revised_answers),('claim_corrections',changes),('recovery_claims',recovered),('insufficiency_classification',list(recovery.values())),('conflict_review',conflicts),('screening_flags',flags)]:
        a.write_jsonl(out/(name+'.jsonl'),rows)
        if name not in ['claims.v1','answers.v1']:a.write_csv(out/(name+'.csv'),rows)
    unsupported=[{**row,'finding_status':'manually_identified_unsupported_or_misclassified_fields'} for row in changes if row['clear_fields']]
    a.write_csv(out/'unsupported_assertions.csv',unsupported)
    a.write_csv(out/'claims.v1.csv',[{'claim_id':c['claim_id'],'query_ids':c['query_ids'],'document_id':c['document_id'],'chunk_id':c['chunk_id'],'statement':c['statement'],'source_url':c['source_url'],**c['fields'],'review_status':c['quality_audit']['review_status'],'audit_flags':c['quality_audit'].get('flags',[]),'screening_flags':c['quality_audit']['screening_flags'],'current_applicability_verified':False,'source_text_path':c['quality_audit']['resolved_text_path']} for c in claims.values()])
    a.write_csv(out/'evidence_coverage.csv',coverage)
    reasons=collections.Counter(r.get('primary_cause','review_failed') for r in recovery.values());contributors=collections.Counter(c for r in recovery.values() for c in [r.get('primary_cause','review_failed')]+r.get('contributing_causes',[]))
    summary={'version':VERSION,'base_queries':len(qmap),'base_claims':len(claims),'insufficient_queries':len(recovery),'primary_causes':dict(reasons),'primary_or_contributing_causes':dict(contributors),'local_review_failures':failed,'missing_query_reviews':len(missing_queries),'missing_conflict_pairs':len(missing_pairs),'recovery_quotes':len(recovered),'queries_with_recovery_quotes':len(byq),'recovery_quotes_already_extracted':sum(e['already_extracted_for_query'] for e in recovered),'rejected_recovery_quotes':sum(len(r.get('rejected_recovery_evidence',[])) for r in recovery.values()),'insufficiencies_fully_resolved':0,'manual_claim_sample':30,'manual_conflict_pairs':len(manual_pairs),'claims_with_manual_field_corrections':sum(bool(p['clear_fields'] or p['set_fields']) for p in patches),'claims_with_manual_review':sum(c['quality_audit']['review_status'].startswith('manually_reviewed') for c in claims.values()),'manual_patch_records':len(patches),'claims_with_cleared_unsupported_fields':len(unsupported),'conflict_pairs':len(conflicts),'conflict_classifications':dict(collections.Counter(p.get('classification','review_failed') for p in conflicts)),'model_label_reason_flags':sum(p['model_label_reason_check_required'] for p in conflicts),'screening_flagged_claims':len(flags),'screening_flag_counts':dict(collections.Counter(x for f in flags for x in f['flags'])),'targeted_drafts_not_executed':len(drafts),'tavily_calls':0,'coverage':coverage}
    # byq is a defaultdict read for every answer above: count nonempty entries, not keys.
    summary['queries_with_recovery_quotes']=sum(bool(v) for v in byq.values())
    t.dump(out/'revision_validation.json',{'checked_at':t.now(),'claims_checked':len(claims),'claim_quote_and_field_provenance_passed':True,'original_source_paths_resolve':True,'answers_checked':len(revised_answers),'answer_statuses_and_selected_ids_preserved':True,'recovery_quotes_checked':len(recovered),'recovery_quote_and_document_provenance_passed':True,'missing_query_reviews':len(missing_queries),'missing_conflict_pairs':len(missing_pairs),'local_review_failures':failed})
    t.dump(out/'quality_summary.json',summary)
    t.dump(out/'preservation_check.json',{'checked_at':t.now(),'all_original_hashes_match':True,'original_files_checked':len(current),'request_ledger_unchanged':True,'request_ledger':ledger,'external_requests_added':0,'original_queries_unchanged':True})
    return summary


def write_report(out,summary):
    causes=[{'cause':c,'primary':summary['primary_causes'].get(c,0),'primary_or_contributing':summary['primary_or_contributing_causes'].get(c,0)} for c in a.CAUSES]
    def coverage_table(rows):
        names={'group':'Group','queries':'Queries','with_selected_evidence':'Any evidence','with_full_text_citation':'Full text','with_trade_authority_citation':'Authority','with_topic_location_term':'Topic/place term','insufficient':'Insufficient','with_recovery_quotes':'Recovery'}
        return table([{label:r[key] for key,label in names.items()} for r in rows],list(names.values()))
    sector=[r for r in summary['coverage'] if r['dimension']=='sector'];geo=[r for r in summary['coverage'] if r['dimension']=='geography']
    conflicts=[{'classification':k,'pairs':v} for k,v in summary['conflict_classifications'].items()]
    text=f'''# Georgia EV tariff corpus: quality audit v1

Audit date: September 10, 2026. Original research date: September 9, 2026; original run completed September 10. Branch: `Tariffs-data`.

The 510-query run is complete as a collection run. It is a sector/regional research baseline, not a verified tariff-exposure register for every company. This audit preserves all original files and creates a separate revision. It made **zero additional Tavily calls and zero external document downloads**. Local Qwen and cached source text were used; current law was not independently rechecked.

## What was reviewed

The original corpus contains 10,217 extracted claims, 2,171 chunks, 910 source URL records, and 748 downloaded files. There are 664 full-document evidence records and 246 snippet fallbacks. Of 510 answers, 481 select evidence; 125 are marked insufficient (96 contain partial evidence and 29 select none). Completion therefore does not establish research sufficiency.

All 125 insufficient answers received local classification/recovery attempts. A seeded purposive sample of 30 claims (six per sector) was read directly against cached quotations and surrounding context, covering company/facility claims, authority documents, snippets, historical/proposed measures, and random selections. An additional eight conflict pairs spanning all sectors and fifteen insufficiency classifications were checked directly. This is an assistant review, not an independent human or legal review. The purposive sample does not support a corpus-wide error-rate estimate.

## Causes of insufficient evidence

{table(causes,['cause','primary','primary_or_contributing'])}

Primary causes sum to 125; the final column overlaps. Classification is local-model triage constrained by observed retrieval metrics, with the fifteen documented manual checks/overrides in [manual_cause_review.json](manual_cause_review.json). The requested weak relevance category also includes product/sector mismatch. “Conflicting or outdated” includes inability to establish current applicability; it does not mean a source was proven false. “Extraction problems” includes omitted synthesis evidence; zero selected claims alone is not proof of extraction failure.

The complete per-query explanations, original metrics, contributing causes, and remaining gaps are in [insufficiency_classification.csv](insufficiency_classification.csv). Four original searches returned no candidates. Other gaps involve broad national rules being offered for local company questions, inaccessible full text, dated/proposed measures, and missing product/origin specificity. No new search has been used to fill those gaps.

No case retains extraction problems as its primary cause after direct review of the two model assignments (q_105 and q_151): their available claims did not answer the requested product/program scope, so omitting them was not evidence of extraction failure. Four cases retain extraction/synthesis problems as a contributing signal. Separately, the field corrections below address confirmed extraction/interpretation problems across the sampled corpus.

## Cached recovery

The local FTS index contains 11,235 passages from previously downloaded full documents. For each insufficient answer, it retrieved up to eight passages with topic, geography, and named-company boosts, then asked local Qwen for up to four exact quotes. Every accepted quote was checked against its supplied passage, original chunk, and document relationship.

There are **{summary['recovery_quotes']} accepted quoted passages across {summary['queries_with_recovery_quotes']} queries**; {summary['recovery_quotes_already_extracted']} quotes exactly duplicate an already extracted quote for that query. These are additional evidence candidates, not necessarily new facts or adequate answers. The validator rejected {summary['rejected_recovery_quotes']} proposed quotations. Local review failures remaining: {summary['local_review_failures']}.

**All 125 insufficient flags remain in the revision.** Additional quotations alone do not verify current policy or company-specific applicability. Recovery claims remain explicitly marked as locally extracted, quote-validated, and not manually verified. The bounded retrieval did not exhaust every possible passage combination; no useful recovery means none was accepted under these settings.

## Coverage by sector

{coverage_table(sector)}

Counts are queries, not documents. Sector assignments overlap, so sector totals exceed 510. `with_selected_evidence` means any original citation; `with_full_text_citation` means at least one selected full-document claim; `with_trade_authority_citation` means a selected claim from a publisher tagged as an official trade authority. These columns are separate tests: an official citation may still be a snippet or off topic. `with_topic_location_term` is an exact term/word-boundary proxy in selected quotations, not a semantic relevance determination. The displayed recovery counts are additional candidates and do not replace insufficiency flags.

The sample revealed off-topic evidence even in authority documents: a hypothetical pasta entry appeared in automotive evidence, face-mask directives and aircraft products appeared in PCB evidence, and general automobile tariff statements appeared in display evidence. Display-specific classification must distinguish monitors, signaling displays, and automotive modules by function and product details. Authority provenance alone is insufficient.

## Coverage by geography

{coverage_table(geo)}

Geography groups are mutually exclusive query labels. Southeast Georgia term matches use named local places/region terms, excluding a bare “Georgia”; statewide matches require “Georgia.” These are location mentions, not proof of a facility’s tariff liability. National/international questions have no geographic-match test. Named-company fields are also only context indicators and may contain unreviewed extraction errors; their counts are available in [evidence_coverage.csv](evidence_coverage.csv).

A national tariff plus a Georgia factory address does not establish that factory’s imports, origin, HTS classification, entry date, content value, exemptions, or actual cost. For instance, the Covington recycling evidence describes operations in Georgia but does not establish Southeast Georgia exposure or tariff causation.

## Citation support and corrections

All 30 sampled quotations were found in their cached chunks after whitespace normalization. Nevertheless, 20 of those records needed field corrections. Additional conflict-context review produced six more corrected claim records: **{summary['claims_with_manual_field_corrections']} total records with manual field corrections**. Supporting quotations remain unchanged. New field values require exact support in the original chunk; removals and before/after values are recorded in [claim_corrections.csv](claim_corrections.csv).

Examples, indexed in [manual_review.json](manual_review.json) and [manual_conflict_review.json](manual_conflict_review.json):

- S04: automobile and auto-part effective dates were collapsed into one date; the correction preserves the separately quoted conditions.
- S07: the country of one factory was attached to another factory’s city/state; the unsupported country assignment was removed.
- S10/S11/S28: a page-update date, capacity-forecast year, or unanchored “now” was treated as an effective date; these fields were cleared.
- S18: a flattened tariff-table row mixed the general rate with preferential treatment; the rate was cleared while the supported HTS code was retained.
- S19: national Hyundai investment/output/job figures were mixed with a single plant and tariff causation. The unsupported investment-effect field was cleared. Cached 500,000-unit Georgia plant reports and the broader 1.2-million-unit statement require dated scope reconciliation; neither figure is adopted as current verified capacity.
- S01/S05/S15/S30: manufacturing locations, export controls, marking law, or policy rationale were mislabeled as origin rules, import tariff programs, or measured production effects.
- MC01/MC07: Schedule B export codes were treated as import HTS codes, and a ruling signatory/CBP was treated as a company. A comparator product also inherited the subject ruling’s duty rate.

[unsupported_assertions.csv](unsupported_assertions.csv) lists {summary['claims_with_cleared_unsupported_fields']} records with manually cleared unsupported or misclassified fields, including their old values and source links. Lexical quotation support and the applicability of a structured field are separate checks.

The broader deterministic screen flags **{summary['screening_flagged_claims']} claim records after manual corrections** for review. Flags include non-company names in company fields, update/relative dates used as effective dates, counties in city fields, and unverified HTS jurisdiction. [screening_flags.csv](screening_flags.csv) contains candidates, not confirmed errors; these uncertain fields were not silently rewritten.

## Conflicts and unresolved questions

The original model supplied 753 unique claim pairs in conflict groups. Their revised triage is:

{table(conflicts,['classification','pairs'])}

These are provisional cached-evidence classifications. Eight pairs were directly reviewed; identical normalized quotes can also be cleared as textual contradictions mechanically. No pair is labeled as a verified resolution of current law. {summary['model_label_reason_flags']} remaining model label/reason inconsistencies require review. Raw prior model outputs are retained alongside the revised results.

The direct review found that duplicate CBP statements, an investigation date versus an imposition date, expiry “unless renewed” versus a later extension, and different graphite forms or LCD functions had been treated as conflicts. Those distinctions explain the text but still do not establish current legal applicability.

Unresolved high-risk issues include battery vendors reporting 57.4% and roughly 70–170% without aligned dates/HTS components, graphite AD and other tariff components being mistaken for a total duty, steel/aluminum content valuation and stacking rules, and current PCB exclusion eligibility/expiry. The apparent-same-scope and insufficient-scope rows in [conflict_review.csv](conflict_review.csv) form the verification queue. Preserve their product, origin, program, rate basis, date, and source links; do not average conflicting rates or select the newest-looking snippet.

## Sector terms and company research

Targeted terminology is maintained in [targeted_terms.json](../../../data/tariffs/targeted_terms.json) for automotive, metals, batteries/minerals, PCBs/electronics, and displays, plus tariff programs, origin rules, exclusions, HTS, and Georgia locations. The audit applies these terms to cached retrieval. It also prepares **{summary['targeted_drafts_not_executed']} deduplicated follow-up drafts** in [targeted_query_drafts.csv](targeted_query_drafts.csv), linked to the 125 original gaps. All are marked `not_executed`; original query text is unchanged.

Use both levels: retain the 510-query baseline for policy and sector context, then investigate individual companies only where a company-specific conclusion is needed. A company dossier needs named company/facility evidence, the actual product/material and origin, and a dated applicable policy. Drafts naming a company inherit that name from the original query; they do not assert a supply relationship or proven exposure. Subsequent searches should prioritize the unresolved primary-authority and product/origin gaps instead of repeating all 510 queries for every company.

## Versioned outputs and preservation

- [claims.v1.jsonl](claims.v1.jsonl) and [claims.v1.csv](claims.v1.csv): all 10,217 original claim IDs with supported field corrections, review metadata, and explicit paths back to original source text.
- [answers.v1.jsonl](answers.v1.jsonl): all 510 original source-quote answers, their statuses preserved, linked to corrections and recovery evidence.
- [recovery_claims.jsonl](recovery_claims.jsonl): separately identified cached recovery quotes with original document/chunk provenance.
- Classification, coverage, screening, conflict, and manual-review files linked above explain the limitations and every intervention.
- [preservation_check.json](preservation_check.json) verifies all original file hashes and the unchanged request ledger. [quality_summary.json](quality_summary.json) contains machine-readable counts.

The original output directory was not overwritten. The revised data is suitable for evidence navigation and prioritizing verification, with the recorded qualifications; it does not certify every extracted field or supply a current company-level duty calculation.
'''
    if summary['local_review_failures'] or summary['missing_query_reviews'] or summary['missing_conflict_pairs']:
        text='**DRAFT — local review incomplete; do not treat these counts as final.**\n\n'+text
    (out/'quality_report.md').write_text(text,encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=Path('outputs/tariffs/pilot-2026-09-09'));p.add_argument('--out',type=Path,default=Path('outputs/tariffs/quality-audit-v1-2026-09-10'));p.add_argument('--terms',type=Path,default=Path('data/tariffs/targeted_terms.json'));p.add_argument('--allow-incomplete',action='store_true');args=p.parse_args();summary=finalize(args.base,args.out,args.terms,args.allow_incomplete);write_report(args.out,summary);print(json.dumps(summary,indent=2))
