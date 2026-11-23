## Quick start

### Option A — Docker (full stack) — **suositus (persistenssi + BPMN)**

Tämä on demojen ja review’n polku: Postgres-sessiot, BPMN wizard_api:n kautta.

```bash
cd implementation_layer/wizard_api
./scripts/dev-stack.sh
```

Tai edellinen tapa:

```bash
cd implementation_layer/wizard_api
export NEXT_SERVER_ACTIONS_ENCRYPTION_KEY=dev-compose-encryption-key-32chars!!
docker compose up --build
```

UI http://localhost:3000 · API http://localhost:8100

**Pysäytys:** `docker compose down` (data säilyy volumeissa)  
**Logit:** `docker compose logs -f wizard-ui` / `wizard-api`

---

## Manuaalinen testaus (Sprint 1 demo)

### 1. Käynnistys

```bash
cd implementation_layer/wizard_api
./scripts/dev-stack.sh
```

Varmista:
- http://localhost:8100/health → `{"status":"ok","version":"…"}`
- http://localhost:3000/login → kirjautumissivu

### 2. Kirjautuminen

| Kenttä | Arvo |
|--------|------|
| Sähköposti | Salasana |
|------------|----------|
| `dev@gaik.local` | `gaik` |
| `dev2@gaik.local` | `gaik2` |

Docker-stackissa `NEXT_PUBLIC_DEV_AUTH=true` — ei Supabasea.

### 3. Uusi sessio (US-S1-01)

1. Etusivulla: kirjoita session nimi → **Aloita uusi**
2. Avautuu wizard-näkymä (chat + työtila + vaiheet)
3. Klikkaa **Seuraava vaihe →** pari kertaa
4. Kirjoita chat-viesti → **Lähetä** — pitäisi näkyä mock-vastaus (SSE)

### 4. Jatka myöhemmin (persistenssi)

1. Sulje välilehti tai selain
2. Avaa http://localhost:3000 uudelleen ja kirjaudu
3. Sessio näkyy listassa **Aiemmat sessiot**
4. Avaa sessio → sama vaihe, chat ja blueprint

### 5. API-restart (kuten #11-testi)

```bash
cd implementation_layer/wizard_api
docker compose restart wizard-api
# odota ~5 s, avaa sessio uudelleen selaimessa
```

Tilan pitäisi säilyä Postgresissa.

### 6. API suoraan (valinnainen)

```bash
# Luo sessio
curl -s -X POST http://localhost:8100/sessions \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"dev@gaik.local","title":"curl-testi"}' | jq .

# Hae (korvaa SESSION_ID)
curl -s http://localhost:8100/sessions/SESSION_ID | jq .
```

### 7. Mock-tila vs. API-tila

| Ympäristö | `WIZARD_API_URL` | Sessiot | Persistenssi + BPMN-edit |
|-----------|------------------|---------|--------------------------|
| Docker Compose (`dev-stack.sh`) — **suositus** | asetettu | Postgres, UUID-sessiot | ✅ oikea polku (demo / review) |
| Paikallinen API + UI | `http://localhost:8100` | Postgres | ✅ sama kuin Docker |
| `npm run dev` ilman API:a (**UI-only**) | ei | In-memory mock (`ses_chatbot` jne.) | ❌ ei täytä tuotevaatimusta |

**Tuotevaatimus** (sessiotallennus + muokattava BPMN ↔ JSON): aina **API-tila**.  
UI-only on vanha Sprint 1 -pikatie UI-kokeiluun — ei demoon, ei asiakasreviewiin.

**Stack E2E** (Postgres + molemmat käyttäjät + API-restart): `cd implementation_layer/wizard_api && ./scripts/docker-test.sh --step stack-e2e`

### 8. Ongelmatilanteet

