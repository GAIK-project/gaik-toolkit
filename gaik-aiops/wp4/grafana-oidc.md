# Grafana login and role mapping

Grafana (the WP5 dashboard platform) uses the same identity provider and the same `roles` claim as the
API.

```bash
docker compose -f deploy/compose/docker-compose.yml -f deploy/compose/identity.yml up -d --build --wait
```

Open http://localhost:3000 and choose "Organisation login". Test users are in
`deploy/compose/keycloak/gaik-realm.json` (password `<username>-local-only`).

## Mapping

| WP4 role | Main Org. (monitoring) | Security (audit log) |
|---|---|---|
| `admin` | Admin | Viewer |
| `expert`, `approver`, `viewer` | Viewer | not a member |
| none | login refused | login refused |

Nobody gets Grafana server admin through the IdP. Dashboards are files, so no WP4 role needs Grafana
Editor; `config.manage` (admin) covers the rest.

## Why a separate Security organisation

Checked on the local stack: a Grafana **Viewer could run any SQL against the audit store** through
`/api/ds/query`, whatever the folder permissions. Grafana OSS has no datasource permissions; every
member of an organisation can query every datasource in it. Hiding the Security folder would not
have protected the audit log.

Datasources belong to an organisation, so the audit datasource and dashboard live in their own
organisation, and only the `admin` role is mapped into it, as Viewer: it can read the audit log but
cannot change or delete the datasource. File provisioning cannot create organisations and stops Grafana
when it refers to a missing one, so `deploy/compose/grafana/setup/security_org.py` creates the
organisation, datasource and dashboards through the API and re-applies them every five minutes.

## Implementation notes

- `org_attribute_path: roles` with `org_mapping`; **no** `role_attribute_path`. When that is set, Grafana
  applies its single role to every mapped organisation, which would make admins Admin of Security too.
- `role_attribute_strict`: a user that matches no mapping entry is refused.
- Org role sync runs on every login, so a role removed in the IdP takes effect at the next login.
- The browser uses `localhost:8180`; Grafana calls the token and userinfo endpoints on the compose
  network. In a real deployment both are the same public IdP URL.
- Client secret is a local value in the overlay; in a real deployment use
  `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET__FILE` with a file rendered by the vault agent (`secrets/`).
- The local `admin` account stays as break-glass access here, where the compose overlay keeps Grafana's
  sign-in form on. On Rahti the form is off (`GF_AUTH_DISABLE_LOGIN_FORM`), so the local admin signs in
  only through the API or after the form is switched back on; see the Rahti overlay's README.md. Grafana refuses to link an IdP user whose login
  equals an existing local account, so an IdP user named `admin` cannot take over the local admin; the
  test realm therefore uses `security-admin`.
- Keycloak test users have fixed ids: the dev server is in memory, and new subjects after a restart would
  look like different people with the same login, which Grafana (correctly) refuses.

## Tests

`wp4/authz/tests/test_grafana_oidc.py` drives the browser flow over HTTP for every role and checks
organisation membership, roles, audit datasource access and refusal of users without a role.
`shared/collection/sink/tests/test_platform_stack.py` checks that the audit store is not in the main
organisation.
