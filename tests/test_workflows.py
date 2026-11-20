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
