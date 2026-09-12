import csv,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import research_tariffs as t
import research_company_tariffs as c
import build_company_tariff_profiles as profiles
import audit_tariff_quality as a

class CompanyTariffTests(unittest.TestCase):
    def test_company_and_domain_metadata_survives_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'queries.csv';a.write_csv(p,[{'id':'one','query':'Company X tariff','company_id':'company_x','company_name':'Company X','company_aliases':['Company X'],'seed_row_ids':['row_2','row_9'],'include_domains':['cbp.gov'],'query_purpose':'shared_policy_verification'}]);rows,_=t.parse_queries(p)
            self.assertEqual(rows[0]['company_aliases'],['Company X']);self.assertEqual(rows[0]['seed_row_ids'],['row_2','row_9']);self.assertEqual(rows[0]['include_domains'],['cbp.gov'])
    def test_search_forwards_official_domain_restriction_without_auto_depth(self):
        client=object.__new__(t.Tavily);client.args=SimpleNamespace(search_depth='basic',max_results=8,tavily_answer=False)
        client.call=lambda operation,owner,payload:payload
        result=client.search({'query_id':'q_x','original_query':'steel tariff','include_domains':['cbp.gov','ustr.gov']})
        self.assertEqual(result['include_domains'],['cbp.gov','ustr.gov']);self.assertFalse(result['auto_parameters']);self.assertEqual(result['search_depth'],'basic')
    def test_chunk_selection_preserves_evidence_and_favors_company(self):
        chunks=[{'text':'generic tariff','chunk_id':'1'},{'text':'Company X imported steel faces tariffs','chunk_id':'2'},{'text':'irrelevant','chunk_id':'3'}]
        selected=t.select_document_chunks(chunks,{'original_query':'Company X steel tariff','company_aliases':['Company X']},1)
        self.assertEqual(selected,[chunks[1]]);self.assertIs(selected[0],chunks[1]);self.assertEqual(t.select_document_chunks(chunks,{'original_query':'x'},0),chunks)
    def test_parent_group_name_does_not_verify_local_company(self):
        company={'company_name':'ZF Gainesville LLC','search_aliases':['ZF Gainesville LLC','zf gainesville']}
        claim={'statement':'ZF reports tariff costs.','fields':{'company':'ZF'}}
        self.assertEqual(profiles.identity_scope(company,claim),'potential_company_or_group_context')
        claim={'statement':'ZF Gainesville expanded its factory.','fields':{'company':'ZF Gainesville'}}
        self.assertEqual(profiles.identity_scope(company,claim),'company_name_matches_cached_evidence')
    def test_short_company_names_require_case_sensitive_quote_or_named_field(self):
        company={'company_name':'AVS','search_aliases':['AVS','avs']}
        self.assertIsNone(profiles.identity_scope(company,{'statement':'An avs item','fields':{}}))
        self.assertEqual(profiles.identity_scope(company,{'statement':'AVS faces tariffs','fields':{}}),'company_name_matches_cached_evidence')
    def test_name_normalization_does_not_merge_different_facilities(self):
        self.assertEqual(c.normalize_name('Novelis Inc.'),'novelis');self.assertNotEqual(c.normalize_name('ZF Gainesville LLC'),c.normalize_name('ZF North America LLC'))

if __name__=='__main__':unittest.main()
