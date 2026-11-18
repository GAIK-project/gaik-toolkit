# GAIK sign-in (Keycloak)

One sign-in for the GAIK apps. Keycloak holds the accounts and the groups; each
app has an oauth2-proxy in front that signs the user in at Keycloak and lets
through only members of the app's group. The apps speak no OIDC themselves, so
the identity source behind Keycloak (its own accounts, Google, later an
organisation's IdP) can change without touching them.

```text
browser ──> Route ──> oauth2-proxy (<stack>-signin) ──> web app ──> wizard_api
                         │  signs in at Keycloak,        checks the forwarded
                         │  admits group wizard-user     token itself
                         ▼                               (lib/proxy-auth.ts)
                   Keycloak (gaik-keycloak, realm gaik)
                         └── own accounts, "Sign in with Google"
```

- `keycloak.yaml`: Keycloak and its own Postgres, one per Rahti project.
- `realm-gaik.json`: the realm, imported on the first start only. Registration is
  off; a new account (also one made by signing in with Google) lands in the group
  `pending` and gets in nowhere until an admin approves it.
- `deploy.sh`: everything below. Secrets are generated and never printed.
- `../openshift/signin-proxy.yaml`, `route-signin.yaml`: the proxy for one wizard
  stack, turned on with `../openshift/deploy.sh signin`.

- `theme/gaik`: the sign-in pages in the Solution Wizard's look (logo, colours,
  card), on top of Keycloak's own theme. After changing it:
  `PROJECT=gaik ./deploy.sh theme` (updates it and restarts Keycloak). The
  stylesheet's address carries a digest of its content, so browsers fetch a
  changed one at once; other theme files are cached an hour
  (`KC_SPI_THEME__STATIC_MAX_AGE`); check a
  change at several window widths, the layout changes at PatternFly's breakpoints.
- `../openshift/signin-templates/error.html`: the proxy's error page. For a user
  still in `pending` it says the account awaits approval and offers a sign-out
  at Keycloak, so they can try another account.

Groups: `pending` (waiting for approval), `wizard-user` (Solution Wizard),
`demo-user` (reserved for the demo app), `admin` (approvers), `aiops-admin` and
`aiops-viewer` (the AIOps stack's Grafana and MLflow, in project `gaik-aiops`;
`gaik-aiops/deploy/k8s/stack/overlays/rahti/README.md` says what each gets).

## Bringing it up

```bash
cd implementation_layer/deploy/keycloak
PROJECT=gaik ./deploy.sh up       # Keycloak + database, realm gaik
PROJECT=gaik ./deploy.sh setup    # groups, second factor, events, approvers, nightly clean-up
```

Keycloak is then at `https://gaik-keycloak-<project>.2.rahtiapp.fi`. The master
admin's console is `/admin` (realm master: no GAIK account works there; approvers
use `/admin/gaik/console/`); the first admin's password is in the Secret
`gaik-keycloak-admin` (`oc extract secret/gaik-keycloak-admin --to=-`). Sign in
once and change it (and then keep the Secret in step, or `setup`, `add-*` and
`approve` cannot sign in).

## Putting a wizard stack behind it

```bash
PROJECT=gaik ./deploy.sh add-client wizard-v2-kc https://wizard-v2-kc-web-gaik.2.rahtiapp.fi
cd ../openshift
PROJECT=gaik INSTANCE=kc ./deploy.sh signin       # proxy, Route, web app settings
PROJECT=gaik INSTANCE=kc ./deploy.sh signin-off   # back to the stack's own sign-in
```

The client id is the stack's name (`wizard-v2`, `wizard-v2-s4`, ...): the web
app checks that the token was issued to it. `deploy.sh manifests` keeps a stack's
sign-in as it is.

## Second factor and sign-in events

Every account signs in with a password and an authenticator app (TOTP: Google
Authenticator, Microsoft Authenticator, 1Password and the like). A new account
sets the app up at its first sign-in; `setup` asks the same of existing accounts
that have none. A sign-in through Google skips Keycloak's password form, so a
flow after it (`gaik post broker otp`) asks for the app as well. Someone who
loses their phone: an approver removes the app in the console (Users → the user →
Credentials → delete OTP), and the next sign-in sets up a new one.

The master admin has no second factor: the scripts sign in with it by password
grant. It has a long random password, and brute-force detection is on in realm
master.

Sign-ins, failed sign-ins and second-factor changes are kept 30 days (Realm
settings → Events → User events), admin changes 90 days.

## Accounts

### Adding accounts (own Keycloak accounts)

A file with one address per line, optionally with a group:

```text
ada@example.org
bob@example.org,wizard-user
carol@example.org,pending
```

```bash
PROJECT=gaik ./deploy.sh add-users users.txt
```

