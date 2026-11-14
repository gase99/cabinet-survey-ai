"""Run a CI gate and expose concise diagnostics through the Checks API."""
import re
import subprocess
import sys
try:
    result = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
except subprocess.TimeoutExpired as error:
    output = error.stdout.decode() if isinstance(error.stdout, bytes) else error.stdout or ''
    result = subprocess.CompletedProcess(sys.argv[1:], 124, output + '\nCI gate exceeded ten-minute timeout')
print(result.stdout)
if result.returncode:
    # Long framework stack traces otherwise hide the originating assertions.
    lines = [line for line in result.stdout.splitlines() if not re.match(r'^\s*#\d+\s', line)]
    detail = '\n'.join(lines)
    if len(detail) > 30000:
        detail = detail[:20000] + '\n...\n' + detail[-10000:]
    for offset in range(0, len(detail), 3000):
        chunk = detail[offset:offset+3000].replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print(f'::error::{chunk}')
else:
    summary = '\n'.join(result.stdout.splitlines()[-4:])
    escaped = summary.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
    print(f'::notice::CI gate passed: {" ".join(sys.argv[1:])}%0A{escaped}')
sys.exit(result.returncode)
