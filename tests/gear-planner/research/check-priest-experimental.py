import runpy, subprocess
from pathlib import Path
from unittest.mock import patch

# Test-process-only switch injection. Production configuration is unchanged.
replay = runpy.run_path(str(Path(__file__).with_name('check-deathknight-raidbots.py')))
original_run = subprocess.run

def experimental_run(args, *a, **kw):
    if isinstance(args, (list, tuple)) and Path(args[0]).name.lower() == 'simc.exe':
        args = [*args, 'allow_experimental_specializations=1']
    return original_run(args, *a, **kw)

with patch.object(subprocess, 'run', experimental_run):
    raise SystemExit(replay['main']())
