"""Read Tavily key/account credit balances without exposing credentials or searching."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parent))
from research_tariffs import ROOT, dump, load_env, parse_queries, sid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and value >= 0 else None


def remaining(limit, used):
    limit, used = number(limit), number(used)
    return max(0,limit-used) if limit is not None and used is not None else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/tariffs/credit-check')
    args=parser.parse_args()
    load_env(args.env_file)
    keys=list(dict.fromkeys(k.strip() for k in (os.getenv('TAVILY_API_KEYS') or os.getenv('TAVILY_API_KEY') or '').split(',') if k.strip()))
    if not keys: raise SystemExit('No Tavily credentials configured')
    opener=urllib.request.build_opener(NoRedirect())
    rows=[]
    usage_cooldown=False
    for index,key in enumerate(keys,1):
        row=dict(key_number=index,key_id=sid('key',key),checked_at=datetime.now(timezone.utc).isoformat())
        if usage_cooldown:
            row.update(status='deferred_rate_limit')
            rows.append(row)
            continue
        req=urllib.request.Request('https://api.tavily.com/usage',headers={'Authorization':'Bearer '+key})
        try:
            with opener.open(req,timeout=30) as response: data=json.load(response)
            k,a=data['key'],data['account']
            row.update(status='ok',key_usage=number(k.get('usage')),key_limit=number(k.get('limit')),
                key_remaining=remaining(k.get('limit'),k.get('usage')),
                account_plan=a.get('current_plan'),account_plan_usage=number(a.get('plan_usage')),
                account_plan_limit=number(a.get('plan_limit')),
                account_plan_remaining=remaining(a.get('plan_limit'),a.get('plan_usage')),
                account_paygo_usage=number(a.get('paygo_usage')),account_paygo_limit=number(a.get('paygo_limit')),
                account_paygo_remaining=remaining(a.get('paygo_limit'),a.get('paygo_usage')))
            # No account identifier is supplied: identical balance snapshots cannot
            # prove that keys share an account or belong to separate accounts.
            caps=[v for v in [row['key_remaining'],row['account_plan_remaining']] if v is not None]
            row['plan_credits_accessible_via_key']=min(caps) if row['account_plan_remaining'] is not None and caps else None
        except urllib.error.HTTPError as e:
            row.update(status='http_error',http_status=e.code)
            # No body logging: error responses could echo credentials.
            if e.code==429:
                # The usage endpoint may limit the client/IP across keys. Stop
                # the batch rather than treating another key as a workaround.
                usage_cooldown=True
                row['retry_after']=e.headers.get('Retry-After')
        except Exception as e:
            row.update(status='error',error_type=type(e).__name__)
        rows.append(row)
        print(json.dumps(row),flush=True)
        dump(args.out/'keys.json',rows)
        if index<len(keys): time.sleep(5)
    dump(args.out/'keys.json',rows)
    queries,counts=parse_queries(ROOT/'data/tariffs/queries.txt')
    balances=[r['plan_credits_accessible_via_key'] for r in rows if r['status']=='ok' and r.get('plan_credits_accessible_via_key') is not None]
    count=len(queries)
    summary=dict(checked_at=datetime.now(timezone.utc).isoformat(),configured_keys=len(keys),
        successful_usage_checks=sum(r['status']=='ok' for r in rows),
        failed_usage_checks=sum(r['status']!='ok' for r in rows),
        largest_confirmed_single_key_plan_balance=max(balances) if balances else None,
        sum_of_per_key_accessible_balances=sum(balances) if balances else None,
        independent_account_total_verified=False,
        account_limit_note='Do not treat the per-key sum as a verified pool total; /usage supplies balances but no account identity. Keys on one account share that account balance.',
        baseline_queries=count,basic_search_credits=count,advanced_search_credits=2*count,
        basic_with_two_transient_retries_each=3*count,
        basic_with_two_transient_retries_and_all_but_one_key_failover=3*count+len(keys)-1,
        paid_extract_enabled=False,search_requests_made=0,
        provider_usage_docs='https://docs.tavily.com/documentation/api-reference/endpoint/usage',
        provider_pricing_docs='https://docs.tavily.com/documentation/api-credits')
    dump(args.out/'summary.json',summary)
    lines=['# Tavily credit check','',f"Checked: {summary['checked_at']}",'',
           '| Key number | Status | Key credits remaining | Account plan credits remaining |',
           '| --- | --- | --- | --- |']
    for r in rows:
        lines.append(f"| {r['key_number']} | {r['status']} | {r.get('key_remaining','unknown')} | {r.get('account_plan_remaining','unknown')} |")
    lines+=['',summary['account_limit_note'],'',
            f'Basic baseline: {count} credits. Advanced baseline: {2*count} credits.',
            f'Two transient retries for every basic query: {3*count} estimated credits; up to {len(keys)-1} additional failed-key reservations can also occur.',
            'Paid extraction is off. This check submitted no searches. Existing run limits were not changed.','']
    (args.out/'report.md').write_text('\n'.join(lines))
    print(json.dumps({'summary':summary},indent=2),flush=True)


if __name__=='__main__': main()
