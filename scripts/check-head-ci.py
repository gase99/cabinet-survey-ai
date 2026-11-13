"""Read-only acceptance evidence collector; fails for stale/missing/incomplete checks."""
import json
import subprocess
import sys
from pathlib import Path

def gh(*args):return json.loads(subprocess.check_output(['gh',*args],text=True))
pr=gh('api','repos/gase99/cabinet-survey-ai/pulls/1')
sha=pr['head']['sha']
checks=gh('api',f'repos/gase99/cabinet-survey-ai/commits/{sha}/check-runs?per_page=100')['check_runs']
required={'backend-ci':{'test','postgres-migration'},'worker-ci':{'test'},'client-ci':{'flutter'}}
runs=gh('api',f'repos/gase99/cabinet-survey-ai/actions/runs?head_sha={sha}&per_page=100')['workflow_runs']
results=[]
for workflow,jobs in required.items():
    matching=sorted([r for r in runs if r['name']==workflow and r['head_sha']==sha],key=lambda r:r['id'],reverse=True)
    if not matching:
        results.append({'workflow':workflow,'sha':sha,'status':'NOT TESTED','reason':'No exact-head run'});continue
    run=matching[0]
    actual=gh('api',f"repos/gase99/cabinet-survey-ai/actions/runs/{run['id']}/jobs?per_page=100")['jobs']
    for job in jobs:
        found=[j for j in actual if j['name']==job]
        item=found[0] if found else {}
        ok=run['status']=='completed' and item.get('conclusion')=='success'
        results.append({'workflow':workflow,'job':job,'sha':sha,'status':'PASS' if ok else ('FAIL' if item.get('conclusion') in {'failure','cancelled','timed_out'} else 'NOT TESTED'),
                        'conclusion':item.get('conclusion'),'url':item.get('html_url',run['html_url']),'run_id':run['id']})
report={'pr':1,'head_sha':sha,'checks':results,
        'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL'}
text=json.dumps(report,indent=2)+'\n'
if len(sys.argv)>1:Path(sys.argv[1]).write_text(text)
print(text)
sys.exit(0 if report['status']=='PASS' else 1)
