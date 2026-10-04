#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PY:-python}"
SINCE=">=$(date -d '7 days ago' +%Y-%m-%d)"

echo "[weekly] search";       "$PY" scripts/search.py --config config.yaml --since "$SINCE"
echo "[weekly] merge";        "$PY" scripts/merge.py  --config config.yaml
echo "[weekly] score";        "$PY" scripts/score.py  --config config.yaml
echo "[weekly] archive";      "$PY" scripts/archive.py --config config.yaml
echo "[weekly] issue";        "$PY" scripts/issue.py  --config config.yaml \
    --issue-body /tmp/issue.md --issue-title /tmp/issue.title
echo "[weekly] done"
