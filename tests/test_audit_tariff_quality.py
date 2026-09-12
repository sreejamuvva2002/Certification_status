import unittest,tempfile,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit_tariff_quality as a

class QualityAuditTests(unittest.TestCase):
    def test_audit_network_is_loopback_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            for endpoint in ['https://api.tavily.com','http://example.org','http://localhost.evil.org','http://secret@localhost:11434']:
                with self.assertRaises(ValueError):a.LocalModel(Path(tmp),endpoint,'qwen3.5:35b-a3b')
            model=a.LocalModel(Path(tmp),'http://localhost:11434','qwen3.5:35b-a3b')
            self.assertEqual(model.endpoint,'http://localhost:11434')
            with self.assertRaises(ValueError):a.NoRedirect().redirect_request(None,None,302,'',{},'https://api.tavily.com')
    def test_terms_use_word_boundaries(self):
        self.assertTrue(a.matches('castings','Automotive castings duties'))
        self.assertFalse(a.matches('steel','Steelman forecast'))
        self.assertFalse(a.matches('EV','review'))
    def test_manifest_detects_changes_without_mutating_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);f=p/'original.json';f.write_text('{"original":true}')
            first=a.manifest(p);self.assertEqual(first,a.manifest(p))
            self.assertEqual(f.read_text(),'{"original":true}')
            f.write_text('{"original":false}');self.assertNotEqual(first,a.manifest(p))
    def test_missing_vs_irrelevant_sources(self):
        m={'retrieved_candidates':0,'retained_sources':0,'original_limitation_codes':[], 'inaccessible_source_count':0,'conflict_groups':0,'synthesis_claims_omitted':0,'full_text_sources':0,'selected_claims':0}
        self.assertEqual(a.Audit.initial_cause(None,m),['missing_sources'])
        m['retrieved_candidates']=8
        self.assertEqual(a.Audit.initial_cause(None,m),['weak_geographic_or_company_relevance'])
if __name__=='__main__':unittest.main()
