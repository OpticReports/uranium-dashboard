#!/bin/bash
# Nightly research-data pull for the Tier-0 lab box.
#
# The mini holds no market-data API key. It pulls allow-listed tables from
# barbell-lab's /api/export/*, guarded by LAB_READ_TOKEN. One direction only:
# nothing here opens a listener, and nothing on Render can start this.
#
# Incremental by default — each table keeps a watermark of the last time
# value seen, and only rows at or after it are re-fetched. --full ignores
# watermarks. Writes NDJSON to $LAB_DATA/<table>.ndjson.
set -euo pipefail

UPSTREAM="${LAB_UPSTREAM:-https://barbell-lab.onrender.com}"
LAB_HOME="${LAB_HOME:-$HOME/lab}"
LAB_DATA="${LAB_DATA:-$LAB_HOME/data}"
TOKEN_FILE="${LAB_TOKEN_FILE:-$LAB_HOME/.lab_read_token}"
STATE="$LAB_DATA/.watermarks"

FULL=0
[ "${1:-}" = "--full" ] && FULL=1

if [ ! -f "$TOKEN_FILE" ]; then
  echo "pull: no token at $TOKEN_FILE" >&2
  echo "      create it (mode 600) with the LAB_READ_TOKEN value from Render." >&2
  exit 1
fi
# A token readable by other local accounts is a token to rotate, not to use.
# BSD stat (macOS) wants -f, GNU stat wants -c — and GNU's -f is a DIFFERENT
# flag (filesystem status) that SUCCEEDS with unrelated output, so `||` alone
# never falls through. Validate the result is octal digits instead.
perms=$(stat -f "%OLp" "$TOKEN_FILE" 2>/dev/null) || perms=""
case "$perms" in
  ''|*[!0-7]*) perms=$(stat -c "%a" "$TOKEN_FILE" 2>/dev/null || echo "?") ;;
esac
if [ "$perms" != "600" ]; then
  echo "pull: $TOKEN_FILE is mode $perms, expected 600" >&2
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")

mkdir -p "$LAB_DATA" "$STATE"

api() {  # api <path> -> body on stdout, non-zero on HTTP error
  curl -fsS --max-time 300 -H "X-Lab-Token: $TOKEN" "$UPSTREAM$1"
}

echo "pull: $UPSTREAM  ->  $LAB_DATA  ($(date -u +%FT%TZ))"

manifest=$(api /api/export/manifest) || {
  echo "pull: manifest failed — 404 means LAB_READ_TOKEN is unset on Render," >&2
  echo "      401 means the local token does not match it." >&2
  exit 1
}

tables=$(printf '%s' "$manifest" \
  | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)["datasets"]))')

for t in $tables; do
  wm_file="$STATE/$t"
  q=""
  if [ "$FULL" -eq 0 ] && [ -f "$wm_file" ]; then
    q="?since=$(cat "$wm_file")"
  fi

  tmp="$LAB_DATA/$t.ndjson.part"
  if ! api "/api/export/table/$t$q" > "$tmp"; then
    echo "pull: $t FAILED (previous file left intact)" >&2
    rm -f "$tmp"
    continue
  fi

  n=$(wc -l < "$tmp" | tr -d ' ')
  if [ "$FULL" -eq 1 ] || [ ! -f "$LAB_DATA/$t.ndjson" ]; then
    mv "$tmp" "$LAB_DATA/$t.ndjson"
  else
    # Incremental slices overlap at the watermark by design (>= not >), so
    # dedupe on the whole line rather than trusting the boundary.
    cat "$LAB_DATA/$t.ndjson" "$tmp" | sort -u > "$LAB_DATA/$t.ndjson.new"
    mv "$LAB_DATA/$t.ndjson.new" "$LAB_DATA/$t.ndjson"
    rm -f "$tmp"
  fi

  latest=$(printf '%s' "$manifest" | python3 -c "
import json,sys
d = json.load(sys.stdin)['datasets']['$t']
print(d['latest'] or '')")
  [ -n "$latest" ] && printf '%s' "$latest" > "$wm_file"

  total=$(wc -l < "$LAB_DATA/$t.ndjson" | tr -d ' ')
  printf '  %-20s +%-8s = %s rows\n' "$t" "$n" "$total"
done

echo "pull: done"
