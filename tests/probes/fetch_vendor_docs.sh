#!/bin/sh
# Snapshot TypeSafe's documentation (docs.typesafe.ai) for the check_* scripts.
# The snapshot is not committed; it is the vendor's content. Usage: ./fetch_vendor_docs.sh [dir]
set -eu
DIR="${1:-$(dirname "$0")/jevdocs}"; mkdir -p "$DIR"; cd "$DIR"
curl -sSL https://docs.typesafe.ai/llms.txt -o llms.txt
grep -oE 'https://docs\.typesafe\.ai/[^)]+\.md' llms.txt | sort -u | while read -r u; do
  curl -sSL --max-time 30 "$u" -o "$(echo "$u" | sed 's#https://docs.typesafe.ai/##; s#/#__#g')"
done