Each account gets a random temporary password that must be changed at the first
sign-in. The passwords are written to `users-passwords-<time>.csv` next to the
file, readable by you only; they never appear on the screen. Hand each one to
its owner over a channel of its own (not in the same message as the address and
the link), then delete the file. An address that already has an account is
skipped. To add an account to one more group (for example `aiops-viewer`):
`PROJECT=gaik ./deploy.sh join someone@example.org aiops-viewer`.

### Approvers (group admin)

Members of the realm's group `admin` may view, approve, disable and delete
users of realm `gaik`, and nothing else: no realm settings, no other realm. They
use their own account in the realm console,
`https://gaik-keycloak-<project>.2.rahtiapp.fi/admin/gaik/console/`, so the
master admin's password is needed only to repair Keycloak itself. Make an
approver with `add-users` (`someone@example.org,admin`). Every change is in the
realm's admin events (Realm settings → Events → Admin events), with who made it,
kept 90 days; the changed objects' contents are not stored there.

An approver can also add someone to `admin`; keep the group small.

### Approving someone who signed in with Google

They land in `pending` and see a page saying their account awaits approval.
Approve them:

```bash
PROJECT=gaik ./deploy.sh approve someone@gmail.com
PROJECT=gaik ./deploy.sh users        # every account and its groups
```

Or in the console: Users → the user → Groups → Join group `wizard-user`, Leave
`pending`.

### Unapproved accounts are deleted after 7 days

Every night at 03:15 (Helsinki) the CronJob `gaik-keycloak-prune-pending`
(`keycloak-maintenance.yaml`, script `prune-pending.sh`) deletes accounts that
have been in `pending` for more than 7 days, so the addresses of people who never
got in are not kept. It runs as the realm's own maintenance client
(`gaik-maintenance`, users of this realm only), logs counts and account ids, not
addresses, and never touches a client's service account. By hand:

```bash
PROJECT=gaik ./deploy.sh prune-pending 7 --dry-run   # what would go
PROJECT=gaik ./deploy.sh prune-pending 7
```

### Closing an account

Console: Users → the user → Enabled off (keeps the record) or Delete. Sessions
end at the next token renewal, within 15 minutes; Sessions → Sign out ends them
at once.

## Sign in with Google

Needs a Google OAuth client, created once in a Google Cloud project that the
project (not a person) owns:

1. console.cloud.google.com → APIs & Services → OAuth consent screen: External,
   app name GAIK, the project's support address; scopes `openid`, `email`,
   `profile` only. Publish it: in Testing mode only listed test users can sign in.
2. Credentials → Create credentials → OAuth client ID → Web application.
   Authorised redirect URI:
   `https://gaik-keycloak-<project>.2.rahtiapp.fi/realms/gaik/broker/google/endpoint`
3. Give the client id and secret to the script through the environment (read the
   secret without echo, so it is not in the shell history):

```bash
read -r GOOGLE_CLIENT_ID; read -rs GOOGLE_CLIENT_SECRET; export GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
PROJECT=gaik ./deploy.sh add-google
```

The Keycloak sign-in page then shows "Google". A personal Google account is
identified by its address only: the organisation does not manage it, and its
second factor is up to its owner. That is why every Google account waits in
`pending` until approved, and why access is closed in Keycloak, not at Google.
Name and address pass to Google's sign-in; say so in the privacy notice.

## The AIOps stack (Grafana, MLflow)

Grafana signs in here with its own OIDC support; MLflow, which has none, behind
an oauth2-proxy like the wizard's. Both are in project `gaik-aiops` and reach
Keycloak over its public address. Their clients and how the groups map are in
`gaik-aiops/deploy/k8s/stack/overlays/rahti/README.md` (Signing in).

## Adding another app (for example the demo app)

1. `PROJECT=gaik ./deploy.sh add-client <app> https://<app address>` makes the
   client and the Secret `<app>-signin` (client-id, client-secret, cookie-secret).
2. Run an oauth2-proxy like `../openshift/signin-proxy.yaml` with `--upstream`
   at the app and `--allowed-group` at its group (`demo-user`), and point the
   app's Route at the proxy.
3. In the app, take the user from `X-Forwarded-Access-Token` and check its
   signature against `http://gaik-keycloak:8080/realms/gaik/protocol/openid-connect/certs`,
   the issuer, `azp` = the client id, the expiry and the group
   (`solution_wizard_v2/lib/proxy-auth.ts` does this in about 150 lines, no
   dependencies). Take the user from the signed token, not from
   `X-Forwarded-Email`.

## Next steps

- Serve the admin console on its own hostname (`KC_HOSTNAME_ADMIN`) before the
  realm holds real users.
- Decide who owns and updates Keycloak after the hand-over.
