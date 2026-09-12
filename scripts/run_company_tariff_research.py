"""Run the approved company tariff plan with one cumulative 500-credit ledger."""
from __future__ import annotations
import json,os,sqlite3,subprocess,sys,time
from pathlib import Path
import research_tariffs as t
import research_company_tariffs as c
ROOT=c.ROOT;OUT=c.OUT;WEB=OUT/'web-run';PYTHON=sys.executable

def snapshot():
    result={'updated_at':t.now(),'credit_cap':500}
    if (WEB/'corpus.sqlite').exists():
        db=sqlite3.connect((WEB/'corpus.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        result['record_counts']={kind:n for kind,n in db.execute('SELECT kind,COUNT(*) FROM records GROUP BY kind')}
        n,estimated,reported=db.execute('SELECT COUNT(*),SUM(estimated),SUM(reported) FROM requests').fetchone();result['usage']={'attempts':n,'estimated':estimated or 0,'reported':reported or 0};db.close()
    return result

def export_profiles():
    with (OUT/'profile-export.log').open('a') as log:
        proc=subprocess.run([PYTHON,str(ROOT/'scripts/build_company_tariff_profiles.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if proc.returncode:raise RuntimeError('Company profile export failed; inspect profile-export.log')

def stage(name,limit,selection=None):
    args=[PYTHON,str(ROOT/'scripts/research_tariffs.py'),'--queries',str(OUT/'company_queries.csv'),'--out',str(WEB),'--max-queries',str(limit),'--max-credits','500','--search-depth','basic','--paid-extract','off','--concurrency','2','--keep-per-query','3','--max-chunks-per-document','6','--num-ctx','32768','--num-predict','6000','--model','qwen3.5:35b-a3b','--ollama-url','http://localhost:11434','--research-date','2026-09-10','--model-timeout','300','--retry-failed']
    if selection:args+=['--query-ids-file',str(selection)]
    for attempt in range(1,4):
        with (OUT/f'{name}-pass-{attempt}.log').open('a') as log:
            proc=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            t.dump(OUT/'active-process.json',{'stage':name,'attempt':attempt,'pid':proc.pid,'supervisor_pid':os.getpid(),'started_at':t.now(),'command':args,'approved_credit_cap':500})
            last_export=time.monotonic()
            while proc.poll() is None:
                state=snapshot();state.update(stage=name,attempt=attempt,pid=proc.pid,status='running');t.dump(OUT/'execution_progress.json',state)
                if time.monotonic()-last_export>300:
                    export_profiles();last_export=time.monotonic()
                time.sleep(10)
        export_profiles();state=snapshot();state.update(stage=name,attempt=attempt,returncode=proc.returncode);t.dump(OUT/'execution_progress.json',state)
        # Count actual query states, not a process's exit status alone.
        db=sqlite3.connect((WEB/'corpus.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        states=[json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind='query_state'")];db.close()
        wanted=set(selection.read_text().split()) if selection else {r['query_id'] for r in t.parse_queries(OUT/'company_queries.csv')[0]}
        complete={r['query_id'] for r in states if r['status'] in {'complete','insufficient_evidence'}}
        if wanted<=complete:return
        if state.get('usage',{}).get('estimated',0)>=500:raise RuntimeError('Approved credit ceiling reached; remaining work preserved for review')
    raise RuntimeError('Three resumable attempts left incomplete queries; inspect per-query failures')

def main():
    plan=json.loads((OUT/'research_plan.json').read_text())
    if not plan.get('full_run_budget_approved') or plan.get('approved_cumulative_credit_cap')!=500:raise ValueError('Full company budget not approved')
    # This stage begins only after cached cleanup completes and preserves its inputs.
    cleanup=ROOT/'outputs/tariffs/quality-audit-v2-2026-09-10/summary.json'
    while not cleanup.exists():
        t.dump(OUT/'execution_progress.json',{'stage':'waiting_for_cached_cleanup','updated_at':t.now(),'approved_credit_cap':500});time.sleep(10)
    export_profiles();stage('primary-policy',20,OUT/'initial_policy_query_ids.txt');stage('all-companies',plan['planned_queries_total']);export_profiles()
    state=snapshot();state.update(status='collection_complete_with_evidence_gaps',completed_at=t.now());t.dump(OUT/'execution_progress.json',state)
    t.dump(OUT/'active-process.json',{'stage':'complete','supervisor_pid':os.getpid(),'completed_at':t.now()})
    print(json.dumps(state,indent=2),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        t.dump(OUT/'execution_error.json',{'timestamp':t.now(),'error_type':type(e).__name__,'error':str(e),'progress':snapshot()});raise
