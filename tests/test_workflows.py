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
