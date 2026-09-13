import copy,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import finalize_tariff_quality_audit as f
import research_tariffs as t
import audit_tariff_quality as a

class FinalizeQualityTests(unittest.TestCase):
    def claim(self):
        return {'claim_id':'c1','statement':'Location in Georgia.','supporting_excerpt':'Location in Georgia.','fields':{'company':'CBP','effective_date':'Updated 2025','expiration_date':None},'field_support':{'company':'CBP','effective_date':'Updated 2025'},'source_url':'https://example.org'}
    def patch(self):
        return {'clear_fields':['company','effective_date'],'set_fields':{'expiration_date':{'value':'December 31, 2027','excerpt':'through December 31, 2027'}},'audit_flags':['date_role'],'audit_verdict':'field_error','reason':'Expiration is not effective date.'}
    def test_corrections_preserve_quote_and_original_and_validate_source(self):
        claim=self.claim();original=copy.deepcopy(claim)
        result=f.apply_patch(claim,self.patch(),{'text':'Relief applies through December 31, 2027.'})
        self.assertEqual(claim,original);self.assertEqual(result['statement'],claim['statement']);self.assertEqual(result['claim_id'],'c1')
        self.assertIsNone(result['fields']['company']);self.assertNotIn('company',result['field_support']);self.assertEqual(result['fields']['expiration_date'],'December 31, 2027')
        with self.assertRaisesRegex(ValueError,'Unsupported correction'):f.apply_patch(claim,self.patch(),{'text':'Different source.'})
    def test_new_value_must_be_supported_by_its_own_excerpt(self):
        patch=self.patch();patch['set_fields']['expiration_date']['value']='2028'
        with self.assertRaisesRegex(ValueError,'Unsupported correction'):f.apply_patch(self.claim(),patch,{'text':'2028 forecast; relief through December 31, 2027.'})
    def test_drafts_deduplicate_and_keep_parentage_without_inventing_company(self):
        lex=json.loads(Path('data/tariffs/targeted_terms.json').read_text())
        queries=[{'query_id':'q_1','original_query':'Georgia battery tariffs','sectors':['batteries_and_minerals'],'geography':'statewide_georgia'},{'query_id':'q_2','original_query':'Georgia battery tariffs','sectors':['batteries_and_minerals'],'geography':'statewide_georgia'},{'query_id':'q_3','original_query':'Hyundai display imports','sectors':['displays'],'geography':'southeast_georgia'}]
        rows=f.draft_queries(queries,lex)
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['parent_query_ids'],['q_1','q_2']);self.assertEqual(rows[0]['company_names'],[])
        self.assertIn('Georgia',rows[0]['query']);self.assertEqual(rows[1]['company_names'],['Hyundai']);self.assertTrue(all(r['execution_status']=='not_executed' for r in rows))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'drafts.csv';a.write_csv(path,rows);parsed=t.parse_queries(path)
            inventory=parsed[0] if isinstance(parsed,tuple) else parsed
            self.assertEqual(len(inventory),2);self.assertEqual(inventory[0]['parent_query_ids'],['q_1','q_2']);self.assertEqual(inventory[0]['parent_query_id'],'q_1')
    def test_finalization_refuses_missing_conflict_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'original';out=root/'revision';base.mkdir();out.mkdir();(out/'recovery').mkdir()
            db=sqlite3.connect(base/'corpus.sqlite')
            db.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT)')
            db.execute('CREATE TABLE requests(estimated REAL,reported REAL)')
            db.execute('INSERT INTO records VALUES(?,?,?)',('answers','q_1',json.dumps({'query_id':'q_1','status':'insufficient_evidence','conflicts':[['c1','c2']]})))
            db.commit();db.close()
            (out/'base_manifest.json').write_text(json.dumps({'file_sha256':a.manifest(base),'request_ledger':[0,None,None]}))
            (out/'recovery'/'q_1.json').write_text(json.dumps({'query_id':'q_1','status':'reviewed'}))
            (out/'manual_cause_review.json').write_text('{"reviews":[]}')
            with self.assertRaisesRegex(ValueError,'1 missing pairs'):
                f.finalize(base,out,root/'unused_terms.json')
            self.assertFalse((out/'claims.v1.jsonl').exists())

    def test_screening_does_not_modify_fields(self):
        claim=self.claim();before=copy.deepcopy(claim);flags=f.scan(claim)
        self.assertIn('company_field_non_company_candidate',flags);self.assertIn('effective_date_may_be_publication_update',flags);self.assertEqual(claim,before)

if __name__=='__main__':unittest.main()
