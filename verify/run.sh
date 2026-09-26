#!/usr/bin/env bash
# One-shot verification pipeline:
#   1. backend code tests (pytest)
#   2. frontend production build (npm run build)
#   3. restoration API smoke test against the live services
# The exit code reports the overall result (0 = all stages passed).
set -u
cd /verify

status=0

echo "=== [1/3] backend code tests (pytest) ==="
if ( cd api && python -m pytest -q ); then
  echo "--- backend tests: OK"
else
  echo "--- backend tests: FAILED"
  status=1
fi

echo "=== [2/3] frontend build (npm ci && npm run build) ==="
if ( cd web && npm ci && npm run build ); then
  echo "--- frontend build: OK"
else
  echo "--- frontend build: FAILED"
  status=1
fi

echo "=== [3/3] restoration API smoke test ==="
if python verify/smoke.py; then
  echo "--- API smoke: OK"
else
  echo "--- API smoke: FAILED"
  status=1
fi

if [ "$status" -eq 0 ]; then
  echo "VERIFY OK"
else
  echo "VERIFY FAILED"
fi
exit "$status"
