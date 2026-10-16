#!/usr/bin/env bash
# Take TeslaMate's own Grafana dashboards of a release and rebuild the AMap
# (teslamate/en) and Chinese AMap (teslamate/zh) versions.
#
#   bash scripts/sync_teslamate.sh            # latest release
#   bash scripts/sync_teslamate.sh v4.3.0     # a given release
#
# Use the release of the teslamate/grafana image you run. Afterwards fill in
# the entries whose value is "" in i18n/zh-CN.json, run
# "python3 scripts/build_i18n.py" and commit.
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=https://github.com/teslamate-org/teslamate.git
TAG=${1:-$(git ls-remote --tags --refs "$REPO" 'v*' | sed 's#.*/##' \
             | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$tmp" init -q
git -C "$tmp" fetch -q --depth 1 --filter=blob:none "$REPO" "refs/tags/$TAG"
git -C "$tmp" checkout -q FETCH_HEAD -- grafana/dashboards

rm -rf teslamate/source
cp -r "$tmp/grafana/dashboards" teslamate/source
echo "$TAG" > teslamate/VERSION
echo "TeslaMate dashboards: $TAG"

python3 scripts/build_i18n.py --update
python3 scripts/build_i18n.py --check || true
