#!/usr/bin/env bash
# Install the mounted checkout the way CI does, then run checks (or extra args).
set -euo pipefail

cd /src

if [ ! -f pyproject.toml ]; then
  echo "error: /src is not a MechaHarness checkout (mount the repo at /src)" >&2
  exit 1
fi

python -m pip install -e ".[dev]"

python - <<'PY'
from importlib.metadata import distribution, version

dist = distribution("pyiv")
print(f"pyiv {version('pyiv')} from {dist.locate_file('')}")
direct = dist.read_text("direct_url.json")
if direct is not None:
    raise SystemExit(f"pyiv was not installed from PyPI:\n{direct}")
PY

if [ "$#" -eq 0 ]; then
  exec ./run_checks.sh
fi
exec "$@"
