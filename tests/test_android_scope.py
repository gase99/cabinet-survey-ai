"""Structural release gates runnable without Flutter/Android SDK; not build evidence."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'apps/client'
ANDROID = '{http://schemas.android.com/apk/res/android}'


def test_web_target_is_not_built_or_shipped():
    assert not (CLIENT / 'web').exists()
    assert not (ROOT / 'scripts/browser_acceptance.py').exists()
    assert not (ROOT / 'scripts/bootstrap-client.sh').exists()
    pubspec = (CLIENT / 'pubspec.yaml').read_text()
    assert 'sqflite_common_ffi_web' not in pubspec
    assert 'file_saver' not in pubspec
    for path in (CLIENT / 'lib').rglob('*.dart'):
        text = path.read_text()
        assert 'dart:html' not in text and 'package:web/' not in text
        assert 'kIsWeb' not in text and 'sqflite_common_ffi_web' not in text
    workflow = (ROOT / '.github/workflows/client-ci.yml').read_text()
    assert 'flutter build web' not in workflow and '--platform chrome' not in workflow
    assert 'build/web' not in (ROOT / 'deploy/compose.yml').read_text()


def test_android_sources_manifest_and_wrapper_are_committed():
    for name in ['settings.gradle.kts', 'build.gradle.kts', 'gradlew', 'gradle/wrapper/gradle-wrapper.jar',
                 'app/build.gradle.kts', 'app/src/main/AndroidManifest.xml']:
        assert (CLIENT / 'android' / name).is_file()
    manifest = ET.parse(CLIENT / 'android/app/src/main/AndroidManifest.xml').getroot()
    permissions = {node.attrib[ANDROID+'name'] for node in manifest.findall('uses-permission')}
    assert permissions == {'android.permission.INTERNET'}
    application = manifest.find('application')
    assert application.attrib[ANDROID+'allowBackup'] == 'false'
    assert application.attrib[ANDROID+'usesCleartextTraffic'] == 'false'
    assert application.attrib[ANDROID+'supportsRtl'] == 'true'
    assert application.find('activity').attrib[ANDROID+'exported'] == 'true'
    release_net = ET.parse(CLIENT / 'android/app/src/main/res/xml/network_security_config.xml').getroot()
    assert release_net.find('base-config').attrib['cleartextTrafficPermitted'] == 'false'
    assert not release_net.findall('domain-config')
    for variant in ['debug', 'profile']:
        config = ET.parse(CLIENT / f'android/app/src/{variant}/res/xml/network_security_config.xml').getroot()
        for domain in config.findall('domain-config'):
            domains = domain.findall('domain')
            assert {node.text for node in domains} == {'10.0.2.2', 'localhost', '127.0.0.1'}
            assert all(node.attrib['includeSubdomains'] == 'false' for node in domains)
    wrapper = CLIENT / 'android/gradle/wrapper/gradle-wrapper.jar'
    assert wrapper.read_bytes()[:2] == b'PK'
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == '2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046'
    properties = (CLIENT / 'android/gradle/wrapper/gradle-wrapper.properties').read_text()
    assert 'gradle-8.12-all.zip' in properties


def test_release_never_falls_back_to_debug_signing():
    gradle = (CLIENT / 'android/app/build.gradle.kts').read_text()
    assert 'signingConfig = signingConfigs.getByName("debug")' not in gradle
    assert 'if (hasReleaseSigning) signingConfig' in gradle
    assert 'minSdk = 24' in gradle and 'targetSdk = 36' in gradle
    rules = (CLIENT / 'android/app/proguard-rules.pro').read_text()
    assert '-dontwarn com.google.android.play.core.**' in rules
    assert '-ignorewarnings' not in rules
    example = (CLIENT / 'android/key.properties.example').read_text()
    assert 'storePassword=REPLACE_LOCALLY' in example
    assert 'keyPassword=REPLACE_LOCALLY' in example
    assert not (CLIENT / 'android/key.properties').exists()
    ignored = (ROOT / '.gitignore').read_text()
    assert 'apps/client/android/key.properties' in ignored
    assert '*.jks' in ignored and '*.keystore' in ignored
    assert not list((CLIENT / 'android').rglob('*.jks'))
    assert not list((CLIENT / 'android').rglob('*.keystore'))
    workflow = (ROOT / '.github/workflows/client-ci.yml').read_text()
    assert 'flutter build apk --debug' in workflow
    assert 'flutter build appbundle --release' in workflow
    assert 'secrets.ANDROID_KEYSTORE_BASE64' in workflow


def test_android_launcher_icons_and_localized_app_names_are_committed():
    res = CLIENT / 'android/app/src/main/res'
    for density in ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']:
        icon = res / f'mipmap-{density}/ic_launcher.png'
        assert icon.is_file(), f'Missing launcher icon for {density}'
        assert icon.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
    assert (res / 'mipmap-anydpi-v26/ic_launcher.xml').is_file()
    assert (res / 'drawable/ic_survey.xml').is_file()
    assert (res / 'values/strings.xml').is_file()
    assert (res / 'values-fa/strings.xml').is_file()


def test_python_lockfiles_and_static_analysis_gates_are_enforced():
    for rel in [
        'backend/requirements.lock',
        'backend/requirements-dev.lock',
        'services/telegram-bot/requirements.lock',
    ]:
        lock = ROOT / rel
        assert lock.is_file(), f'Missing lockfile {rel}'
        pinned = [
            line for line in lock.read_text().splitlines()
            if line and not line.startswith('#') and not line.startswith(' ')
        ]
        assert pinned and all('==' in line for line in pinned), f'Unpinned entry in {rel}'
    assert 'COPY requirements.lock .' in (ROOT / 'backend/Dockerfile').read_text()
    assert 'COPY requirements.lock .' in (ROOT / 'services/telegram-bot/Dockerfile').read_text()
    backend_ci = (ROOT / '.github/workflows/backend-ci.yml').read_text()
    assert 'backend/requirements.lock' in backend_ci
    assert 'backend/requirements-dev.lock' in backend_ci
    assert 'ruff check app migrations tests' in backend_ci
    assert 'mypy app migrations tests' in backend_ci
    worker_ci = (ROOT / '.github/workflows/worker-ci.yml').read_text()
    assert 'pip install -r requirements.lock' in worker_ci


def test_phase_gate_and_telegram_single_replica_docs_are_consistent():
    agents = (ROOT / 'AGENTS.md').read_text()
    roadmap = (ROOT / 'docs/development-roadmap.md').read_text()
    assert 'stop for explicit user approval at phase boundaries' in agents
    assert 'stop for explicit user approval at every phase boundary' in roadmap
    tg_doc = (ROOT / 'docs/telegram-deployment.md').read_text()
    ops_doc = (ROOT / 'docs/operations.md').read_text()
    worker_readme = (ROOT / 'services/telegram-bot/README.md').read_text()
    compose = yaml.safe_load((ROOT / 'deploy/compose.yml').read_text()) if 'yaml' in globals() else None
    assert 'POST /webhook' in tg_doc and 'exactly one replica' in tg_doc
    assert 'long polling is **not**\n  implemented' in tg_doc or 'long polling is **not** implemented' in tg_doc
    assert 'single replica (`1`)' in ops_doc
    assert 'Strictly one replica (`1`)' in worker_readme
    compose_text = (ROOT / 'deploy/compose.yml').read_text()
    assert 'replicas: 1' in compose_text


def test_three_telegram_credentials_remain_distinct():
    env = dict(line.split('=', 1) for line in (ROOT / '.env.example').read_text().splitlines()
               if line and not line.startswith('#') and '=' in line)
    keys = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'TELEGRAM_WORKER_SECRET']
    assert all(key in env for key in keys)
    compose = (ROOT / 'deploy/compose.yml').read_text()
    assert 'BACKEND_WORKER_SECRET: ${TELEGRAM_WORKER_SECRET:?' in compose
    assert 'TELEGRAM_WEBHOOK_SECRET: ${TELEGRAM_WEBHOOK_SECRET:?' in compose
    gateway = (ROOT / 'deploy/gateway.conf').read_text()
    assert 'location ^~ /api/v1/telegram/internal/ { return 404; }' in gateway
    assert 'location = /telegram/webhook' in gateway
    assert 'try_files' not in gateway and 'root /usr/share' not in gateway


def test_flutter_client_uses_sync_as_sole_domain_write_path():
    for path in (CLIENT / 'lib').rglob('*.dart'):
        text = path.read_text()
        assert not re.search(r"request\(\s*['\"]PUT['\"]", text), f"Direct REST PUT found in {path}"
        assert not re.search(r"request\(\s*['\"]DELETE['\"]", text), f"Direct REST DELETE found in {path}"
    sync_doc = (ROOT / 'docs/offline-sync.md').read_text()
    assert 'POST /api/v1/sync/push' in sync_doc and 'only' in sync_doc

