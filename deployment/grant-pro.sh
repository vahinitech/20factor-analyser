#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Give a person or a group Pro until a date: docs/17-access-and-trials.md,
# "Give a family or teacher a Pro trial", as one command.
#
#   deployment/grant-pro.sh stage|prod "<label>" <last day, YYYY-MM-DD>
#   deployment/grant-pro.sh prod "hyd pilot, shared" 2026-11-21
#
# Run it on the deploy server as the deploying user. It backs up the
# ledger, creates the customer, issues a random key, grants Pro until the
# end of the last day in India time, checks the key and asks the site what
# it gets. The key is never printed: it goes to a 0600 file under
# ~/secrets/pro-keys/, and one line (date, customer id, label, end; never
# the key) goes to the private register, ~/secrets/pro-register.txt unless
# VAHINI_PRO_REGISTER names another file. Hand the key over as docs/17
# "How the key reaches the person" says.
set -euo pipefail

usage() { sed -n '6,7p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[ $# -eq 3 ] || usage
case "$1" in
  stage) C=vahini-analyser-stage; SITE=https://stage.vahinitech.com ;;
  prod) C=vahini-analyser-prod; SITE=https://vahinitech.com ;;
  *) usage ;;
esac
LABEL=$2
END_DAY=$3
END=$(TZ=Asia/Kolkata date -d "$END_DAY 23:59:59" +%s) || { echo "Not a date: $END_DAY" >&2; exit 2; }
[ "$END" -gt "$(date +%s)" ] || { echo "$END_DAY has passed" >&2; exit 2; }
DB=/data/entitlements/subscriptions.sqlite
REGISTER=${VAHINI_PRO_REGISTER:-$HOME/secrets/pro-register.txt}
KEYS=$HOME/secrets/pro-keys

# The tool is backend/server/subscription_admin.py since the folder sort
# (#282); an image built before it has it at the top of backend/.
TOOL=/app/backend/server/subscription_admin.py
docker exec "$C" test -f "$TOOL" || TOOL=/app/backend/subscription_admin.py
admin() { docker exec "$C" python "$TOOL" --db "$DB" "$@"; }

if ! docker exec "$C" test -f "$DB"; then
  echo "No ledger at $DB in $C. First time only (docs/17):" >&2
  echo "  docker exec $C python $TOOL --db $DB init" >&2
  exit 1
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
echo "1. Back up the ledger: /data/entitlements/backup-$STAMP.sqlite"
docker exec "$C" python -c "import os,sqlite3,sys; os.umask(0o077); s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
  "$DB" "/data/entitlements/backup-$STAMP.sqlite"

echo "2. Create the customer"
CUS=$(admin create-customer | python3 -c 'import json,sys; print(json.load(sys.stdin)["customer_id"])')
echo "   $CUS"

echo "3. Issue a random key into the container's private /tmp"
docker exec "$C" rm -f /tmp/newkey
admin issue-key "$CUS" --secret-file /tmp/newkey

echo "4. Pro until $END_DAY 23:59:59 India time"
admin subscription "$CUS" --tier pro --status active --expires-at "$END"

echo "5. Check the key maps to $CUS with tier pro"
admin check-key --secret-file /tmp/newkey

SLUG=$(printf '%s' "$LABEL" | tr -cs 'A-Za-z0-9' '-' | sed 's/^-*//;s/-*$//' | cut -c1-40)
KEYFILE="$KEYS/${SLUG:-key}-$STAMP.key"
echo "6. Move the key to $KEYFILE and clear the container copy"
( umask 077; mkdir -p "$KEYS"; docker exec "$C" cat /tmp/newkey > "$KEYFILE" )
docker exec "$C" rm /tmp/newkey

echo "7. Record it in the private register: $REGISTER"
( umask 077; mkdir -p "$(dirname "$REGISTER")"
  printf '%s  %s  %s  %s  pro until %s (expires_at %s)\n' \
    "$(date -u +%F)" "$1" "$CUS" "$LABEL" "$END_DAY" "$END" >> "$REGISTER" )

echo "8. Ask $SITE what the key gets"
HEADER=$(mktemp)
( umask 077; printf 'Authorization: Bearer %s\n' "$(cat "$KEYFILE")" > "$HEADER" )
curl -s -H @"$HEADER" "$SITE/api/v2/me" | python3 -m json.tool | grep -E '"(tier|subscription_status|expires_at)"' || true
rm -f "$HEADER"

echo
echo "Done: $CUS has Pro on $1 until $END_DAY. Key file: $KEYFILE"
echo "Look it up:  docker exec $C python $TOOL --db $DB show-customer $CUS"
echo "End it:      ... revoke-key <key id>   or   ... subscription $CUS --tier free --status cancelled"
