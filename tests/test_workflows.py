"""Parse all GitHub workflow YAML before a colon in a label breaks Actions."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_workflows_parse_and_android_jobs_are_required():
    documents = {p.name: yaml.safe_load(p.read_text()) for p in (ROOT / '.github/workflows').glob('*.yml')}
    assert all(isinstance(document, dict) and 'jobs' in document for document in documents.values())
    android = documents['client-ci.yml']
    assert android['name'] == 'android-ci'
    assert set(android['jobs']) == {'flutter-android', 'android-emulator'}
    for document in documents.values():
        assert document['permissions'] == {'contents': 'read'}


def test_personal_apk_dispatch_uses_app_validator_and_no_secrets():
    workflow = (ROOT / '.github/workflows/personal-debug-apk.yml').read_text()
    assert 'workflow_dispatch:' in workflow
    assert "default: 'http://127.0.0.1:8000/api/v1/'" in workflow
    assert 'dispatch_api_url_test.dart' in workflow
    assert '--dart-define=DISPATCH_VALIDATE=true' in workflow
    assert '--dart-define="API_BASE_URL=$API_URL"' in workflow
    assert 'actions/upload-artifact@v4' in workflow
    assert 'secrets.' not in workflow
    validator_test = (ROOT / 'apps/client/test/dispatch_api_url_test.dart').read_text()
    assert 'validateApiBase(supplied, release: false)' in validator_test


def test_emulator_failure_artifact_upload_runs_after_device_script():
    workflow = yaml.safe_load((ROOT / '.github/workflows/client-ci.yml').read_text())
    job = workflow['jobs']['android-emulator']
    steps = job['steps']
    runner_index = next(i for i, step in enumerate(steps) if step.get('uses') == 'reactivecircus/android-emulator-runner@v2')
    artifact_index = next(i for i, step in enumerate(steps) if step.get('name') == 'Upload emulator failure diagnostics')
    artifact = steps[artifact_index]
    assert runner_index < artifact_index
    assert artifact['if'] == 'always()'
    assert artifact['uses'] == 'actions/upload-artifact@v4'
    assert artifact['with']['path'] == '${{ runner.temp }}/emulator-diagnostics/'
    assert 'scripts/android-emulator-smoke.sh' in steps[runner_index]['with']['script']
