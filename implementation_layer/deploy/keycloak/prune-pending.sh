#!/bin/bash
# Deletes accounts that have waited in the group `pending` longer than <days>
# (default 7): sign-ins with Google that nobody approved. Runs where kcadm.sh
# is (the Keycloak image): nightly as the CronJob in keycloak-maintenance.yaml,
# or by hand with `deploy.sh prune-pending`.
#
#   prune-pending.sh [days] [--dry-run]
#
# Signs in either as the realm's maintenance client (KC_CLIENT_ID and
# KC_CLI_CLIENT_SECRET, the CronJob) or as the bootstrap admin (inside the
# Keycloak pod). Secrets come from the environment, never from arguments.
# Logs counts and account ids only, no addresses.
set -euo pipefail
days="${1:-7}"; dry=0; [ "${2:-}" = "--dry-run" ] && dry=1
case "$days" in ''|*[!0-9]*) echo "days must be a whole number" >&2; exit 2 ;; esac
realm=gaik
server="${KC_SERVER:-http://localhost:8080}"
k=/opt/keycloak/bin/kcadm.sh
cfg="$(mktemp /tmp/kcadm-prune.XXXXXX)"
trap 'rm -f "$cfg"' EXIT

if [ -n "${KC_CLIENT_ID:-}" ]; then
    "$k" config credentials --config "$cfg" --server "$server" --realm "$realm" --client "$KC_CLIENT_ID" >/dev/null
else
    KC_CLI_PASSWORD="$KC_BOOTSTRAP_ADMIN_PASSWORD" "$k" config credentials --config "$cfg" --server "$server" \
        --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" >/dev/null
fi

# The Keycloak image has no awk: pick the exact name in bash.
gid=""
while IFS=, read -r g_id g_name; do
    if [ "$g_name" = pending ]; then gid="$g_id"; break; fi
done < <("$k" get groups --config "$cfg" -r "$realm" -q search=pending --fields id,name --format csv --noquotes)
[ -n "$gid" ] || { echo "group pending not found" >&2; exit 1; }

cutoff_ms=$(( ($(date +%s) - days * 86400) * 1000 ))
old=0; kept=0
while IFS=, read -r id username created; do
    [ -n "$id" ] || continue
    # A client's service account is a user too, and Keycloak gives it the
    # default group; it is never a person waiting for approval.
    case "$username" in service-account-*) continue ;; esac
    if [ "${created:-0}" -lt "$cutoff_ms" ]; then
        old=$((old + 1))
        if [ "$dry" = 1 ]; then
            echo "would delete $id"
        else
            "$k" delete "users/$id" --config "$cfg" -r "$realm"
            echo "deleted $id"
        fi
    else
        kept=$((kept + 1))
    fi
done < <("$k" get "groups/$gid/members" --config "$cfg" -r "$realm" -q max=10000 \
    --fields id,username,createdTimestamp --format csv --noquotes)

echo "pending accounts older than $days days: $old $([ "$dry" = 1 ] && echo '(dry run, none deleted)' || echo deleted); younger kept: $kept"
