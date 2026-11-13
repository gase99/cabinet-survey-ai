"""Run a CI gate and expose diagnostics as annotations (also accessible via Checks API)."""
import subprocess
import sys
result = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print(result.stdout)
if result.returncode:
    detail = result.stdout[-14000:].replace('%','%25').replace('\r','%0D').replace('\n','%0A')
    print(f'::error::{detail}')
sys.exit(result.returncode)
