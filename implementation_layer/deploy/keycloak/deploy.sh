#!/bin/bash
# =============================================================================
# GAIK Keycloak on Rahti: one sign-in for the GAIK apps (README.md here).
#
#   PROJECT=<project> ./deploy.sh up                     Keycloak + its database, realm gaik
#   PROJECT=<project> ./deploy.sh setup                  after up: groups claim, approvers, nightly clean-up
#   PROJECT=<project> ./deploy.sh theme                  update the sign-in pages' look, then restart Keycloak
#   PROJECT=<project> ./deploy.sh add-client <id> <url> [callback]
#                                                         register an app; Secret <id>-signin (in SECRET_NAMESPACE)
#   PROJECT=<project> ./deploy.sh add-google             "Sign in with Google" (GOOGLE_CLIENT_ID/SECRET from env)
#   PROJECT=<project> ./deploy.sh add-users <file>       accounts from a file, one "email[,group]" per line
#   PROJECT=<project> ./deploy.sh approve <email>        pending -> wizard-user
#   PROJECT=<project> ./deploy.sh join <email> <group>   add an account to one more group
#   PROJECT=<project> ./deploy.sh users                  list accounts and their groups
#   PROJECT=<project> ./deploy.sh prune-pending [days] [--dry-run]
#                                                         delete unapproved accounts now (nightly: 7 days)
#
# Secrets are generated here and never printed. Temporary passwords from
# add-users go to a file only the operator can read, not to the terminal.
# =============================================================================
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to the Rahti project, e.g. gaik}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REALM=gaik
KC=deployment/gaik-keycloak
KEYCLOAK_HOST="gaik-keycloak-${PROJECT}.2.rahtiapp.fi"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

