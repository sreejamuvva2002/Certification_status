"""Prepare traceable company tariff research; seed labels never establish exposure."""
from __future__ import annotations
import argparse,collections,csv,json,re,sqlite3
from pathlib import Path
import openpyxl
import audit_tariff_quality as a
import research_tariffs as t
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/tariffs/pilot-2026-09-09'
V1=ROOT/'outputs/tariffs/quality-audit-v1-2026-09-10'
OUT=ROOT/'outputs/tariffs/company-research-2026-09-10'
POLICY_DOMAINS=['cbp.gov','federalregister.gov','ustr.gov','usitc.gov','trade.gov']

def normalize_name(name):
    words=re.findall(r'[a-z0-9]+',name.casefold())
    suffixes={'inc','incorporated','llc','corp','corporation','co','company','lp','ltd','limited'}
    while words and words[-1] in suffixes:words.pop()
    return ' '.join(words)

def load_roster(path):
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True);sheet=wb.active;rows=iter(sheet.values);headers=next(rows);companies={};seed=[]
    city_county=json.loads((ROOT/'data/ga_city_county.json').read_text())
    for rownum,values in enumerate(rows,2):
        row={str(k):v for k,v in zip(headers,values) if k};name=str(row.get('Company') or '').strip()
        if not name:continue
        ident=t.sid('company',name.casefold());sid=f'gnem_row_{rownum}'
        r={'seed_row_id':sid,'worksheet_row':rownum,'company_id':ident,'source_sheet':sheet.title,'seed':row,'seed_fields_verified':False,'issues':[]}
        location=str(row.get('Location') or '');parts=location.split(',');city=parts[0].strip().casefold();county=parts[-1].replace('County','').strip() if len(parts)>1 else ''
        expected=city_county.get(city)
        if expected and county and county not in expected.split('/'):r['issues'].append({'type':'city_county_disagreement_with_local_reference','provided_county':county,'local_reference_county':expected,'action':'verify_external_source; do not overwrite seed'})
        if not location:r['issues'].append({'type':'missing_seed_location'})
        seed.append(r)
        c=companies.setdefault(ident,{'company_id':ident,'company_name':name,'search_aliases':[name,normalize_name(name)],'seed_row_ids':[],'seed_locations':[],'seed_products':[],'seed_industries':[],'identity_verified':False,'facility_exposure_verified':False})
        c['seed_row_ids'].append(sid)
        for key,col in [('seed_locations','Location'),('seed_products','Product / Service'),('seed_industries','Industry Group')]:
            value=str(row.get(col) or '').strip()
            if value and value not in c[key]:c[key].append(value)
    return list(companies.values()),seed

