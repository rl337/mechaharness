#!/usr/bin/env bash
# Build the CI-like image and run the same checks GitHub Actions runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose -f "$ROOT/containers/compose.yaml" build ci
docker compose -f "$ROOT/containers/compose.yaml" run --rm --no-deps ci "$@"
