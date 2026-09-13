from pathlib import Path
import datetime, json, os, subprocess
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
python=root/'outputs/tariffs/runtime-venv/bin/python'
cmd=[str(python),'-u',str(root/'scripts/research_tariffs.py'),'--out',str(out),'--max-queries','510','--max-credits','700','--retry-failed']
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
record={'status':'running','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'passes':[],'credit_ceiling':700}
def save():
    (out/'full-bank-execution.json').write_text(json.dumps(record,indent=2)+'\n')
save()
for attempt in range(1,4):
    with (out/f'full-bank-pass-{attempt}.log').open('a') as log:
        result=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    record['passes'].append({'pass':attempt,'exit_code':result.returncode,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save()
    if result.returncode==0 or result.returncode!=3:
        break
    summary=json.loads((out/'summary.json').read_text())
    if summary['usage']['budget_accounted_credits']>=700:
        break
    if attempt<3:
        import time
        time.sleep(60)
with (out/'audit.json').open('w') as report:
    check=subprocess.run([str(python),str(root/'scripts/audit_tariff_corpus.py'),str(out)],cwd=root,env=env,stdout=report,stderr=subprocess.STDOUT)
record.update(status='completed' if result.returncode==0 and check.returncode==0 else 'needs_attention',audit_exit_code=check.returncode,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
save()
