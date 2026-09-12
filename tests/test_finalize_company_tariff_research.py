import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import finalize_company_tariff_research as f

class ReviewedCompanyTests(unittest.TestCase):
    def evidence(self,scope='company_name_matches_cached_evidence'):
        return {'company_name':'Example Corp.','source_url':'https://example.org','evidence_scope':scope,'statement':'Example Corp reports costs.'}
    def test_group_context_is_never_promoted_by_company_effect_label(self):
        r=f.classify_relationship(self.evidence('potential_company_or_group_context'),{'kind':'named_company_tariff_effect','reason':'Parent reports tariff costs.'})
        self.assertFalse(r['supports_named_company_tariff_assertion']);self.assertFalse(r['company_identity_verified']);self.assertEqual(r['facility_applicability'],'not_established')
    def test_operating_context_does_not_count_as_tariff_assertion(self):
        r=f.classify_relationship(self.evidence(),{'kind':'company_operations_context','reason':'Factory opened.'})
        self.assertFalse(r['supports_named_company_tariff_assertion'])
    def test_manual_review_overrides_model_and_preserves_original(self):
        e=self.evidence();r=f.classify_relationship(e,{'kind':'named_company_tariff_effect'}, {'kind':'company_tariff_response_or_opinion','identity_assessment':'group_context_only','reason':'An attributed parent-company forecast.'})
        self.assertEqual(r['reviewed_kind'],'company_tariff_response_or_opinion');self.assertFalse(r['supports_named_company_tariff_assertion']);self.assertNotIn('reviewed_kind',e)
    def test_wrong_morgan_entity_is_rejected(self):
        e=self.evidence();e.update(company_name='Morgan Corp.',source_url='https://morgan-motor-usa.com/tariffs')
        r=f.classify_relationship(e,{'kind':'named_company_tariff_effect'})
        self.assertEqual(r['reviewed_identity_scope'],'rejected_wrong_company');self.assertFalse(r['supports_named_company_tariff_assertion'])
    def test_source_reported_effect_still_does_not_verify_current_law(self):
        r=f.classify_relationship(self.evidence(),{'kind':'named_company_tariff_effect'})
        self.assertTrue(r['supports_named_company_tariff_assertion']);self.assertEqual(r['current_legal_applicability'],'not_established')

if __name__=='__main__':unittest.main()
