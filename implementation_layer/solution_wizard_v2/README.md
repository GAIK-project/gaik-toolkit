# GAIK Solution Wizard — basic UI -prototyyppi

Erillinen Next.js-prototyyppi GAIK Solution Wizardin web-UI:sta. Sisältää:

- **Supabase-kirjautumisen** (sähköposti + salasana), reitit suojattu middlewarella
- **Session-hallinnan** (Sprint 1 -tarina): session-lista, uuden aloitus, sekä wizard-näkymä jossa kolme paneelia (chat | työtila | vaiheet). Stepper näyttää nykyisen vaiheen, valmiit vaiheet ja gate-statukset; käyttäjä etenee vaiheissa ja hyväksyy gatet.
- **Chat-paneelin SSE-streamauksella**: viestilista (käyttäjä/assistentti) + syöte. Vastaus striimataan reaaliajassa `text/event-stream`-endpointista (`/api/sessions/[id]/chat`) token kerrallaan. Mock-vastaus on vaihe-tietoinen ja käyttäjän kielellä; chat-historia tallentuu session-dataan. Varsinainen agentti (Claude Agent SDK) kytketään saman SSE-rajapinnan taakse Sprint 2:ssa.
- **Työtila-paneelin** kolmella välilehdellä: **Työnkulku** (kevyt read-only -vuokaavio blueprintistä; AI-/ihmistarkistus-/IO-vaiheet tyyppivärein), **Blueprint (JSON)** (siisti JSON-näkymä) ja **PoC** ("Aja PoC" striimaa mock-lokit SSE:llä terminaaliin + status). Blueprint on mock-dataa session-mallissa. Varsinainen bpmn-js-editori on Sprint 2–3 (spike).
- **Design-systeemi**: yhtenäinen ammattimainen ilme (teal-brandi `#0d9488`, slate-neutraalit). Semanttiset väri-/varjo-/radius-tokenit `app/globals.css`:n `@theme`-lohkossa (esim. `bg-surface`, `text-text-muted`, `bg-brand`, status-/gate-tokenit, `term-*`). Käytä näitä tokeneita, älä raakoja Tailwind-värejä, jotta ilme pysyy yhtenäisenä.
- **Kielivalinnan fi/en**: kevyt eväste-pohjainen i18n, vaihto headerin FI/EN-valitsimesta. Toimii server-renderöinnissä ja säilyy session yli.

> **Mock-data:** session-tila elää tällä hetkellä `lib/mock-sessions.ts`:ssä dev-serverin muistissa (nollautuu uudelleenkäynnistyksessä). Kentät vastaavat suunniteltua tietomallia (S1-1 `wizard_sessions`, S1-2 `blueprint_versions`), jotta oikea persistenssi (Supabase/Postgres tai FastAPI) voidaan kytkeä samaan malliin myöhemmin.

Tämä on prototyyppi näytille, ei vielä toiminnallinen wizard (chat, BPMN ja PoC ovat placeholdereita). Pino vastaa GAIK demo-appia (Next.js + Supabase) niin että sen voi myöhemmin siirtää demo-appin laajennokseksi.

## Käyttöönotto

1. Asenna riippuvuudet:
   ```
   npm install
   ```
2. Luo Supabase-projekti (https://supabase.com) tai käytä olemassa olevaa. Ota talteen Project URL ja anon/publishable key (Project Settings → API).
3. Kopioi ympäristömuuttujat:
   ```
   cp .env.local.example .env.local
   ```
   ja täytä `NEXT_PUBLIC_SUPABASE_URL` ja `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
4. Käynnistä:
   ```
   npm run dev
   ```
   Avaa http://localhost:3000 — kirjautumaton käyttäjä ohjataan `/login`-sivulle.

## Kirjautuminen

- **Rekisteröidy**-napilla luot tilin. Jos Supabase-projektissa on sähköpostivahvistus päällä, vahvista linkki sähköpostista ennen kirjautumista (tai kytke vahvistus pois: Authentication → Providers → Email → Confirm email).
- **Kirjaudu**-napilla kirjaudut sisään, jolloin pääset wizard-runkoon.
- **Kirjaudu ulos** -nappi headerissa.

## Rakenne

```
app/
  layout.tsx          juuri-layout (asettaa <html lang> kielen mukaan)
  page.tsx            suojattu session-lista + uuden aloitus
  actions.ts          server action: startSession (luo + ohjaa wizardiin)
  locale-actions.ts   server action: setLocale (kielenvaihto)
  api/sessions/[id]/chat/
    route.ts          SSE-streaming-endpoint chatin (mock) vastaukselle
  sessions/[id]/
    page.tsx          wizard-näkymä (3 paneelia, stepper, vaiheen ohjaus)
    actions.ts        server actions: advance / regress / approve
  login/
    page.tsx          kirjautumis-/rekisteröitymislomake
    actions.ts        server actions: login / signup / signOut
components/
  locale-switcher.tsx FI/EN-kielivalitsin
  chat-panel.tsx      chat-paneeli (client; lukee SSE-striimin, päivittää reaaliajassa)
  workspace-panel.tsx työtila-paneeli (client; Työnkulku-vuokaavio + Blueprint JSON)
lib/
  current-user.ts     jaettu getCurrentUser (dev-eväste tai Supabase)
  mock-sessions.ts    session-malli + mock-tietovarasto (muistissa)
  i18n.ts             sanakirjat (fi/en) + getLocale/getI18n
  auth.ts             dev-tilan vakiot
  supabase/
    client.ts         selainpuolen Supabase-client
    server.ts         palvelinpuolen Supabase-client
    middleware.ts     session-päivitys + reittisuojaus
middleware.ts         Next.js middleware -kytkentä
```

## Seuraavat askeleet

- Korvaa `mock-sessions.ts` oikealla persistenssillä (Supabase/Postgres tai FastAPI `wizard_api`), sama tietomalli
- Chat: kytke SSE-endpointin mock-vastaus oikeaan agenttiin (Claude Agent SDK, Sprint 2)
- Työnkulku: korvaa kevyt vuokaavio interaktiivisella bpmn-js-editorilla + JSON-synkronointi (Sprint 2–3)
- Tuotantokirjautuminen (HAKA / Entra ID) Supabasen sijaan, jos tilaaja niin päättää
