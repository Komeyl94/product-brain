#!/usr/bin/env bash
# Package the brainify skill into a .skill/.zip bundle for uploading to a claude.ai
# account (Cowork: Settings → Features → add a custom skill).
#
# This is generated on demand into dist/ (gitignored) so the bundle is always current
# and never committed — the source of truth is skills/brainify/SKILL.md.
#
# Usage:
#   bin/package-skill.sh              # writes dist/brainify.skill (a zip)
#   bin/package-skill.sh OUT.zip      # write to a specific path

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/skills/brainify"
OUT="${1:-$ROOT/dist/brainify.skill}"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "error: can't find the skill at $SRC/SKILL.md" >&2
  exit 1
fi
if ! command -v zip >/dev/null 2>&1; then
  echo "error: 'zip' is not installed." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

# Zip with SKILL.md at the top of a brainify/ folder — the layout claude.ai expects.
( cd "$ROOT/skills" && zip -q -r "$OUT" brainify -x '*/.DS_Store' )

echo "📦 Wrote $OUT"
echo "   Upload it to claude.ai → Settings → Features to use brainify in Cowork."
