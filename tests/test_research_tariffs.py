"""Offline regression tests. Fixtures are synthetic, never live research evidence."""
import contextlib
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import research_tariffs as t
import check_tavily_usage as usage_checker
from audit_tariff_corpus import audit


class Response(io.BytesIO):
    def __init__(self,value):
        super().__init__(json.dumps(value).encode())


class TariffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.args=t.parser().parse_args(['--out',str(self.root/'run')])
        self.args.max_credits=100
        self.store=t.Store(self.args.out,100)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.db.close)

    def test_usage_rate_limit_stops_entire_key_batch(self):
        out=self.root/'balances'
        refusal=urllib.error.HTTPError('https://api.tavily.com/usage',429,'rate limit',{'Retry-After':'60'},None)
        with patch.dict(os.environ,{'TAVILY_API_KEYS':'synthetic-one,synthetic-two'}), \
             patch.object(sys,'argv',['check_tavily_usage.py','--env-file',str(self.root/'missing.env'),'--out',str(out)]), \
             patch.object(usage_checker.urllib.request.OpenerDirector,'open',side_effect=refusal) as network, \
             patch.object(usage_checker.time,'sleep'), contextlib.redirect_stdout(io.StringIO()):
            usage_checker.main()
        self.assertEqual(network.call_count,1)
        rows=json.loads((out/'keys.json').read_text())
        self.assertEqual([r['status'] for r in rows],['http_error','deferred_rate_limit'])
        self.assertEqual(rows[0]['retry_after'],'60')
        summary=json.loads((out/'summary.json').read_text())
        self.assertIsNone(summary['largest_confirmed_single_key_plan_balance'])
        self.assertNotIn('synthetic-one',(out/'keys.json').read_text())

    def test_preserve_numbering_text_and_duplicates(self):
        path=self.root/'queries.md'
        path.write_text('# Bank\n\n1. Georgia EV tariffs\n2.  Georgia EV tariffs\n2. Metals\n- Unnumbered question\n')
        rows,stats=t.parse_queries(path)
        self.assertEqual(stats['input_queries'],4)
        self.assertEqual(stats['duplicate_queries'],1)
        self.assertEqual(rows[1]['duplicate_of'],'q_1')
        self.assertEqual(rows[2]['query_id'],'q_2__2')
        self.assertEqual(rows[0]['original_query'],'Georgia EV tariffs')
        self.assertEqual(rows,t.parse_queries(path)[0])

    def test_csv_preserves_quotes_and_ids(self):
        path=self.root/'queries.csv'
        with path.open('w',newline='') as f:
            w=csv.writer(f); w.writerow(['id','query']); w.writerow(['001','"Metaplant", tariffs']); w.writerow(['','Battery tariffs'])
        rows,stats=t.parse_queries(path)
        self.assertEqual(rows[0]['original_id'],'001')
        self.assertEqual(rows[0]['original_query'],'"Metaplant", tariffs')
        self.assertEqual(stats['input_queries'],2)

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), 'optional XLSX reader unavailable')
    def test_xlsx_query_inventory_preserves_ids_and_original_text(self):
        import openpyxl
        path=self.root/'queries.xlsx'
        book=openpyxl.Workbook()
        sheet=book.active
        sheet.append(['id','query'])
        sheet.append(['001','Georgia battery tariffs'])
        sheet.append(['002','Georgia battery tariffs'])
        book.save(path); book.close()
        rows,stats=t.parse_queries(path)
        self.assertEqual(rows[0]['original_id'],'001')
        self.assertEqual(rows[0]['original_query'],'Georgia battery tariffs')
        self.assertEqual(rows[1]['duplicate_of'],'q_001')
        self.assertEqual(stats['duplicate_queries'],1)

    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'optional PDF reader unavailable')
    def test_unreadable_pdf_download_is_not_full_text_evidence(self):
        from pypdf import PdfWriter
        from email.message import Message
        content=io.BytesIO()
        writer=PdfWriter(); writer.add_blank_page(width=100,height=100); writer.write(content)
        class Page(io.BytesIO):
            def __init__(self):
                super().__init__(content.getvalue())
                self.headers=Message(); self.headers['Content-Type']='application/pdf'
                self.url='https://example.com/document.pdf'
        class Opener:
            def open(self,*args,**kwargs): return Page()
        candidate=dict(document_id='pdf-doc',canonical_url='https://example.com/document.pdf',
            metadata={'title':'Synthetic blank PDF','content':'Synthetic snippet only; the PDF has no machine-readable content.'})
        with patch.object(t,'public_url',side_effect=lambda u:u),patch.object(t.urllib.request,'build_opener',return_value=Opener()):
            result=t.download_document(self.store,self.args,None,candidate)
        self.assertTrue(result['downloaded'])
        self.assertEqual(result['evidence_kind'],'search_snippet')
        self.assertTrue((self.args.out/result['raw_path']).read_bytes().startswith(b'%PDF'))
        self.assertTrue(result['failures'])

    def test_query_selection_preserves_text_and_cumulative_limit(self):
        inventory,_=t.parse_queries(t.ROOT/'data/tariffs/queries.txt')
        p=self.root/'selection.txt';p.write_text('q_1\nq_246\nq_156\nq_181\n')
        selected=t.select_queries(inventory,4,p,['q_1'])
        self.assertEqual([q['query_id'] for q in selected],['q_1','q_246','q_156','q_181'])
        self.assertEqual(selected[1]['original_query'],inventory[245]['original_query'])
        with self.assertRaisesRegex(ValueError,'exceeds'):
            t.select_queries(inventory,3,p)
        with self.assertRaisesRegex(ValueError,'previously attempted'):
            t.select_queries(inventory,4,p,['q_2'])
        with self.assertRaisesRegex(ValueError,'previously attempted'):
            t.select_queries(inventory,50,None,['q_246'])
        self.assertEqual(len(t.select_queries(inventory,510,None,['q_246'])),510)
        p.write_text('q_1\nq_1\n')
        with self.assertRaisesRegex(ValueError,'duplicate'):
            t.select_queries(inventory,4,p)
        p.write_text('q_999\n')
        with self.assertRaisesRegex(ValueError,'unknown'):
            t.select_queries(inventory,4,p)

    def test_supplied_bank_counts_and_tail(self):
        rows,stats=t.parse_queries(t.ROOT/'data/tariffs/queries.txt')
        self.assertEqual((stats['input_queries'],stats['unique_queries'],stats['duplicate_queries']),(510,510,0))
        self.assertEqual(rows[-1]['query_id'],'q_510')

    def test_canonical_urls_preserve_semantic_parameters(self):
        a=t.canonical_url('https://EXAMPLE.com:443/p?b=2&utm_source=x&a=1#top')
        self.assertEqual(a,'https://example.com/p?a=1&b=2')
        self.assertNotEqual(t.canonical_url('https://example.com/p?a=2'),a)
        self.assertNotEqual(t.canonical_url('https://example.com/P'),t.canonical_url('https://example.com/p'))
        with self.assertRaises(ValueError): t.canonical_url('file:///etc/passwd')
        with self.assertRaises(ValueError): t.canonical_url('https://user:secret@example.com')

    def test_source_authority_not_spoofable(self):
        self.assertEqual(t.credibility('https://www.cbp.gov/a')[0],1)
        self.assertEqual(t.credibility('https://cbp.gov.example.com/a')[0],.5)

    def test_chunks_cover_text_and_overlap(self):
        body='abcdefghijklmnopqrstuvwxyz'
        rows=t.chunks(body,'doc',10,3)
        self.assertEqual(rows[0]['text'][-3:],rows[1]['text'][:3])
        self.assertEqual(rows[-1]['end_char'],len(body))
        self.assertEqual(rows,t.chunks(body,'doc',10,3))
        self.assertNotEqual(rows[0]['chunk_id'],t.chunks(body+'!', 'doc',10,3)[0]['chunk_id'])
        with self.assertRaises(ValueError): t.chunks(body,'doc',3,3)

    def test_atomic_budget_concurrency_and_unknown_outcomes(self):
        self.store.max_credits=3
        def reserve(i):
            try: return self.store.reserve('search',str(i),{'query':str(i)},1)
            except t.BudgetStop: return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            successes=[r for r in pool.map(reserve,range(20)) if r]
        self.assertEqual(len(successes),3)
        self.assertEqual(self.store.usage()['unknown_outcome_requests'],3)
        reopened=t.Store(self.args.out,3)
        try:
            with self.assertRaises(t.BudgetStop): reopened.reserve('search','resume',{},1)
        finally: reopened.db.close()

    def test_reported_cost_cannot_reduce_reservation(self):
        rid,_=self.store.reserve('search','q1',{},2)
        self.store.finish_request(rid,200,{'usage':{'credits':0}})
        self.assertEqual(self.store.usage()['budget_accounted_credits'],2)
        self.assertEqual(self.store.usage()['provider_reported_credits'],0)
        rid,_=self.store.reserve('search','q2',{},1)
        self.store.finish_request(rid,200,{'usage':{'credits':4}})
        self.assertEqual(self.store.usage()['budget_accounted_credits'],6)

    def test_search_success_resume_never_recharges(self):
        client=t.Tavily(self.store,self.args,['synthetic-secret'])
        query={'query_id':'q1','original_query':'original search'}
        data={'results':[],'usage':{'credits':1}}
        with patch.object(t.urllib.request,'urlopen',return_value=Response(data)) as network:
            self.assertEqual(client.search(query),data)
            self.assertEqual(client.search(query),data)
            self.assertEqual(network.call_count,1)
        self.assertEqual(self.store.usage()['estimated_credits'],1)
        for p in (self.args.out/'raw_tavily').glob('*.json'):
            self.assertNotIn('synthetic-secret',p.read_text())

    def test_retries_are_budgeted_and_redact_credentials(self):
        client=t.Tavily(self.store,self.args,['synthetic-secret'])
        err=urllib.error.HTTPError('https://api.tavily.com/search',429,'limit',{'Retry-After':'0'},io.BytesIO(b'synthetic-secret'))
        with patch.object(t.urllib.request,'urlopen',side_effect=[err,Response({'results':[]})]),patch.object(t.time,'sleep'):
            client.search({'query_id':'q1','original_query':'tariffs'})
        self.assertEqual(self.store.usage()['estimated_credits'],2)
        for p in (self.args.out/'raw_tavily').glob('*.json'):
            self.assertNotIn('synthetic-secret',p.read_text())

    def test_retry_after_date_and_persistent_cooldown(self):
        self.assertEqual(t.retry_delay('5',0),5)
        future=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=30))
        self.assertGreater(t.retry_delay(future,0),28)
        with self.assertRaises(RuntimeError): t.retry_delay('300',0)
        client=t.Tavily(self.store,self.args,['secret'])
        err=urllib.error.HTTPError('https://api.tavily.com/search',429,'limit',{'Retry-After':'300'},io.BytesIO(b'limit'))
        query={'query_id':'q1','original_query':'tariffs'}
        with patch.object(t.urllib.request,'urlopen',side_effect=err) as network:
            with self.assertRaises(RuntimeError): client.search(query)
            with self.assertRaises(RuntimeError): client.search(query)
            self.assertEqual(network.call_count,1)
        self.assertEqual(self.store.usage()['estimated_credits'],1)

    def test_quota_failover_persists_across_queries_and_resume(self):
        self.args.retries=0
        client=t.Tavily(self.store,self.args,['first-secret','second-secret'])
        requests=[]
        def network(req,**kwargs):
            requests.append(req.get_header('Authorization'))
            if requests[-1]=='Bearer first-secret':
                raise urllib.error.HTTPError(req.full_url,432,'quota',{},io.BytesIO(b'first-secret exhausted'))
            return Response({'results':[], 'usage':{'credits':1}})
        with patch.object(t.urllib.request,'urlopen',side_effect=network):
            client.search({'query_id':'q1','original_query':'tariffs'})
            client.search({'query_id':'q2','original_query':'batteries'})
            resumed=t.Tavily(self.store,self.args,['second-secret','first-secret'])
            resumed.search({'query_id':'q3','original_query':'metals'})
        self.assertEqual(requests,['Bearer first-secret']+['Bearer second-secret']*3)
        self.assertEqual(self.store.usage()['estimated_credits'],4)
        self.assertEqual(len(self.store.all('key_rotation_events')),1)
        for kind in ['tavily_key_state','request_keys','key_rotation_events']:
            self.assertNotIn('first-secret',json.dumps(self.store.all(kind)))
        for path in (self.args.out/'raw_tavily').glob('*.json'):
            self.assertNotIn('first-secret',path.read_text())
            self.assertNotIn('second-secret',path.read_text())

    def test_all_keys_exhausted_stops_and_deduplicates_keys(self):
        client=t.Tavily(self.store,self.args,['first','first','second','third','fourth'])
        statuses=iter([401,402,432,433])
        def network(req,**kwargs):
            raise urllib.error.HTTPError(req.full_url,next(statuses),'refused',{},io.BytesIO(b'refused'))
        with patch.object(t.urllib.request,'urlopen',side_effect=network) as request:
            with self.assertRaises(t.NoUsableTavilyKey):
                client.search({'query_id':'q1','original_query':'tariffs'})
            self.assertEqual(request.call_count,4)
            with self.assertRaises(t.NoUsableTavilyKey):
                client.search({'query_id':'q2','original_query':'battery'})
            self.assertEqual(request.call_count,4)
        self.assertTrue(client.pool.exhausted())
        self.assertEqual(self.store.usage()['estimated_credits'],4)
        self.args.reset_tavily_keys=True
        reset=t.Tavily(self.store,self.args,['first','second'])
        self.assertFalse(reset.pool.exhausted())
        self.assertIn(reset.pool.select()[0],['first','second'])

    def test_failover_still_enforces_shared_credit_ceiling(self):
        self.store.max_credits=1
        client=t.Tavily(self.store,self.args,['first','second'])
        error=urllib.error.HTTPError('https://api.tavily.com/search',432,'quota',{},io.BytesIO(b'quota'))
        with patch.object(t.urllib.request,'urlopen',side_effect=error) as request:
            with self.assertRaises(t.BudgetStop):
                client.search({'query_id':'q1','original_query':'tariffs'})
            self.assertEqual(request.call_count,1)
        self.assertEqual(self.store.usage()['estimated_credits'],1)

    def test_forbidden_and_bad_request_do_not_rotate(self):
        for status in [400,403]:
            client=t.Tavily(self.store,self.args,['first','second'])
            error=urllib.error.HTTPError('https://api.tavily.com/search',status,'error',{},io.BytesIO(b'error'))
            with patch.object(t.urllib.request,'urlopen',side_effect=error) as request:
                with self.assertRaises(RuntimeError):
                    client.search({'query_id':str(status),'original_query':'tariffs'})
                self.assertEqual(request.call_count,1)
        self.assertFalse(self.store.all('key_rotation_events'))

    def test_cooldown_is_shared_across_queries_and_survives_key_reset(self):
        client=t.Tavily(self.store,self.args,['first'])
        error=urllib.error.HTTPError('https://api.tavily.com/search',429,'rate',{'Retry-After':'300'},io.BytesIO(b'rate'))
        with patch.object(t.urllib.request,'urlopen',side_effect=error) as request:
            with self.assertRaises(RuntimeError):
                client.search({'query_id':'q1','original_query':'tariffs'})
            self.args.reset_tavily_keys=True
            resumed=t.Tavily(self.store,self.args,['first'])
            with self.assertRaises(t.NoUsableTavilyKey):
                resumed.search({'query_id':'q2','original_query':'battery'})
            self.assertEqual(request.call_count,1)

    def test_extract_uses_the_same_key_pool(self):
        self.args.paid_extract='basic'
        client=t.Tavily(self.store,self.args,['first','second'])
        error=urllib.error.HTTPError('https://api.tavily.com/extract',433,'quota',{},io.BytesIO(b'quota'))
        with patch.object(t.urllib.request,'urlopen',side_effect=[error,Response({'results':[]})]) as request:
            client.call('extract','doc1',{'urls':['https://example.com']})
            self.assertEqual([c.args[0].get_header('Authorization') for c in request.call_args_list],['Bearer first','Bearer second'])
        self.assertEqual(client.pool.select()[0],'second')

    def fixture_claim(self):
        text='Example manufacturer plans battery production in Bryan County, Georgia in 2027.'
        chunk=t.chunks(text,'doc')[0]
        source=dict(document_id='doc',url='https://example.com/source',title='Synthetic fixture',publisher='example.com',evidence_kind='search_snippet',retrieved_at=t.now(),text_path='text/test.txt',content_hash=t.digest(text))
        return text,chunk,source,{'claims':[{'supporting_excerpt':text,'fields':{}}]}

    def test_claim_provenance_and_no_unstated_rate(self):
        text,chunk,source,value=self.fixture_claim()
        claims,rejected=t.validate_claims(value,chunk,source,'q1','2026-09-08')
        self.assertEqual(len(claims),1)
        self.assertEqual(claims[0]['source_url'],source['url'])
        self.assertIsNone(claims[0]['fields']['duty_rate'])
        self.assertEqual(claims[0]['policy_status_as_of'],'uncertain')
        self.assertFalse(rejected)
        value['claims'][0]['fields']['duty_rate']={'value':'25%','excerpt':text}
        claims,rejected=t.validate_claims(value,chunk,source,'q1','2026-09-08')
        self.assertEqual(len(claims),1)
        self.assertIsNone(claims[0]['fields']['duty_rate'])
        self.assertIn('not grounded',rejected[0]['reason'])
        self.assertEqual(rejected[0]['rejection_scope'],'optional_field')

    def test_identical_content_preserves_distinct_source_claims(self):
        text,chunk,source,value=self.fixture_claim()
        first=t.validate_claims(value,chunk,source,'q1','2026-09-08')[0][0]
        second=t.validate_claims(value,chunk,{**source,'document_id':'mirror','url':'https://example.com/mirror'},'q2','2026-09-08')[0][0]
        self.assertNotEqual(first['claim_id'],second['claim_id'])
        self.assertEqual(first['chunk_id'],second['chunk_id'])

    def test_export_country_does_not_establish_origin(self):
        text,chunk,source,value=self.fixture_claim()
        value['claims'][0]['fields']['country_of_origin']={'value':'Georgia','excerpt':text}
        # Explicit production wording may establish origin, whereas an export-only
        # passage must not be classified as origin even when its value is verbatim.
        export='The exporter ships components from Korea to the United States.'
        chunk=t.chunks(export,'doc')[0]
        value={'claims':[{'supporting_excerpt':export,'fields':{'country_of_origin':{'value':'Korea','excerpt':export},'exporting_country':{'value':'Korea','excerpt':export}}}]}
        claims,rejected=t.validate_claims(value,chunk,source,'q1','2026-09-09')
        self.assertIsNone(claims[0]['fields']['country_of_origin'])
        self.assertEqual(claims[0]['fields']['exporting_country'],'Korea')
        self.assertTrue(rejected)

    @unittest.skipUnless(importlib.util.find_spec('trafilatura'), 'optional HTML reader unavailable')
    def test_readable_html_discards_navigation(self):
        paragraph='This synthetic article discusses supplier costs and manufacturing plans in Georgia. '+('The company reported changes to its sourcing and investment plans. '*8)
        html=('<html><body><nav>UNRELATED NAVIGATION</nav><article><h1>Supplier report</h1><p>'+paragraph+'</p></article><footer>UNRELATED FOOTER</footer></body></html>').encode()
        text,method=t.readable_html(html,'https://example.com/article')
        self.assertIn('supplier costs',text)
        self.assertNotIn('UNRELATED NAVIGATION',text)
        self.assertNotIn('UNRELATED FOOTER',text)
        self.assertEqual(method,'trafilatura_main_text')

    def test_fabricated_excerpt_and_facility_confirmation_rejected(self):
        text,chunk,source,value=self.fixture_claim()
        value['claims'][0]['supporting_excerpt']='The tariff costs this Georgia facility 100 million dollars.'
        self.assertFalse(t.validate_claims(value,chunk,source,'q1','2026-09-08')[0])
        value['claims'][0]['supporting_excerpt']=text
        value['claims'][0]['geographic_connection']='confirmed_southeast_georgia_facility'
        claims,rejected=t.validate_claims(value,chunk,source,'q1','2026-09-08')
        self.assertEqual(claims[0]['geographic_connection'],'needs_verification')
        self.assertTrue(rejected)

    def test_answer_coverage_uses_saved_evidence_and_preserves_insufficiency(self):
        self.store.put('claims','c1',{'claim_id':'c1','evidence_kind':'full_document'})
        self.store.put('answers','q1',dict(query_id='q1',selected_claim_ids=['c1'],
            limitation_codes=['snippet_only','conflicting_sources','insufficient_evidence'],
            conflicts=[],status='complete'))
        self.store.put('query_state','q1',dict(query_id='q1',status='complete'))
        t.normalize_answer_metadata(self.store)
        answer=self.store.get('answers','q1')
        self.assertEqual(answer['status'],'insufficient_evidence')
        self.assertNotIn('snippet_only',answer['limitation_codes'])
        self.assertNotIn('conflicting_sources',answer['limitation_codes'])
        self.assertEqual(self.store.get('query_state','q1')['status'],'insufficient_evidence')
        self.store.put('claims','c1',{'claim_id':'c1','evidence_kind':'search_snippet'})
        t.normalize_answer_metadata(self.store)
        self.assertIn('snippet_only',self.store.get('answers','q1')['limitation_codes'])

    def test_synthesis_rejects_unknown_citations_and_retains_conflicts(self):
        claims=[{'claim_id':'c1'},{'claim_id':'c2'}]
        data={'selected_claim_ids':['c1','c2'],'limitation_codes':['conflicting_sources'],'conflicts':[['c1','c2']]}
        self.assertEqual(t.validate_synthesis(data,claims)[2],[['c1','c2']])
        data['selected_claim_ids']=['invented']
        with self.assertRaises(ValueError): t.validate_synthesis(data,claims)

    def test_pdf_layout_cleanup_preserves_original_evidence(self):
        quote='A tariff rate of 25 percent applies to the specified products.'
        original={'chunk':{'text':quote+' . '*30+' 9903.91.02', 'chunk_id':'original'}}
        cleaned=t.model_evidence(original)
        self.assertIn(quote,cleaned['chunk']['text'])
        self.assertIn('9903.91.02',cleaned['chunk']['text'])
        self.assertNotIn(' . '*12,cleaned['chunk']['text'])
        self.assertIn(' . '*12,original['chunk']['text'])
        self.assertEqual(cleaned['chunk']['chunk_id'],'original')
        self.assertIn('layout_note',cleaned)
        plain={'chunk':{'text':'The duty rate is 2.5 percent.'}}
        self.assertIs(t.model_evidence(plain),plain)

    def test_synthesis_bounds_prevent_runaway_citation_lists(self):
        claims=[{'claim_id':f'c{i}'} for i in range(30)]
        data={'selected_claim_ids':[c['claim_id'] for c in claims], 'limitation_codes':[], 'conflicts':[]}
        with self.assertRaises(ValueError): t.validate_synthesis(data,claims)
        data['selected_claim_ids']=data['selected_claim_ids'][:20]
        self.assertEqual(len(t.validate_synthesis(data,claims)[0]),20)
        data['conflicts']=[['c1','c1']]
        with self.assertRaises(ValueError): t.validate_synthesis(data,claims)
        schema=t.response_schema({'claims':claims})
        self.assertEqual(schema['properties']['selected_claim_ids']['maxItems'],20)
        self.assertEqual(schema['properties']['conflicts']['maxItems'],5)

    def test_assessment_map_requires_every_original_candidate(self):
        value={'assessments':{'c1':{'relevance':.8,'reason':'Relevant'},'c2':{'relevance':.2,'reason':'Weak'}}}
        self.assertEqual(set(t.validate_assessment(value,{'c1','c2'})),{'c1','c2'})
        with self.assertRaises(ValueError):t.validate_assessment(value,{'c1','c3'})
        value['assessments']['c2']=None
        with self.assertRaises(ValueError):t.validate_assessment(value,{'c1','c2'})

    def test_duplicate_valid_citations_are_normalized_without_inventing_evidence(self):
        claims=[{'claim_id':'c1'},{'claim_id':'c2'}]
        value={'selected_claim_ids':['c1','c2','c1'], 'limitation_codes':['conflicting_sources'],
               'conflicts':[['c1','c2'],['c2','c1']]}
        selected,_,conflicts=t.validate_synthesis(value,claims)
        self.assertEqual(selected,['c1','c2'])
        self.assertEqual(conflicts,[['c1','c2']])
        value['selected_claim_ids'].append('invented')
        with self.assertRaises(ValueError):t.validate_synthesis(value,claims)

    def test_assessment_requires_complete_unique_coverage(self):
        with self.assertRaises(ValueError): t.validate_assessment({'assessments':[]},{'c1'})
        with self.assertRaises(ValueError): t.validate_assessment({'assessments':[{'candidate_id':'c1','relevance':float('nan'),'reason':'x'}]},{'c1'})

    def test_preflight_does_not_substitute_smaller_model(self):
        self.args.ollama_url='http://localhost:11434'
        with patch.object(t.urllib.request,'urlopen',return_value=Response({'models':[{'name':'qwen3:14b'}]})):
            result=t.preflight(self.args,['key'])
        self.assertIsNone(result['verified_model'])
        self.assertTrue(result['blockers'])
        with patch.object(t.urllib.request,'urlopen',return_value=Response({'models':[{'name':'qwen3.5:35b-a3b'}]})):
            result=t.preflight(self.args,['key'])
        self.assertEqual(result['verified_model'],'qwen3.5:35b-a3b')

    def test_expanded_bank_requires_explicit_sufficient_budget(self):
        args=t.parser().parse_args(['--max-queries','510','--dry-run','--out',str(self.root/'expanded')])
        with self.assertRaisesRegex(ValueError,'explicit'): t.run(args)
        args.max_credits=100
        with self.assertRaisesRegex(ValueError,'at least 510'): t.run(args)

    def test_document_content_dedup_keeps_source_provenance(self):
        text='Synthetic evidence source containing enough readable text for document chunk extraction and provenance checks.'
        class Page(io.BytesIO):
            def __init__(self):
                super().__init__(text.encode())
                from email.message import Message
                self.headers=Message(); self.headers['Content-Type']='text/plain'
                self.url='https://example.com/source'
        class Opener:
            def open(self,*a,**kw): return Page()
        with patch.object(t,'public_url',side_effect=lambda u:u),patch.object(t.urllib.request,'build_opener',return_value=Opener()):
            for i in range(2):
                c=dict(document_id=f'd{i}',canonical_url=f'https://example.com/{i}',metadata={'title':'Synthetic'})
                t.download_document(self.store,self.args,None,c)
        docs=self.store.all('documents')
        self.assertEqual(len(docs),2)
        self.assertEqual(docs[0]['content_hash'],docs[1]['content_hash'])
        self.assertEqual(docs[0]['text_path'],docs[1]['text_path'])
        self.assertNotEqual(docs[0]['url'],docs[1]['url'])
        self.assertEqual(docs[1]['duplicate_content_of'],'d0')

    def test_mocked_end_to_end_and_resume(self):
        """Exercise real HTTP request building, persistence, Qwen validation and exports."""
        path=self.root/'two.txt'; path.write_text('1. Georgia battery tariffs\n2. Georgia imported battery tariffs\n')
        out=self.root/'integration'
        args=t.parser().parse_args(['--queries',str(path),'--out',str(out),'--model','qwen3.5:35b-a3b','--retries','0','--keep-per-query','1'])
        text='Synthetic company reports battery tariff exposure in Georgia. No exact tariff rate is provided.'
        calls=[]
        def network(req,**kwargs):
            url=req if isinstance(req,str) else req.full_url
            calls.append(url)
            if url.endswith('/api/tags'):
                return Response({'models':[{'name':'qwen3.5:35b-a3b','digest':'fixture'}]})
            payload=json.loads(req.data)
            if url.endswith('/search'):
                return Response({'results':[{'url':'https://example.com/a','title':'Synthetic fixture','content':text},{'url':'https://example.com/a?utm_source=test','title':'Duplicate fixture','content':text}], 'usage':{'credits':1}})
            self.assertTrue(url.endswith('/api/chat'))
            evidence=json.loads(payload['messages'][1]['content'].split('UNTRUSTED_EVIDENCE_JSON:\n')[1])
            schema=payload['format']
            self.assertEqual(schema['type'],'object')
            expected='assessments' if 'candidates' in evidence else 'claims' if 'chunk' in evidence else 'selected_claim_ids'
            self.assertIn(expected,schema['required'])
            if 'candidates' in evidence:
                result={'assessments':{c['candidate_id']:{'relevance':.9,'reason':'Relevant synthetic fixture'} for c in evidence['candidates']}}
            elif 'chunk' in evidence:
                result={'claims':[{'supporting_excerpt':text,'fields':{}}]}
            else:
                result={'selected_claim_ids':[evidence['claims'][0]['claim_id']],'limitation_codes':['facility_exposure_not_established'],'conflicts':[]}
            return Response({'message':{'content':json.dumps(result)},'done_reason':'stop'})
        with patch.dict(os.environ,{'TAVILY_API_KEY':'synthetic-key','TAVILY_API_KEYS':'','LLM_BASE_URL':'http://localhost:11434/v1','OLLAMA_HOST':''}),patch.object(t.urllib.request,'urlopen',side_effect=network),patch.object(t,'public_url',side_effect=ValueError('Fixture: direct download unavailable')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.run(args),0)
            before=len(calls)
            with patch.object(t,'export',wraps=t.export) as exporter:
                self.assertEqual(t.run(args),0)
                self.assertEqual(exporter.call_count,1)
            self.assertEqual(calls[before:],['http://localhost:11434/api/tags'])
        summary=json.loads((out/'summary.json').read_text())
        self.assertEqual(summary['queries_processed'],2)
        self.assertEqual(summary['retrieved_candidates'],4)
        self.assertEqual(summary['retained_documents'],1)
        self.assertEqual(summary['claims'],1)
        self.assertEqual(summary['usage']['estimated_credits'],2)
        claim=json.loads((out/'claims.jsonl').read_text())
        self.assertEqual(claim['query_ids'],['q_1','q_2'])
        self.assertEqual(claim['evidence_kind'],'search_snippet')
        self.assertIn('[source](https://example.com/a)',(out/'findings.md').read_text())
        self.assertEqual(audit(out)['status'],'passed')
        text_path=out/claim['text_path']
        text_path.write_text('Tampered synthetic evidence')
        self.assertEqual(audit(out)['status'],'failed')
        rebuild_store=t.Store(out,100)
        try:
            before_usage=rebuild_store.usage()
            t.rebuild_evidence(rebuild_store)
            self.assertEqual(rebuild_store.usage(),before_usage)
            self.assertEqual(rebuild_store.all('claims'),[])
            self.assertEqual(len(rebuild_store.all('documents')),1)
            self.assertTrue(rebuild_store.cached_request('search','q_1'))
            self.assertEqual(len(rebuild_store.all('evidence_revisions')),1)
        finally:
            rebuild_store.db.close()
        self.assertEqual(audit(out)['status'],'passed')
        self.assertTrue(list((out/'revisions').glob('*/records.json')))
        changed=t.parser().parse_args(['--queries',str(path),'--out',str(out),'--dry-run','--search-depth','advanced'])
        with self.assertRaisesRegex(ValueError,'Resume configuration mismatch'): t.run(changed)


if __name__=='__main__': unittest.main()
