#!/usr/bin/env bash
# Run tests and static checks for MechaHarness.
# Used locally and by CI. Prefer an existing .venv when present.

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=========================================="
echo "Running MechaHarness checks"
echo "=========================================="

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
  RUFF="$ROOT/.venv/bin/ruff"
  MYPY="$ROOT/.venv/bin/mypy"
  PYTEST="$ROOT/.venv/bin/pytest"
  MECHA="$ROOT/.venv/bin/mechaharness"
else
  PYTHON="python3"
  RUFF="ruff"
  MYPY="mypy"
  PYTEST="pytest"
  MECHA="mechaharness"
fi

run_check() {
  local name="$1"
  shift
  echo ""
  echo -e "${YELLOW}Running: $name${NC}"
  echo "Command: $*"
  if "$@"; then
    echo -e "${GREEN}✓ $name passed${NC}"
  else
    local exit_code=$?
    echo -e "${RED}✗ $name failed (exit code: $exit_code)${NC}"
    FAILED=1
  fi
}

run_check "Ruff lint" "$RUFF" check src tests
run_check "Mypy type checking" "$MYPY"
run_check "Pytest" "$PYTEST" -q

if command -v "$MECHA" >/dev/null 2>&1 || [ -x "$MECHA" ]; then
  run_check "CLI version" "$MECHA" version
  run_check "CLI backends" "$MECHA" backends
  run_check "CLI families" "$MECHA" families
else
  echo ""
  echo -e "${YELLOW}⚠ mechaharness CLI not on PATH; skipping CLI smoke checks${NC}"
fi

echo ""
echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
else
  echo -e "${RED}Some checks failed. Please fix the issues above.${NC}"
  exit 1
fi