def prepare(out=OUT):
    out.mkdir(parents=True,exist_ok=True);lex=json.loads((ROOT/'data/tariffs/targeted_terms.json').read_text());companies,seeds=load_roster(ROOT/'data/GNEM_Excel_Data.xlsx')
    # Sector labels are discovery hints only; always preserve full original row evidence.
    for c in companies:
        hints=' '.join(c['seed_industries'])
        c['sector_hints']=[s for s,terms in lex['sectors'].items() if any(a.matches(term,hints) for term in terms)] or ['automotive_and_trade']
        if 'Primary Metal' in hints or 'Fabricated Metal' in hints:c['sector_hints']=sorted(set(c['sector_hints']+['metals']))
        if 'Electronic' in hints:c['sector_hints']=sorted(set(c['sector_hints']+['pcbs_and_electronics','displays']))
        if any(a.matches(term,c['company_name']) for term in ['Battery','Enchem','Anovion','SungEel','Ascend Elements','LG Energy']):c['sector_hints']=sorted(set(c['sector_hints']+['batteries_and_minerals']))
        c['southeast_georgia_seed_hint']=any(a.matches(term,' '.join(c['seed_locations'])) for term in lex['geography_terms'] if term not in ['Georgia','Southeast Georgia'])
    companies.sort(key=lambda c:(not c['southeast_georgia_seed_hint'],c['company_name'].casefold()))
    queryrows=[]
    for c in companies:
        sectorwords={'automotive_and_trade':'automotive vehicles auto parts','metals':'steel aluminum copper tariffs','batteries_and_minerals':'batteries critical minerals lithium graphite','pcbs_and_electronics':'PCBs printed circuit boards electronics','displays':'LCD OLED displays'}
        product_terms=' '.join(sectorwords[s] for s in c['sector_hints'])
        for stage,query in [('discovery',f'"{c["company_name"]}" Georgia tariffs import duties supply chain'),('targeted',f'"{c["company_name"]}" {product_terms} tariffs cost sourcing country of origin 2026')]:
            queryrows.append({'id':c['company_id']+'_'+stage,'query':query,'company_id':c['company_id'],'company_name':c['company_name'],'company_aliases':c['search_aliases'],'seed_row_ids':c['seed_row_ids'],'query_purpose':'company_'+stage,'sector_terms':product_terms,'reason':'Collect company-named evidence; seed product/location labels are unverified.','parent_query_ids':[],'include_domains':[]})
    for sector,words in {'automotive_and_trade':'automobiles auto parts Section 232','metals':'steel aluminum copper derivatives Section 232','batteries_and_minerals':'batteries graphite critical minerals Section 301','pcbs_and_electronics':'printed circuit boards PCB Section 301 exclusions','displays':'LCD OLED display modules HTS classification Section 301'}.items():
        for focus in ['effective date status 2026','country of origin exemptions exclusions','HTS Chapter 99 product scope','duty stacking valuation rates']:
            queryrows.append({'id':t.sid('policyquery',sector,focus),'query':words+' '+focus,'company_id':'','company_name':'','company_aliases':[],'seed_row_ids':[],'query_purpose':'shared_policy_verification','sector_terms':words,'reason':'Primary-authority verification shared across company dossiers; applicability must be established separately.','parent_query_ids':[],'include_domains':POLICY_DOMAINS})
    a.write_jsonl(out/'companies.jsonl',companies);a.write_jsonl(out/'seed_rows.jsonl',seeds);a.write_csv(out/'company_inventory.csv',companies);a.write_csv(out/'seed_quality_issues.csv',[s for s in seeds if s['issues']]);a.write_csv(out/'company_queries.csv',queryrows)
    # Initial 20 queries: prioritize unresolved policy verification, before company web research.
    pilot=[r for r in queryrows if r['query_purpose']=='shared_policy_verification']
    (out/'initial_policy_query_ids.txt').write_text(''.join('q_'+r['id']+'\n' for r in pilot))
    plan={'created_at':t.now(),'seed_workbook_rows':len(seeds),'distinct_company_names':len(companies),'duplicate_name_rows_preserved':len(seeds)-len(companies),'seed_rows_with_location_issues':sum(bool(s['issues']) for s in seeds),'planned_company_queries':len(companies)*2,'shared_policy_queries':len(pilot),'planned_queries_total':len(queryrows),'basic_search_credits_without_retries':len(queryrows),'proposed_cumulative_credit_cap':500,'initial_authorized_query_limit':20,'initial_credit_cap':100,'full_run_budget_approved':False,'paid_extraction':'off','pricing_documentation':'https://docs.tavily.com/documentation/api-credits','pricing_checked_on':'2026-09-10','all_five_sector_terms':lex['sectors'],'sequence':['local_cleanup','initial_primary_policy_verification','company_discovery_and_targeted_queries','company_evidence_profiles'],'company_roster_basis':'193 exact case-insensitive names; similar names are not merged automatically.'}
    prior_plan=out/'research_plan.json'
    if prior_plan.exists():
        previous=json.loads(prior_plan.read_text())
        for key in ['full_run_budget_approved','approved_cumulative_credit_cap','approval_source','approval_date']:
            if key in previous:plan[key]=previous[key]
    t.dump(out/'research_plan.json',plan)
    (out/'research_plan.md').write_text(f'''# Company tariff research plan\n\nThe workbook has {len(seeds)} populated company rows and {len(companies)} distinct names. All rows and duplicate names are preserved. Seed locations, products, EV roles, and affiliations require verification.\n\nThe reviewable [query bank](company_queries.csv) contains {len(queryrows)} queries: two per company plus 20 shared policy checks across automotive, metals, batteries/critical minerals, PCBs/electronics, and displays. Names and sector hints guide discovery; they do not establish exposure. [Company inventory](company_inventory.csv).\n\nSequence: finish local cleanup; execute the initial 20 primary-authority queries; then research every company and attach verified source quotations and unresolved gaps to each profile. Basic searches cost one credit according to [Tavily documentation](https://docs.tavily.com/documentation/api-credits), checked September 10, 2026. The proposed full-run ceiling is 500 credits including the initial 20, remaining searches and retries. Paid extraction remains off. Until the full budget is approved, the existing brief limits work to the initial 20-query pilot within its 100-credit ceiling.\n\nEach company profile will separate company-named statements, group-level context, facility evidence, sector policy, and unsupported applicability. No exact duty rate, HTS classification, origin or duty stacking is inferred from a generic product label. A searched company with no usable evidence receives an explicit gap record.\n''')
    return plan

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=OUT);args=p.parse_args();print(json.dumps(prepare(args.out),indent=2))
