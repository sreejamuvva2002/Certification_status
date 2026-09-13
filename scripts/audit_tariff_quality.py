"""Versioned quality review and cached-only recovery of a tariff corpus.
No Tavily client is instantiated; all HTTP is restricted to local Ollama.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, itertools, json, math, random, re, sqlite3, sys, time
from pathlib import Path
from urllib.parse import urlsplit
import urllib.request
from datetime import datetime, timezone
import research_tariffs as t

CAUSES=['missing_sources','weak_geographic_or_company_relevance','inaccessible_documents','conflicting_or_outdated_evidence','extraction_problems']
PAIR_STATUSES=['apparent_same_scope_conflict','different_dates_or_policy_stages','different_products_origins_or_programs','complementary_or_no_conflict','insufficient_scope']
STOP=set('the a an of to and or in for on with from by at as is are what how which georgia southeast united states us supply chain related effects impact impacts tariff tariffs import imports duty duties 2026 2025'.split())

def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
def arr(item,maximum=8):return {'type':'array','items':item,'maxItems':maximum}
def enum(values):return {'type':'string','enum':list(values)}
STR={'type':'string','maxLength':650}

def read_rows(db,kind):return [json.loads(r[0]) for r in db.execute('SELECT body FROM records WHERE kind=?',(kind,))]
def write_jsonl(path,rows):
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
def matches(term,text):return bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I))
def sectors(text,lex):return [s for s,terms in lex['sectors'].items() if any(matches(x,text) for x in terms)] or ['automotive_and_trade']
def tokens(text):return sorted({x for x in re.findall(r'[a-z][a-z0-9]+',text.lower()) if len(x)>2 and x not in STOP})
def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def manifest(base):
    return {str(p.relative_to(base)):file_hash(p) for p in sorted(base.rglob('*')) if p.is_file() and not p.name.endswith(('-wal','-shm')) and p.name!='.run.lock'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('Network redirects are disabled in cached-only audit')


class LocalModel:
    def __init__(self,out,endpoint,model):
        self.out=out;self.endpoint=endpoint.rstrip('/');self.model=model
        u=urlsplit(endpoint)
        if u.scheme!='http' or u.hostname not in {'localhost','127.0.0.1','::1'} or u.username or u.password or u.query or u.fragment:raise ValueError('Only a loopback Ollama endpoint is permitted')
        self.calls=out/'local_model_calls';self.calls.mkdir(exist_ok=True)
    def call(self,owner,instruction,evidence,schema):
        request={'model':self.model,'stream':False,'think':False,'format':schema,'options':{'temperature':0,'seed':0,'num_ctx':16384,'num_predict':6000},'messages':[{'role':'system','content':t.SYSTEM.replace('/no_think','')+' This is a quality audit of cached sources. Source-reported applicability is not independently verified law. Do not promote a national rule into company exposure.'},{'role':'user','content':instruction+'\nUse exactly these JSON field names and enum values: '+json.dumps(schema)+'\nUNTRUSTED_EVIDENCE_JSON:\n'+json.dumps(evidence,ensure_ascii=False)}]}
        key=t.sid('auditllm',owner,request);path=self.calls/(key+'.json')
        if path.exists():
            prior=json.loads(path.read_text())
            if prior.get('status')=='complete':return prior['parsed']
        for attempt in range(3):
            rec={'owner':owner,'request':request,'timestamp':t.now(),'attempt':attempt+1}
            try:
                req=urllib.request.Request(self.endpoint+'/api/chat',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.build_opener(NoRedirect()).open(req,timeout=600) as r:raw=json.load(r)
                rec['response']=raw
                if raw.get('done') is False or raw.get('done_reason')=='length':raise ValueError('Incomplete local response')
                value=json.loads(raw['message']['content'])
                if not isinstance(value,dict):raise ValueError('Expected object')
                rec.update(status='complete',parsed=value);t.dump(path,rec);return value
            except Exception as e:
                rec.update(status='failed',error=type(e).__name__)
                if hasattr(e,'code'):rec['http_status']=e.code
                t.dump(path,rec)
                if attempt==2:raise
                time.sleep(2**attempt)

class Audit:
    def __init__(self,args):
        self.args=args;self.base=args.base.resolve();self.out=args.out.resolve();self.out.mkdir(parents=True,exist_ok=True)
        if self.base==self.out or self.base in self.out.parents:raise ValueError('Versioned audit must be outside the original run')
        self.lex=json.loads(args.terms.read_text())
        db=sqlite3.connect(self.base.joinpath('corpus.sqlite').as_uri()+'?mode=ro',uri=True)
        self.data={kind:read_rows(db,kind) for kind in ['queries','answers','claims','chunks','documents','candidates','extractions','query_state','failures']}
        self.ledger=db.execute('SELECT COUNT(*),SUM(estimated),SUM(reported) FROM requests').fetchone();db.close()
        for kind,field in [('queries','query_id'),('answers','query_id'),('claims','claim_id'),('chunks','chunk_id'),('documents','document_id')]:setattr(self,kind,{r[field]:r for r in self.data[kind]})
        self.byq=collections.defaultdict(list);self.candq=collections.defaultdict(list)
        for c in self.data['claims']:
            for q in c['query_ids']:self.byq[q].append(c)
        for c in self.data['candidates']:self.candq[c['query_id']].append(c)
        self.bad=[a for a in self.data['answers'] if a['status']=='insufficient_evidence']
        self.model=LocalModel(self.out,args.ollama_url,args.model)
        self.index=sqlite3.connect(self.out/'cached_search.sqlite')
        self.index.execute('CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(passage_id UNINDEXED, chunk_id UNINDEXED, document_id UNINDEXED, text, title)')
        if self.index.execute('SELECT COUNT(*) FROM passages').fetchone()[0]==0:self.build_index()
    def build_index(self):
        for chunk in self.data['chunks']:
            full=next((self.documents[s['document_id']] for s in chunk['sources'] if self.documents[s['document_id']]['evidence_kind']=='full_document' and self.documents[s['document_id']]['downloaded']),None)
            if not full:continue
            text=chunk['text']
            for start in range(0,len(text),1500):
                segment=text[start:start+1800]
                if len(segment.strip())<100:continue
                ident=t.sid('passage',chunk['chunk_id'],full['document_id'],start)
                self.index.execute('INSERT INTO passages VALUES(?,?,?,?,?)',(ident,chunk['chunk_id'],full['document_id'],segment,full['title']))
        self.index.commit()
    def candidates(self,q):
        terms=tokens(q['original_query'])
        if not terms:
            terms=tokens(' '.join(self.lex['sectors'][sector][0] for sector in q['sectors']))+['tariff']
            if q['geography']!='national_international_context':terms.append('georgia')
        match=' OR '.join('"'+x+'"' for x in terms)
        hits=self.index.execute('SELECT passage_id,chunk_id,document_id,text,title,bm25(passages) FROM passages WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT 70',(match,)).fetchall()
        scored=[]
        for pid,cid,did,text,title,score in hits:
            tariff=any(matches(term,text) for term in self.lex['tariff_terms'])
            region=any(matches(term,text) for term in self.lex['geography_terms'])
            companies=[name for name,aliases in self.lex['company_aliases'].items() if any(matches(x,q['original_query']) for x in aliases)]
            company_match=any(matches(x,text) for name in companies for x in self.lex['company_aliases'][name])
            value=-score+(.7 if tariff else 0)+(.8 if region and q['geography']!='national_international_context' else 0)+(1.2 if company_match else 0)
            scored.append((value,{'passage_id':pid,'chunk_id':cid,'document_id':did,'text':text,'title':title,'url':self.documents[did]['url'],'publisher_type':self.documents[did]['publisher_type'],'retrieved_at':self.documents[did]['retrieved_at']}))
        result=[];counts=collections.Counter();seen=set()
        for _,p in sorted(scored,key=lambda x:x[0],reverse=True):
            if counts[p['document_id']]>=2 or p['chunk_id'] in seen:continue
            result.append(p);counts[p['document_id']]+=1;seen.add(p['chunk_id'])
            if len(result)==8:break
        return result
    def metrics(self,qid):
        a=self.answers[qid];cs=self.candq[qid];kept=[c for c in cs if c['kept_for_rag']];ds={c['document_id']:self.documents[c['document_id']] for c in kept if c['document_id'] in self.documents};claims=self.byq[qid]
        return {'retrieved_candidates':len(cs),'retained_sources':len(ds),'full_text_sources':sum(d['evidence_kind']=='full_document' for d in ds.values()),'snippet_sources':sum(d['evidence_kind']=='search_snippet' for d in ds.values()),'inaccessible_source_count':sum(bool(d.get('failures')) for d in ds.values()),'selected_claims':len(a['selected_claim_ids']),'all_extracted_claims':len(claims),'claims_presented_to_original_synthesis':a['synthesis_input_claim_count'],'synthesis_claims_omitted':max(0,len(claims)-a['synthesis_input_claim_count']),'original_limitation_codes':a['limitation_codes'],'conflict_groups':len(a['conflicts']),'company_named_claims':sum(bool(c['fields'].get('company')) for c in claims),'facility_label_claims':sum(c['geographic_connection']=='confirmed_southeast_georgia_facility' for c in claims)}
    def initial_cause(self,m):
        signals=[]
        if not m['retrieved_candidates']:signals.append('missing_sources')
        if not m['retained_sources'] and m['retrieved_candidates']:signals.append('weak_geographic_or_company_relevance')
        if 'facility_exposure_not_established' in m['original_limitation_codes']:signals.append('weak_geographic_or_company_relevance')
        if m['inaccessible_source_count']:signals.append('inaccessible_documents')
        if m['conflict_groups'] or 'historical_or_future_measure' in m['original_limitation_codes']:signals.append('conflicting_or_outdated_evidence')
        if m['synthesis_claims_omitted'] or (m['full_text_sources'] and not m['selected_claims']):signals.append('extraction_problems')
        return list(dict.fromkeys(signals))
    def recovery(self):
        folder=self.out/'recovery';folder.mkdir(exist_ok=True)
        schema=obj({'primary_cause':enum(CAUSES),'contributing_causes':arr(enum(CAUSES),5),'cause_explanation':STR,'confidence':enum(['high','medium','low']),'remaining_gap':STR,'recovery_assessment':enum(['no_useful_cached_support','partial_cached_support','potentially_adequate_source_reported_support']),'evidence':arr(obj({'passage_id':{'type':'string'},'supporting_excerpt':{'type':'string','minLength':20,'maxLength':550},'relevance_explanation':STR,'company_applicability':enum(['explicit_named_company_effect','facility_location_only','national_or_sector_context','not_established']),'temporal_status':enum(['source_reports_historical','source_reports_future','source_reports_effective_as_of_source_date','proposal_or_uncertain','date_not_established'])}),4)})
        for n,a in enumerate(self.bad[:self.args.recovery_limit] if self.args.recovery_limit else self.bad,1):
            qid=a['query_id'];path=folder/(qid+'.json')
            if path.exists() and json.loads(path.read_text()).get('status')=='reviewed':continue
            q=self.queries[qid];m=self.metrics(qid);passages=self.candidates(q);allowed={p['passage_id']:p for p in passages}
            local_schema=json.loads(json.dumps(schema))
            allowed_causes=self.initial_cause(m) or ['weak_geographic_or_company_relevance']
            local_schema['properties']['primary_cause']=enum(allowed_causes)
            local_schema['properties']['contributing_causes']=arr(enum(allowed_causes),5)
            local_schema['properties']['evidence']['items']['properties']['passage_id']=enum(allowed) if allowed else {'type':'string'}
            original=[self.claims[i] for i in a['selected_claim_ids'][:8]]
            evidence={'original_query':q['original_query'],'query_geography_hint':q['geography'],'research_date':a['research_date'],'audit_date':self.args.audit_date,'original_metrics':m,'causes_supported_by_observed_metrics':allowed_causes,'original_selected_evidence':[{'claim_id':x['claim_id'],'quote':x['statement'][:550],'url':x['source_url'],'kind':x['evidence_kind'],'fields':{k:v for k,v in x['fields'].items() if v and k in ['company','facility','effective_date','reported_policy_status','duty_rate','hts_code','country_of_origin']}} for x in original],'cached_full_text_passages':passages}
            instruction='Classify why this original answer is insufficient using exactly one primary cause and distinct contributing causes, chosen only from causes_supported_by_observed_metrics. An empty local-retrieval list does NOT mean original documents were inaccessible; check original_metrics. Classify the ORIGINAL answer gap, not an audit retrieval limitation. Separate missing sources from irrelevant sources; inaccessible full text from insufficient extraction/synthesis. A historical source is not necessarily false; current applicability may be unestablished. Conflict flags are unverified model suggestions. First try recovery ONLY from the cached full-text passages. Select up to 4 relevant exact contiguous quotes, each 20-550 characters, with passage IDs. Do not repeat an existing quote. Answer all required fields concisely. For company applicability require an explicit named-company effect, not mere facility location or a nationwide tariff. Never declare current law verified. A source reporting effective status only establishes what it reported at its own date. Empty evidence is valid; do not force a recovery.'
            try:
                result=self.model.call('recover_'+qid,instruction,evidence,local_schema)
                if result.get('primary_cause') not in allowed_causes:raise ValueError('Cause unsupported by observed metrics')
                result['contributing_causes']=sorted(set(result.get('contributing_causes',[]))-{result['primary_cause']})
                if not set(result['contributing_causes'])<=set(allowed_causes):raise ValueError('Unsupported contributing cause')
                valid=[];rejected=[]
                original_quotes={t.norm(c['statement']) for c in self.byq[qid]}
                for item in result.get('evidence',[]):
                    p=allowed.get(item.get('passage_id'));quote=item.get('supporting_excerpt','')
                    if not p or not isinstance(quote,str) or not 20<=len(quote)<=550 or t.norm(quote) not in t.norm(p['text']):rejected.append({'reason':'Quote not verbatim in supplied passage','item':item});continue
                    chunk=self.chunks[p['chunk_id']]
                    if t.norm(quote) not in t.norm(chunk['text']):raise ValueError('Passage provenance mismatch')
                    valid.append({**item,'recovery_claim_id':t.sid('recovered',qid,p['chunk_id'],quote),'query_id':qid,'chunk_id':p['chunk_id'],'document_id':p['document_id'],'source_url':p['url'],'evidence_kind':'full_document','already_extracted_for_query':t.norm(quote) in original_quotes,'source_text_path':self.documents[p['document_id']]['text_path'],'current_legal_applicability':'not_established','review_status':'locally_extracted_quote_validated_not_manually_verified'})
                result.update(status='reviewed',query_id=qid,query=q['original_query'],metrics=m,rule_signals=self.initial_cause(m),candidate_passage_ids=list(allowed),candidate_document_ids=sorted({p['document_id'] for p in passages}),validated_recovery_evidence=valid,rejected_recovery_evidence=rejected,recovery_does_not_automatically_resolve_insufficiency=True)
                t.dump(path,result)
            except Exception as e:t.dump(path,{'status':'failed','query_id':qid,'error':type(e).__name__,'metrics':m,'rule_signals':self.initial_cause(m)})
            self.progress('cached_recovery',n,len(self.bad));print(f'recovery {n}/{len(self.bad)} {qid}: '+json.loads(path.read_text())['status'],flush=True)
    def conflict_pairs(self):
        pairs={}
        for a in self.data['answers']:
            for group in a['conflicts']:
                for pair in itertools.combinations(group,2):
                    pair=tuple(sorted(pair));pid=t.sid('conflict',pair)
                    row=pairs.setdefault(pid,{'pair_id':pid,'claim_ids':list(pair),'query_ids':[]})
                    row['query_ids']=sorted(set(row['query_ids']+[a['query_id']]))
        return list(pairs.values())
    def conflicts(self):
        pairs=self.conflict_pairs();folder=self.out/'conflicts';folder.mkdir(exist_ok=True)
        for start in range(0,len(pairs),10):
            batch=pairs[start:start+10];path=folder/f'batch_{start:04d}.json'
            if path.exists() and json.loads(path.read_text()).get('status')=='reviewed':continue
            items=[]
            for p in batch:
                items.append({**p,'claims':[{'claim_id':cid,'quote':self.claims[cid]['statement'][:900],'url':self.claims[cid]['source_url'],'kind':self.claims[cid]['evidence_kind'],'publisher_type':self.documents[self.claims[cid]['document_id']]['publisher_type'],'fields':{k:v for k,v in self.claims[cid]['fields'].items() if v and k in ['company','facility','tariff_program','legal_authority','affected_product','hts_code','chapter_99_code','country_of_origin','exporting_country','duty_rate','effective_date','expiration_date','announcement_date','reported_policy_status']}} for cid in p['claim_ids']]})
            row_schema=obj({'classification':enum(PAIR_STATUSES),'reason':STR,'requires_current_authority_verification':{'type':'boolean'}})
            schema=obj({'pairs':obj({p['pair_id']:row_schema for p in batch})})
            try:
                result=self.model.call('conflicts_'+str(start),'Review these previously model-flagged conflict pairs against the supplied quotations and scope/date fields. Do not assume every pair is a conflict. Different products, origins, tariff programs, or dated stages are not automatically contradictory. Only use apparent_same_scope_conflict when the supplied claims appear incompatible on the same scope/date; otherwise use different_dates_or_policy_stages for dated progression, different_products_origins_or_programs for differing scope, complementary_or_no_conflict for complementary or identical claims, and insufficient_scope for missing scope. The classification MUST agree with the reason. An old conditional expiry and a later renewal are compatible. Do not verify current law from memory. Explain the reason briefly for every pair.',{'research_date':self.args.audit_date,'pairs':items},schema)
                if set(result.get('pairs',{}))!={p['pair_id'] for p in batch}:raise ValueError('Pair coverage mismatch')
                rows=[{**p,**result['pairs'][p['pair_id']],'assessment_method':'local_Qwen_scope_review_not_manual_verification','resolved':False} for p in batch]
                if any(r['classification'] not in PAIR_STATUSES for r in rows):raise ValueError('Invalid conflict classification')
                t.dump(path,{'status':'reviewed','pairs':rows})
            except Exception as e:t.dump(path,{'status':'failed','error':type(e).__name__,'pairs':batch})
            self.progress('conflict_review',min(start+10,len(pairs)),len(pairs));print(f'conflicts {min(start+10,len(pairs))}/{len(pairs)}',flush=True)
    def progress(self,stage,done,total):t.dump(self.out/'progress.json',{'stage':stage,'completed':done,'total':total,'updated_at':t.now(),'tavily_calls':0})
    def sample(self):
        path=self.out/'manual_sample.json'
        if path.exists():return
        rng=random.Random(20260910);selected=[];used=set();docs=set()
        for sector in self.lex['sectors']:
            pool=[c for c in self.data['claims'] if any(sector in self.queries[q]['sectors'] for q in c['query_ids'])]
            for stratum in ['company_or_facility','official_rate_or_date','snippet','historical_or_proposal','random_a','random_b']:
                candidates=[c for c in pool if c['claim_id'] not in used and c['document_id'] not in docs]
                if stratum=='company_or_facility':candidates=[c for c in candidates if c['fields'].get('company') and (c['fields'].get('facility') or c['fields'].get('oem_supplier_relationship'))]
                elif stratum=='official_rate_or_date':candidates=[c for c in candidates if self.documents[c['document_id']]['publisher_type']=='official_trade_authority' and (c['fields'].get('duty_rate') or c['fields'].get('effective_date'))]
                elif stratum=='snippet':candidates=[c for c in candidates if c['evidence_kind']=='search_snippet']
                elif stratum=='historical_or_proposal':candidates=[c for c in candidates if c['fields'].get('effective_date') or c['fields'].get('reported_policy_status')]
                if not candidates:candidates=[c for c in pool if c['claim_id'] not in used]
                if not candidates:continue
                c=rng.choice(sorted(candidates,key=lambda x:x['claim_id']));used.add(c['claim_id']);docs.add(c['document_id'])
                chunk=self.chunks[c['chunk_id']];quote=c['supporting_excerpt'];pos=chunk['text'].find(quote);pos=max(0,pos)
                selected.append({'sample_id':f'S{len(selected)+1:02d}','sector_stratum':sector,'risk_stratum':stratum,'claim':c,'document':self.documents[c['document_id']],'source_context':chunk['text'][max(0,pos-550):min(len(chunk['text']),pos+len(quote)+550)]})
        t.dump(path,{'method':'Seeded stratified purposive sample, 6 per sector; diverse source URLs where available. Not a statistically representative prevalence estimate.','seed':20260910,'sample':selected})
    def initialize(self):
        path=self.out/'base_manifest.json'
        if not path.exists():
            t.dump(path,{'base_directory':str(self.base),'created_at':t.now(),'file_sha256':manifest(self.base),'request_ledger':list(self.ledger)})
        self.sample()
        t.dump(self.out/'audit_config.json',{'version':self.out.name,'base':str(self.base),'audit_date':self.args.audit_date,'research_date':'2026-09-09','model':self.args.model,'ollama_url':self.args.ollama_url,'think':False,'tavily_calls_permitted':False,'external_document_downloads_permitted':False,'recovery_query_count':len(self.bad),'cached_passages':self.index.execute('SELECT COUNT(*) FROM passages').fetchone()[0],'candidate_passage_limit':8,'recovery_quote_limit':4,'conflict_pair_count':len(self.conflict_pairs())})
    def run(self):
        self.initialize()
        if self.args.prepare_only:return
        with urllib.request.build_opener(NoRedirect()).open(self.model.endpoint+'/api/tags',timeout=10) as response:
            tags=json.load(response)
        matching=[m for m in tags['models'] if m['name']==self.args.model]
        if not matching:raise ValueError('Required local model is not installed')
        t.dump(self.out/'local_model_verified.json',{'checked_at':t.now(),'model':matching[0]})
        if self.args.stage in {'all','recovery'}:self.recovery()
        if self.args.stage in {'all','conflicts'}:self.conflicts()
        failed=sum(json.loads(p.read_text()).get('status')=='failed' for folder in ['recovery','conflicts'] for p in (self.out/folder).glob('*.json'))
        self.progress('local_review_pass_has_failures' if failed else 'local_review_pass_finished',len(self.bad),len(self.bad))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=Path('outputs/tariffs/pilot-2026-09-09'));p.add_argument('--out',type=Path,default=Path('outputs/tariffs/quality-audit-v1-2026-09-10'));p.add_argument('--terms',type=Path,default=Path('data/tariffs/targeted_terms.json'));p.add_argument('--ollama-url',default='http://localhost:11434');p.add_argument('--model',default='qwen3.5:35b-a3b');p.add_argument('--audit-date',default='2026-09-10');p.add_argument('--prepare-only',action='store_true');p.add_argument('--stage',choices=['all','recovery','conflicts'],default='all');p.add_argument('--recovery-limit',type=int);args=p.parse_args();Audit(args).run()
