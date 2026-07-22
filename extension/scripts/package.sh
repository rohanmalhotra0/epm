#!/usr/bin/env bash
# Build the Chrome Web Store upload zip for the EPM Wizard browser-agent
# extension. Produces dist/epm-wizard-extension-<version>.zip containing only
# the files Chrome loads (manifest at the archive root) — no docs, no scripts.
set -euo pipefail

cd "$(dirname "$0")/.."   # extension/

version="$(node -p "require('./manifest.json').version" 2>/dev/null || \
           grep -oE '"version"[^,]*' manifest.json | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
out="dist/epm-wizard-extension-${version}.zip"

# Files/dirs that ship in the package (everything the manifest references).
include=(
  manifest.json
  background
  common
  content
  sidepanel
  icons
)

# Fail early if anything referenced is missing.
for f in "${include[@]}"; do
  [ -e "$f" ] || { echo "ERROR: missing $f" >&2; exit 1; }
done

mkdir -p dist
rm -f "$out"

# Zip, excluding editor/OS cruft. -x patterns are matched against archive paths.
zip -r -q "$out" "${include[@]}" \
  -x '*/.DS_Store' '*/Thumbs.db' '*.map'

echo "Built $out"
unzip -l "$out" | tail -n +4 | head -n -2 | awk '{print "  " $4}'
echo "Size: $(du -h "$out" | cut -f1)"