| Ongelma | Ratkaisu |
|---------|----------|
| Portti 5432 varattu | `docker ps` — sammuta toinen Postgres tai `POSTGRES_HOST_PORT=5433 docker compose up` |
| UI ei lataudu | `docker compose logs wizard-ui` |
| Tyhjä sessiolista API-tilassa | Normaalia ensimmäisellä kerralla — luo uusi sessio |
| Chat ei vastaa | Varmista että olet kirjautunut; tuotanto-UI Dockerissa (ei `next dev`) |
| BPMN “Failed to load” / 500 UI-onlyssa | Aja `./scripts/setup.sh` (`.venv` + pydantic) **tai** käytä API-tilaa (`WIZARD_API_URL`) — suositus: API |
| BPMN OK API-tilassa, 500 UI-onlyssa | Odotettua ilman setupia: UI-only spawn `python3` + `solution_wizard`; API generoi BPMN:n itse |

---

### Option B — Local dev (API + UI separately)

```bash
# 1. Backend
cd implementation_layer/wizard_api
./scripts/setup.sh          # once
./scripts/dev-api.sh        # Postgres + API on :8100

# 2. Frontend (new terminal)
cd implementation_layer/solution_wizard_v2
./scripts/setup.sh          # once (npm + .venv/pydantic for BPMN scripts)
cp .env.example .env.local
# Edit .env.local: NEXT_PUBLIC_DEV_AUTH=true and WIZARD_API_URL=http://localhost:8100
npm run dev                 # http://localhost:3000
```

### Option B2 — UI only (`npm run dev`, mock sessions) — ei demoon

**Älä käytä demoon tai asiakaskatselmointiin.** UI-onlylla ei ole Postgres-persistenssiä;
BPMN-editin “oikea” tallennuspolku on wizard_api.

Ilman `WIZARD_API_URL` Next spawnataan Python
(`scripts/generate_bpmn_from_v2.py` → `solution_wizard` + **pydantic**).
Järjestelmän `/usr/bin/python3` usein ilman pydanticia → 500 / “Failed to load BPMN”.

Jos silti tarvitset UI-onlyn paikalliseen UI-kokeiluun:

```bash
cd implementation_layer/solution_wizard_v2
./scripts/setup.sh          # npm ci + .venv + pip install -r requirements-bpmn.txt
cp .env.example .env.local
# Edit .env.local: NEXT_PUBLIC_DEV_AUTH=true; leave WIZARD_API_URL commented out
npm run dev
```

Optional: `WIZARD_BPMN_PYTHON=/path/to/python` (pydantic asennettuna).  
API-tilassa (`WIZARD_API_URL` asetettu) UI **ei** spawnaa Pythonia BPMN:ään — generointi on wizard_api:ssa.

### Option C — One script (API + UI, no Docker UI image)

```bash
cd implementation_layer
./wizard_dev.sh
```

Login (dev): `dev@gaik.local` / `gaik`

---

## Tests

### All tests in Docker (recommended before PR)

Run in **your own terminal** so output streams live (Cursor agent runs may look stuck):

```bash
cd implementation_layer/wizard_api
./scripts/docker-test.sh
```

Progress lines look like `[08:24:01] >>> Backend tests (pytest)` with elapsed seconds on each step.
First image build (npm + Playwright) can take several minutes — later runs use cache.

Run one stage only:

```bash
./scripts/docker-test.sh --step api    # pytest
./scripts/docker-test.sh --step ui     # vitest + lint + build
./scripts/docker-test.sh --step e2e    # Playwright (starts mock UI, polls health every 5s)
```

From the UI package:

```bash
cd implementation_layer/solution_wizard_v2
npm run test:docker
```

### Local (without Docker test images)

```bash
# Backend unit/integration (needs Postgres on :5432)
cd implementation_layer/wizard_api
pytest -v

# Frontend unit tests
cd implementation_layer/solution_wizard_v2
npm run test

# Frontend E2E (Playwright, mock mode)
npm run test:e2e

# All UI tests
npm run test:all
```

CI runs `.github/workflows/solution-wizard-v2.yml` on changes to wizard_api / solution_wizard_v2.

---

## Lint

```bash
cd implementation_layer/solution_wizard_v2
npm run lint

cd implementation_layer/wizard_api
ruff check . && ruff format --check .
```

---

## Security

See [docs/SECURITY.md](solution_wizard_v2/docs/SECURITY.md).
