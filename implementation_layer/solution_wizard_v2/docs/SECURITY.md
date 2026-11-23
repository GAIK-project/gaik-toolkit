# Solution Wizard V2 — security notes (Sprint 1)

## Authentication

- **UI:** Routes protected by `proxy.ts` (Supabase or `NEXT_PUBLIC_DEV_AUTH` cookie).
- **Dev auth** (`dev@gaik.local` / `gaik`, `dev2@gaik.local` / `gaik2`) is for local/demo only. **Never enable `NEXT_PUBLIC_DEV_AUTH` in production.**

## Session isolation (US-S1-01)

- Server components and API routes use `requireOwnedSession()` / `getSessionForUser()` so users only see their own sessions.
- Unknown or other-user session IDs return **404** (no information leak).

## wizard_api (FastAPI)

- **No end-user authentication in Sprint 1.** The API is intended for the **Next.js server** on a trusted network (Docker Compose / internal).
- Do **not** expose port `8100` publicly without adding auth (Sprint 2+).
- `user_id` is validated: no path traversal (`..`, `/`, `\`).
- Output directories are created under `WIZARD_SESSION_OUTPUT_ROOT/<user_id>/<session_id>/`.

## Secrets

- Keep `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` and Supabase keys in `.env.local` (gitignored).
- Never commit `.env.local` or production credentials.

## BPMN spike route

- Serves a **static public** XML file only for allowed sessions; requires owned session.
