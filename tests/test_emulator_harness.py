"""Exercise the CI shell harness with fake Flutter/adb; no emulator is claimed."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'scripts/android-emulator-smoke.sh'


@pytest.fixture
def harness(tmp_path):
    sdk = tmp_path / 'sdk'
    platform = sdk / 'platform-tools'
    platform.mkdir(parents=True)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    temp = tmp_path / 'runner-temp'
    temp.mkdir()
    trace = tmp_path / 'trace'
    adb = platform / 'adb'
    adb.write_text('''#!/usr/bin/env python3
import os, sys
with open(os.environ['TRACE'], 'a') as f:
    f.write('adb ' + ' '.join(sys.argv[1:]) + '\\n')
if 'screencap' in sys.argv:
    if os.environ['SCENARIO'] == 'screenshot_failure':
        sys.exit(1)
    sys.stdout.buffer.write(b'fake png')
elif 'dumpsys' in sys.argv:
    print('activity crash diagnostics fixture')
elif 'logcat' in sys.argv:
    print('logcat fixture')
''')
    flutter = bin_dir / 'flutter'
    flutter.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['TRACE'], 'a') as f:
    f.write('flutter ' + ' '.join(args) + '\\n')
mode = os.environ['SCENARIO']
if args[0] == 'doctor':
    sys.exit(0)
if 'integration_test/local_encryption_test.dart' in args:
    sys.exit(4 if mode == 'encryption_failure' else 0)
phase = 'reopen' if '--dart-define=VERIFY_REOPEN=true' in args else 'capture'
count_file = Path(os.environ['RUNNER_TEMP']) / ('count-' + phase)
count = int(count_file.read_text()) + 1 if count_file.exists() else 1
count_file.write_text(str(count))
print('00:00 +0: loading integration_test/android_smoke_test.dart')
if mode in ('dds', 'dds_twice', 'reopen_dds', 'both_dds', 'screenshot_failure') and (mode == 'both_dds' or phase == ('reopen' if mode == 'reopen_dds' else 'capture')) and (count == 1 or mode in ('dds_twice', 'screenshot_failure')):
    print('Failed to start Dart Development Service')
    sys.exit(1)
if mode == 'timeout' and phase == 'capture' and count == 1:
    sys.exit(124)
if mode == 'test_failure' and phase == 'capture':
    print('Android Persian RTL offline capture and process restart')
    print('Failed to start Dart Development Service')
    sys.exit(1)
print('Android Persian RTL offline capture and process restart')
''')
    adb.chmod(0o755)
    flutter.chmod(0o755)

    def run(scenario):
        env = os.environ.copy()
        env.update(ANDROID_HOME=str(sdk), RUNNER_TEMP=str(temp), TRACE=str(trace),
                   SCENARIO=scenario, PATH=f'{bin_dir}:{env["PATH"]}')
        result = subprocess.run(['bash', str(HARNESS)], env=env, text=True,
                                capture_output=True, timeout=15, cwd=ROOT)
        return result, trace.read_text().splitlines(), temp / 'emulator-diagnostics'
    return run


def test_success_checks_capture_and_reopen_without_diagnostics(harness):
    result, trace, diag = harness('success')
    assert result.returncode == 0, result.stderr
    smoke = [line for line in trace if 'flutter test integration_test/android_smoke_test.dart' in line]
    assert len(smoke) == 2
    assert '--dart-define=VERIFY_REOPEN=true' in smoke[1]
    assert not diag.exists()


@pytest.mark.parametrize('scenario', ['dds', 'timeout', 'reopen_dds'])
def test_startup_failure_gets_one_retry_and_keeps_first_attempt_evidence(harness, scenario):
    result, trace, diag = harness(scenario)
    assert result.returncode == 0, result.stderr
    assert 'retrying once' in result.stdout
    smoke = [line for line in trace if 'flutter test integration_test/android_smoke_test.dart' in line]
    assert len(smoke) == 3
    assert any('forward --remove-all' in line for line in trace)
    captured = diag / ('reopen-attempt-1' if scenario == 'reopen_dds' else 'capture-attempt-1')
    assert (captured / 'logcat.txt').read_text() == 'logcat fixture\n'
    assert (captured / 'screenshot.png').read_bytes() == b'fake png'
    assert 'activity crash diagnostics fixture' in result.stdout
    assert (captured / 'dumpsys-activity.txt').exists()
    assert list(captured.glob('smoke-*-attempt-*.txt'))


def test_assertion_failure_is_not_retried_and_diagnostics_precede_uninstall(harness):
    result, trace, diag = harness('test_failure')
    assert result.returncode == 1
    assert len([line for line in trace if 'flutter test integration_test/android_smoke_test.dart' in line]) == 1
    assert (diag / 'final/screenshot.png').exists()
    assert next(i for i, line in enumerate(trace) if 'dumpsys activity' in line) < len(trace) - 1
    assert 'uninstall com.cabinetsurvey.client.debug' in trace[-1]


def test_retry_is_bounded_and_failure_is_not_masked(harness):
    result, trace, diag = harness('dds_twice')
    assert result.returncode == 1
    assert len([line for line in trace if 'flutter test integration_test/android_smoke_test.dart' in line]) == 2
    assert (diag / 'capture-attempt-1/screenshot.png').exists()
    assert (diag / 'final/screenshot.png').exists()


def test_early_encryption_failure_also_collects_diagnostics(harness):
    result, trace, diag = harness('encryption_failure')
    assert result.returncode == 4
    assert not any('flutter test integration_test/android_smoke_test.dart' in line for line in trace)
    assert (diag / 'final/logcat.txt').exists()


def test_only_one_retry_across_both_smoke_phases(harness):
    result, trace, diag = harness('both_dds')
    assert result.returncode == 1
    assert len([line for line in trace if 'flutter test integration_test/android_smoke_test.dart' in line]) == 3
    assert (diag / 'capture-attempt-1/logcat.txt').exists()
    assert (diag / 'final/logcat.txt').exists()


def test_missing_screenshot_is_documented_without_masking_failure(harness):
    result, trace, diag = harness('screenshot_failure')
    assert result.returncode == 1
    assert (diag / 'final/screenshot-unavailable.txt').read_text() == 'screenshot unavailable\n'
    assert not (diag / 'final/screenshot.png').exists()
    assert (diag / 'final/logcat.txt').exists()
