# OIDC and RBAC policy layer (spike)

Spike for S1 (authentication) and S2 (role-based access control).
Framework-neutral core, with a FastAPI integration because the first reference application uses it.

| Path | What |
|---|---|
| `policy.yaml` | Role-to-permission table (viewer, expert, approver, admin); configuration, not code |
| `gaik_authz/policy.py` | Loads the table, resolves role includes, rejects cycles; unknown roles grant nothing |
| `gaik_authz/tokens.py` | Access token validation: JWKS signature, issuer, audience, expiry; role claim path configurable |
| `gaik_authz/fastapi.py` | `require(permission)` per route; `enforce()` refuses to start if a route declares nothing |
| `gaik_authz/audit.py` | Sends `authz.denied` / `auth.token_rejected` to the collection layer over OTLP |
| `example_api.py` | Example resource server used by the tests |
| `../../deploy/compose/keycloak/gaik-realm.json` | Local realm: roles, clients, test users |

## Decisions shown here

- The API validates the user's token itself; it does not trust a user id forwarded by the front end.
- Deny by default: a route without a declared permission stops the application at startup.
- Separation of duties: `expert` cannot approve, `approver` cannot edit.
- Denials are audit events; the raw subject is pseudonymised by the collector before storage.
- Roles come from one claim (`roles` here, `realm_access.roles` or a group claim elsewhere), so the IdP
  can be replaced by configuration.

## Run

```bash
docker compose -f deploy/compose/docker-compose.yml --profile identity up -d --build --wait
```

```bash
cd wp4/authz && uv run --python 3.12 --extra dev pytest -q
```

Unit tests use locally signed tokens and need nothing running. `test_keycloak_stack.py` gets real tokens
from the local Keycloak and checks the stored audit event; it is skipped when the stack is not running.

The `gaik-local-test` client enables the password grant for automated tests only. Browser clients use the
authorization code flow with PKCE (`gaik-web`).

## Not covered yet

- Browser login flow in a front end (session cookie, refresh, logout)
- Ownership and sharing on top of roles
- Token exchange or client credentials for service-to-service calls