random_secret() { python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'; }

ensure_secret() {  # <name> <key>=<value>...; created once, left alone afterwards
    local name="$1"; shift
    if oc get secret "$name" -n "$PROJECT" >/dev/null 2>&1; then return; fi
    local args=() kv
    for kv in "$@"; do args+=("--from-literal=$kv"); done
    oc create secret generic "$name" -n "$PROJECT" "${args[@]}" >/dev/null
    echo "Secret $name created."
}

# kcadm inside the Keycloak pod, signed in as the bootstrap admin from the pod's
# own environment, so no password passes through this script or its arguments.
# kcadm reads a password from stdin when it has one, so the sign-in gets
# /dev/null and the script after it keeps its stdin (a secret, a JSON body).
# The master admin signs in with a password grant, so it must not get a second
# factor; it is protected by its long random password and brute-force detection.
KC_SIGNIN='cfg=/tmp/kcadm.config; k=/opt/keycloak/bin/kcadm.sh
KC_CLI_PASSWORD="$KC_BOOTSTRAP_ADMIN_PASSWORD" "$k" config credentials --config "$cfg" --server http://localhost:8080 \
    --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" </dev/null >/dev/null 2>&1 \
    || { echo "kcadm sign-in failed (was the bootstrap admin password changed? see README)" >&2; exit 1; }'

kcadm() {
    oc exec -n "$PROJECT" "$KC" -- sh -c "$KC_SIGNIN"'
        exec "$k" "$@" --config "$cfg"' kcadm "$@"
}

# A short script run in the pod after the same sign-in ($k is kcadm.sh, $cfg its
# config). It gets this script's stdin and its arguments as $1...: a secret goes
# on stdin, other values as arguments, never spliced into the script text.
kcadm_script() {  # <script> [args...]
    local script="$1"; shift
    oc exec -i -n "$PROJECT" "$KC" -- sh -c "$KC_SIGNIN
$script" kcadm "$@"
}

up() {
    ensure_secret gaik-keycloak-db database-user=keycloak "database-password=$(random_secret)"
    ensure_secret gaik-keycloak-admin username=admin "password=$(random_secret)"
    oc create configmap gaik-keycloak-realm -n "$PROJECT" \
        --from-file=realm-gaik.json="$SCRIPT_DIR/realm-gaik.json" --dry-run=client -o yaml | oc apply -n "$PROJECT" -f -
    theme
    sed -e "s/PROJECT_PLACEHOLDER/$PROJECT/g" "$SCRIPT_DIR/keycloak.yaml" | oc apply -n "$PROJECT" -f -
    oc rollout status deployment/gaik-keycloak-db -n "$PROJECT" --timeout=300s
    oc rollout status deployment/gaik-keycloak -n "$PROJECT" --timeout=600s
    echo -e "${GREEN}Keycloak is up: https://$KEYCLOAK_HOST (admin password: Secret gaik-keycloak-admin)${NC}"
}

theme() {  # the sign-in pages' GAIK look (theme/gaik); keycloak.yaml maps the files
    local t="$SCRIPT_DIR/theme/gaik/login" version props
    # Keycloak serves theme files under an address that does not change with
    # their content, and a browser keeps what it fetched. The stylesheet's
    # address therefore carries a digest of its content (?v=...), so a changed
    # stylesheet is a new address and every browser fetches it at once.
    version=$(shasum -a 256 "$t/resources/css/gaik.css" | cut -c1-12)
    props="$(mktemp)"
    sed -e "s#css/gaik.css#css/gaik.css?v=$version#" "$t/theme.properties" > "$props"
    oc create configmap gaik-keycloak-theme -n "$PROJECT" \
        --from-file=theme.properties="$props" \
        --from-file=gaik.css="$t/resources/css/gaik.css" \
        --from-file=gaik-wordmark.svg="$t/resources/img/gaik-wordmark.svg" \
        --from-file=messages_fi.properties="$t/messages/messages_fi.properties" \
        --from-file=messages_en.properties="$t/messages/messages_en.properties" \
        --dry-run=client -o yaml | oc apply -n "$PROJECT" -f -
    rm -f "$props"
}

setup() {
    # The groups claim (lib/proxy-auth.ts and oauth2-proxy --allowed-group read
    # it). Made here, not in the realm import: a realm file that lists client
    # scopes replaces Keycloak's default ones.
    if kcadm get client-scopes -r "$REALM" --fields name --format csv --noquotes | grep -qx groups; then
        echo "Client scope groups exists."
    else
        local id
        id=$(kcadm create client-scopes -r "$REALM" -i -s name=groups -s protocol=openid-connect \
            -s 'attributes."include.in.token.scope"=true' -s 'attributes."display.on.consent.screen"=false')
        kcadm create "client-scopes/$id/protocol-mappers/models" -r "$REALM" \
            -s name=groups -s protocol=openid-connect -s protocolMapper=oidc-group-membership-mapper \
            -s 'config."claim.name"=groups' -s 'config."full.path"=false' \
            -s 'config."access.token.claim"=true' -s 'config."id.token.claim"=true' \
            -s 'config."userinfo.token.claim"=true' >/dev/null
        kcadm update "realms/$REALM/default-default-client-scopes/$id" -r "$REALM" >/dev/null
        echo "Client scope groups created and made a default scope."
    fi
    # The apps need only the e-mail address. Keycloak's default user profile asks
    # every user for a first and last name at sign-in; collecting them would be
    # personal data with no use here, so the names are made optional.
    kcadm get users/profile -r "$REALM" | python3 -c '
import json, sys
profile = json.load(sys.stdin)
for attr in profile.get("attributes", []):
    if attr.get("name") in ("firstName", "lastName"):
        attr.pop("required", None)
print(json.dumps(profile))' | kcadm_script '
        cat > /tmp/profile-optional.json
        "$k" update users/profile --config "$cfg" -r "$1" -f /tmp/profile-optional.json >/dev/null
        rm -f /tmp/profile-optional.json' "$REALM"
    echo "First and last name are optional."

    # Sign-ins, failed sign-ins and second-factor changes, kept 30 days: who
    # signed in when, for the audit trail (the apps behind the proxy see no
    # sign-in of their own).
    kcadm update "realms/$REALM" -s eventsEnabled=true -s eventsExpiration=2592000 \
        -s 'enabledEventTypes=["LOGIN","LOGIN_ERROR","LOGOUT","UPDATE_PASSWORD","UPDATE_TOTP","REMOVE_TOTP","IDENTITY_PROVIDER_FIRST_LOGIN"]'
    echo "Sign-in events are recorded (30 days)."

    # A second factor for everyone: an authenticator app (TOTP). Every new
    # account sets one up at its first sign-in; Keycloak's browser flow then asks
    # for it on every sign-in. Existing accounts without one get the same step.
    kcadm update authentication/required-actions/CONFIGURE_TOTP -r "$REALM" -s enabled=true -s defaultAction=true
    require_totp_for_existing
    echo "Every account signs in with a second factor."

    # The master realm (the bootstrap admin) slows down guessing as well.
    kcadm update realms/master -s bruteForceProtected=true -s failureFactor=5 -s waitIncrementSeconds=60 \
        -s maxFailureWaitSeconds=900
    echo "Brute-force detection is on in realm master."

    # Groups added after a realm was first imported (the import runs once).
    local g
    for g in pending wizard-user demo-user admin aiops-admin aiops-viewer; do
        if [ -z "$(group_id "$g")" ]; then
            kcadm create groups -r "$REALM" -s name="$g" >/dev/null
            echo "Group $g created."
        fi
    done

    # Approvers: members of the realm's group admin may view and manage users
    # (approve, disable, delete) in realm gaik and nowhere else, in the console
    # at /admin/gaik/console with their own account. The master admin is then
    # needed only to repair Keycloak itself.
    kcadm add-roles -r "$REALM" --gname admin --cclientid realm-management \
        --rolename view-users --rolename manage-users --rolename query-users --rolename query-groups
    echo "Group admin may view and manage users of realm $REALM."
    # Who changed what in the realm, kept 90 days; without the changed objects'
    # contents, which would copy personal data into the log.
    kcadm update "realms/$REALM" -s adminEventsEnabled=true -s adminEventsDetailsEnabled=false \
        -s 'attributes."adminEventsExpiration"=7776000'
    echo "Admin events are recorded (90 days)."

    # The nightly clean-up's own client: a service account that may only view
    # and manage users here (keycloak-maintenance.yaml).
    if ! kcadm get clients -r "$REALM" -q clientId=gaik-maintenance --fields id --format csv --noquotes | grep -q .; then
        kcadm create clients -r "$REALM" -s clientId=gaik-maintenance -s enabled=true -s protocol=openid-connect \
            -s publicClient=false -s serviceAccountsEnabled=true -s standardFlowEnabled=false \
            -s directAccessGrantsEnabled=false -s implicitFlowEnabled=false >/dev/null
        echo "Client gaik-maintenance created."
    fi
    kcadm add-roles -r "$REALM" --uusername service-account-gaik-maintenance --cclientid realm-management \
        --rolename view-users --rolename manage-users --rolename query-groups
    # Keycloak put the service account in the default group pending; it is not
    # a person waiting for approval.
    local sa pending
    sa=$(kcadm get users -r "$REALM" -q username=service-account-gaik-maintenance -q exact=true --fields id --format csv --noquotes | head -1)
    pending=$(group_id pending)
    if [ -n "$sa" ] && [ -n "$pending" ]; then
        kcadm delete "users/$sa/groups/$pending" -r "$REALM" >/dev/null 2>&1 || true
    fi
    if ! oc get secret gaik-keycloak-maintenance -n "$PROJECT" >/dev/null 2>&1; then
        local id secret
        id=$(kcadm get clients -r "$REALM" -q clientId=gaik-maintenance --fields id --format csv --noquotes)
        secret=$(kcadm get "clients/$id/client-secret" -r "$REALM" --fields value --format csv --noquotes)
        oc create secret generic gaik-keycloak-maintenance -n "$PROJECT" --from-literal=client-secret="$secret" >/dev/null
        unset secret
        echo "Secret gaik-keycloak-maintenance created."
    fi
    oc create configmap gaik-keycloak-scripts -n "$PROJECT" \
        --from-file=prune-pending.sh="$SCRIPT_DIR/prune-pending.sh" --dry-run=client -o yaml | oc apply -n "$PROJECT" -f -
    oc apply -n "$PROJECT" -f "$SCRIPT_DIR/keycloak-maintenance.yaml"
    echo "Nightly clean-up of pending accounts older than 7 days is scheduled."
}

require_totp_for_existing() {
    # Accounts that have no authenticator app and are not yet asked to set one up.
    local id username actions types
    kcadm get users -r "$REALM" -q max=10000 --fields id,username,requiredActions | python3 -c '
import json, sys
for u in json.load(sys.stdin):
    if u["username"].startswith("service-account-"):
        continue
    if "CONFIGURE_TOTP" not in (u.get("requiredActions") or []):
        print(u["id"], json.dumps((u.get("requiredActions") or []) + ["CONFIGURE_TOTP"]))' |
    while read -r id actions; do
        types=$(kcadm get "users/$id/credentials" -r "$REALM" --fields type --format csv --noquotes)
        echo "$types" | grep -qx otp && continue
        kcadm update "users/$id" -r "$REALM" -s "requiredActions=$actions"
    done
}

prune_pending() {  # [days] [--dry-run]: the nightly clean-up, run now
    oc exec -i -n "$PROJECT" "$KC" -- sh -c 'cat > /tmp/prune-pending.sh' < "$SCRIPT_DIR/prune-pending.sh"
    oc exec -n "$PROJECT" "$KC" -- bash /tmp/prune-pending.sh "${1:-7}" ${2:+"$2"}
}

add_client() {  # <client-id> <app-url> [callback path, default /oauth2/callback]
    # The Secret <client-id>-signin goes to SECRET_NAMESPACE (default PROJECT):
    # an app in another Rahti project (the AIOps stack) reads it there.
    local client="${1:?client id}" url="${2:?app URL}" callback="${3:-/oauth2/callback}"
    local ns="${SECRET_NAMESPACE:-$PROJECT}"
    url="${url%/}"
    if kcadm get clients -r "$REALM" -q clientId="$client" --fields id --format csv --noquotes | grep -q .; then
        echo "Client $client exists in realm $REALM."
    else
        kcadm create clients -r "$REALM" -s clientId="$client" -s enabled=true -s protocol=openid-connect \
            -s publicClient=false -s standardFlowEnabled=true -s directAccessGrantsEnabled=false \
            -s serviceAccountsEnabled=false -s implicitFlowEnabled=false \
            -s "redirectUris=[\"$url$callback\"]" -s "webOrigins=[\"$url\"]" \
            -s "attributes.\"post.logout.redirect.uris\"=$url/*" \
            -s 'attributes."pkce.code.challenge.method"=S256' >/dev/null
        echo "Client $client created (redirect $url$callback)."
    fi
    local id secret
    id=$(kcadm get clients -r "$REALM" -q clientId="$client" --fields id --format csv --noquotes)
    secret=$(kcadm get "clients/$id/client-secret" -r "$REALM" --fields value --format csv --noquotes)
    if oc get secret "$client-signin" -n "$ns" >/dev/null 2>&1; then
        echo "Secret $client-signin exists in $ns; left as it is."
    else
        oc create secret generic "$client-signin" -n "$ns" --from-literal=client-id="$client" \
            --from-literal=client-secret="$secret" --from-literal=cookie-secret="$(random_secret)" >/dev/null
        echo "Secret $client-signin created in $ns."
    fi
    unset secret
}

add_google() {
    : "${GOOGLE_CLIENT_ID:?set GOOGLE_CLIENT_ID (Google Cloud OAuth client, see README)}"
    : "${GOOGLE_CLIENT_SECRET:?set GOOGLE_CLIENT_SECRET}"
    if kcadm get identity-provider/instances -r "$REALM" --fields alias --format csv --noquotes | grep -qx google; then
        echo "Identity provider google exists; change it in the admin console."
        return
    fi
    google_otp_flow
    # The secret goes to the pod on stdin, the client id as an argument; neither
    # is spliced into the script.
    printf '%s' "$GOOGLE_CLIENT_SECRET" | kcadm_script '
        secret=$(cat)
        "$k" create identity-provider/instances --config "$cfg" -r "$1" \
            -s alias=google -s providerId=google -s enabled=true -s trustEmail=true \
            -s firstBrokerLoginFlowAlias="first broker login" -s postBrokerLoginFlowAlias="gaik post broker otp" \
            -s config.clientId="$2" -s config.clientSecret="$secret" \
            -s config.syncMode=IMPORT -s config.defaultScope="openid email profile" >/dev/null' "$REALM" "$GOOGLE_CLIENT_ID"
    echo -e "${GREEN}Google sign-in added. Redirect URI for the Google client:${NC}"
    echo "  https://$KEYCLOAK_HOST/realms/$REALM/broker/google/endpoint"
}

google_otp_flow() {
    # A sign-in through Google skips Keycloak's own browser flow, and with it the
    # second factor. This flow runs after every Google sign-in and asks for the
    # authenticator app (setting one up the first time).
    local alias="gaik post broker otp"
    if ! kcadm get authentication/flows -r "$REALM" --fields alias --format csv --noquotes | grep -qx "$alias"; then
        kcadm create authentication/flows -r "$REALM" -s alias="$alias" -s providerId=basic-flow \
            -s topLevel=true -s builtIn=false -s description="Second factor after an identity provider" >/dev/null
        kcadm create "authentication/flows/gaik%20post%20broker%20otp/executions/execution" -r "$REALM" \
            -s provider=auth-otp-form >/dev/null
        local eid
        eid=$(kcadm get "authentication/flows/gaik%20post%20broker%20otp/executions" -r "$REALM" --fields id --format csv --noquotes | head -1)
        kcadm update "authentication/flows/gaik%20post%20broker%20otp/executions" -r "$REALM" \
            -b "{\"id\":\"$eid\",\"requirement\":\"REQUIRED\"}" >/dev/null
        echo "Flow '$alias' created."
    fi
}

user_id() { kcadm get users -r "$REALM" -q email="$1" -q exact=true --fields id --format csv --noquotes | head -1; }
group_id() { kcadm get groups -r "$REALM" -q search="$1" --fields id,name --format csv --noquotes | awk -F, -v g="$1" '$2==g{print $1}' | head -1; }

add_users() {  # <file>: one "email[,group]" per line (group defaults to wizard-user)
    local file="${1:?file of email[,group] lines}"
    local out
    out="$(dirname "$file")/$(basename "$file" .txt)-passwords-$(date +%Y%m%d-%H%M%S).csv"
    ( umask 077; : > "$out" )
    local line email group uid gid pw n=0
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"; line="$(echo "$line" | tr -d '[:space:]')"
        [ -z "$line" ] && continue
        email="$(echo "${line%%,*}" | tr '[:upper:]' '[:lower:]')"
        group="wizard-user"; [[ "$line" == *,* ]] && group="${line#*,}"
        uid=$(user_id "$email")
        if [ -n "$uid" ]; then
            echo "$email exists; skipped."
            continue
        fi
        # A new password and an authenticator app at the first sign-in.
        kcadm create users -r "$REALM" -s username="$email" -s email="$email" -s emailVerified=true \
            -s enabled=true -s 'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]' >/dev/null
        uid=$(user_id "$email")
        pw=$(random_secret | cut -c1-20)
        printf '%s' "$pw" | kcadm_script '
            pw=$(cat)
            "$k" set-password --config "$cfg" -r "$1" --userid "$2" --new-password "$pw" --temporary' "$REALM" "$uid"
        gid=$(group_id "$group")
        if [ -n "$gid" ]; then
            kcadm update "users/$uid/groups/$gid" -r "$REALM" -s realm="$REALM" -s userId="$uid" -s groupId="$gid" -n >/dev/null
            pending=$(group_id pending)
            [ -n "$pending" ] && [ "$group" != pending ] && kcadm delete "users/$uid/groups/$pending" -r "$REALM" >/dev/null 2>&1 || true
        else
            echo -e "${YELLOW}$email: group $group not found; left in pending.${NC}"
        fi
        echo "$email,$pw" >> "$out"
        n=$((n + 1))
        echo "$email added ($group)."
    done < "$file"
    unset pw
    echo -e "${GREEN}$n account(s) added. Temporary passwords (changed at first sign-in): $out${NC}"
}

approve() {  # <email>: pending -> wizard-user
    local email uid gid pending
    email="$(echo "${1:?email}" | tr '[:upper:]' '[:lower:]')"
    uid=$(user_id "$email"); [ -n "$uid" ] || { echo -e "${RED}No account $email${NC}"; exit 1; }
    gid=$(group_id wizard-user); pending=$(group_id pending)
    kcadm update "users/$uid/groups/$gid" -r "$REALM" -s realm="$REALM" -s userId="$uid" -s groupId="$gid" -n >/dev/null
    [ -n "$pending" ] && kcadm delete "users/$uid/groups/$pending" -r "$REALM" >/dev/null 2>&1 || true
    echo -e "${GREEN}$email approved (wizard-user).${NC}"
}

join_group() {  # <email> <group>: add an account to one more group
    local email uid gid
    email="$(echo "${1:?email}" | tr '[:upper:]' '[:lower:]')"
    uid=$(user_id "$email"); [ -n "$uid" ] || { echo -e "${RED}No account $email${NC}"; exit 1; }
    gid=$(group_id "${2:?group}"); [ -n "$gid" ] || { echo -e "${RED}No group $2${NC}"; exit 1; }
    kcadm update "users/$uid/groups/$gid" -r "$REALM" -s realm="$REALM" -s userId="$uid" -s groupId="$gid" -n >/dev/null
    echo "$email joined $2."
}

users() {
    local row id email
    kcadm get users -r "$REALM" --fields id,email --format csv --noquotes | while IFS=, read -r id email; do
        echo "$email: $(kcadm get "users/$id/groups" -r "$REALM" --fields name --format csv --noquotes | tr '\n' ' ')"
    done
}

case "${1:-}" in
    up)         up ;;
    setup)      setup ;;
    theme)      theme; oc rollout restart deployment/gaik-keycloak -n "$PROJECT" ;;
    add-client) add_client "${2:-}" "${3:-}" "${4:-}" ;;
    add-google) add_google ;;
    add-users)  add_users "${2:-}" ;;
    approve)    approve "${2:-}" ;;
    join)       join_group "${2:-}" "${3:-}" ;;
    users)      users ;;
    prune-pending) prune_pending "${2:-7}" "${3:-}" ;;
    *) sed -n '2,20p' "$0"; exit 1 ;;
esac
