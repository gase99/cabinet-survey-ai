"""Read-only exact-current-HEAD CI evidence. Never substitutes an old PR/run."""
import json
import subprocess
import sys
from pathlib import Path


def gh(*args):
    return json.loads(subprocess.check_output(['gh', *args], text=True))


def collect(repo):
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    runs = gh('api', f'repos/{repo}/actions/runs?head_sha={sha}&per_page=100')['workflow_runs']
    required = {'backend-ci': {'test', 'postgres-migration'}, 'worker-ci': {'test'},
                'android-ci': {'flutter-android', 'android-emulator'}}
    results = []
    for workflow, jobs in required.items():
        matching = sorted((r for r in runs if r['name'] == workflow and r['head_sha'] == sha),
                          key=lambda r: r['id'], reverse=True)
        if not matching:
            results.append({'workflow': workflow, 'sha': sha, 'status': 'NOT TESTED', 'reason': 'No exact-head run'})
            continue
        run = matching[0]
        actual = gh('api', f'repos/{repo}/actions/runs/{run["id"]}/jobs?per_page=100')['jobs']
        for job in jobs:
            found = next((j for j in actual if j['name'] == job), {})
            ok = run['status'] == 'completed' and run['conclusion'] == 'success' and found.get('conclusion') == 'success'
            results.append({'workflow': workflow, 'job': job, 'sha': sha,
                'status': 'PASS' if ok else ('FAIL' if found.get('conclusion') in {'failure', 'cancelled', 'timed_out'} else 'NOT TESTED'),
                'conclusion': found.get('conclusion'), 'url': found.get('html_url', run['html_url']), 'run_id': run['id']})
    return {'branch': subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
            'head_sha': sha, 'checks': results, 'status': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL'}


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else 'gase99/cabinet-survey-ai'
    report = collect(repo)
    text = json.dumps(report, indent=2)+'\n'
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text)
    print(text)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
