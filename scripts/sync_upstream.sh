#!/usr/bin/env bash
# Merge the latest upstream dashboards and refresh the Chinese translation.
#
#   bash scripts/sync_upstream.sh
#
# Afterwards fill in the entries whose value is "" in i18n/zh-CN.json,
# run "python3 scripts/build_i18n.py" and commit.
set -euo pipefail
cd "$(dirname "$0")/.."

UPSTREAM=https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards.git
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM"
git fetch upstream main
git merge --no-edit upstream/main

python3 scripts/build_i18n.py --update
python3 scripts/build_i18n.py --check || true
