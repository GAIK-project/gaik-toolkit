# GAIK Solution Wizard — basic UI -prototyyppi

Erillinen Next.js-prototyyppi GAIK Solution Wizardin web-UI:sta. Sisältää:

- **Supabase-kirjautumisen** (sähköposti + salasana), reitit suojattu proxyllä (`proxy.ts`)
- **Session-hallinnan**: sessiot ovat vasemmassa sivupalkissa joka sivulla (haku, uudelleennimeäminen, ZIP-lataus, poisto), ja uusi sessio alkaa aloitusnäkymän (`/`) ensimmäisestä viestistä, josta sessio saa nimensä. Session yläpalkissa on neljän gaten rivi: se näyttää missä sessio on, ja vaiheen painallus avaa sen askeleet ja hyväksynnässä tarkistettavat asiat; käyttäjä hyväksyy gatet.
- **Chat-paneelin SSE-streamauksella**: viestilista (käyttäjä/assistentti) + syöte. Vastaus striimataan reaaliajassa `text/event-stream`-endpointista (`/api/sessions/[id]/chat`) token kerrallaan. Mock-vastaus on vaihe-tietoinen ja käyttäjän kielellä; chat-historia tallentuu session-dataan. Varsinainen agentti (Claude Agent SDK) kytketään saman SSE-rajapinnan taakse Sprint 2:ssa.
- **Työtila-paneelin** neljällä välilehdellä: **Työnkulku** (virallinen BPMN 2.0 -kaavio inline bpmn-js:llä; vaihe 8+), **Blueprint** (lomake-editori: nimi/tavoite/kuvaus + vaihekortit, komponentti + asetukset per vaihe; raaka JSON kehittäjänäkymän takana), **Suunnitelma** (SME-5: sama sisältö liiketoimintakielellä — syötteet/vaiheet/tulosteet/ihmisen tarkistukset) ja **PoC** ("Aja PoC" striimaa mock-lokit SSE:llä terminaaliin + status). BPMN V2 aloitettu (#34): asiakkaan referenssi-XML + standardirenderöinti; muokkaus ja JSON-synkka Sprint 2–3.
- **Design-systeemi**: yhtenäinen ammattimainen ilme (teal-brandi `#0d9488`, slate-neutraalit). Semanttiset väri-/varjo-/radius-tokenit `app/globals.css`:n `@theme`-lohkossa (esim. `bg-surface`, `text-text-muted`, `bg-brand`, status-/gate-tokenit, `term-*`). Käytä näitä tokeneita, älä raakoja Tailwind-värejä, jotta ilme pysyy yhtenäisenä.
- **Kielivalinnan fi/en**: kevyt eväste-pohjainen i18n, vaihto sivupalkin käyttäjäalueen FI/EN-valitsimesta (sen vieressä kirjautunut käyttäjä, uloskirjautuminen ja tietosuojaseloste). Toimii server-renderöinnissä ja säilyy session yli.

> **Sessions:** without `WIZARD_API_URL`, state is in-memory mock (`lib/mock-sessions.ts`) — fine for quick UI checks only. **Demo / persistence / editable BPMN:** set `WIZARD_API_URL` (Postgres via `wizard_api`). See [`../WIZARD-DEV.md`](../WIZARD-DEV.md).

Tämä on prototyyppi näytille, ei vielä toiminnallinen wizard (chat, BPMN ja PoC ovat placeholdereita). Pino vastaa GAIK demo-appia (Next.js + Supabase) niin että sen voi myöhemmin siirtää demo-appin laajennokseksi.

## Käyttöönotto

1. Asenna riippuvuudet:
   ```
   npm install
   ```
2. Luo Supabase-projekti (https://supabase.com) tai käytä olemassa olevaa. Ota talteen Project URL ja anon/publishable key (Project Settings → API).
3. Kopioi ympäristömuuttujat:
   ```
   cp .env.example .env.local
   ```
   ja täytä `NEXT_PUBLIC_SUPABASE_URL` ja `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
   Lisää `WIZARD_ALLOWED_EMAILS` (pilkuin eroteltu lista): Supabase-tilassa sisään
   pääsevät vain listatut tilit, joiden osoitteen Supabase on vahvistanut, ja ilman
   muuttujaa ei kukaan. Itse luodulle tilille valitse "Auto Confirm User" tai vahvista
   osoite, muuten tili ei pääse sisään. Sovelluksessa ei ole
   rekisteröitymistä; luo tilit Supabasessa ja ota Supabasen oma sign-up pois päältä
   (Authentication → Sign In / Providers → Allow new users to sign up).
4. Käynnistä:
   ```
   npm run dev
   ```
   Avaa http://localhost:3000 — kirjautumaton käyttäjä ohjataan `/login`-sivulle.

## Kirjautuminen

### Supabase-kirjautuminen (GAIK-demon tunnukset)

`WIZARD_AUTH_MODE=supabase` kirjaa käyttäjät GAIK-demon Supabase-projektin
kautta. Tila valitaan ajon aikana, joten sama image käy myös dev-kirjautumisella
buildattuna (`NEXT_PUBLIC_DEV_AUTH=true` jää silloin pois käytöstä).
Wizardissa ei ole omaa rekisteröitymistä: tunnus luodaan demossa, ja
kirjautumissivu linkittää demon rekisteröitymiseen (`WIZARD_SUPABASE_SIGNUP_URL`,
oletuksena demon `/sign-up`).

Sisään pääsee vain vahvistettu sähköpostiosoite, joka on joko
`WIZARD_ALLOWED_EMAILS`-listassa tai, kun `WIZARD_SUPABASE_ACCESS=access_requests`,
jonka oma rivi demon `access_requests`-taulussa on hyväksytty (`status = approved`).
Demon `wizard_access` ei yksinään päästä sisään. Rivi luetaan käyttäjän omalla istunnolla,
joten taulun säännöt (RLS) ratkaisevat, mitä näkyy; puuttuva tai lukematon rivi ei
päästä ketään sisään. Hyväksyntää odottava tunnus kirjataan ulos ja ohjataan
kirjautumissivulle ilmoituksen kanssa, ja API-kutsu ilman pääsyä saa `401`.

| Muuttuja | Merkitys |
| --- | --- |
| `WIZARD_AUTH_MODE` | `supabase` valitsee tämän tilan |
| `WIZARD_SUPABASE_URL`, `WIZARD_SUPABASE_KEY` | projektin osoite ja julkinen (anon/publishable) avain, luetaan ajon aikana; ei koskaan secret- tai service role -avainta |
| `WIZARD_SUPABASE_ACCESS` | `access_requests`: pääsy demon taulusta |
| `WIZARD_SUPABASE_SIGNUP_URL` | rekisteröitymislinkki; tyhjä piilottaa sen |
| `WIZARD_SUPABASE_ACCESS_CACHE_S` | kuinka kauan hyväksyntä pidetään luettuna, oletus `60`, `0` pois; hylkäystä ei muisteta, joten hyväksyntä näkyy heti ja peruttu hyväksyntä lakkaa viimeistään tämän ajan jälkeen |
| `WIZARD_ALLOWED_EMAILS` | lisäksi päästettävät osoitteet, pilkuin eroteltuna |

Demon Supabase-projektin redirect-listalle lisätään wizardin osoite, ja
sähköpostivahvistuksen on oltava päällä (vahvistamaton osoite on pelkkä väite).

### Dev-kirjautuminen

- **Rekisteröidy**-napilla luot tilin. Jos Supabase-projektissa on sähköpostivahvistus päällä, vahvista linkki sähköpostista ennen kirjautumista (tai kytke vahvistus pois: Authentication → Providers → Email → Confirm email).
- **Kirjaudu**-napilla kirjaudut sisään, jolloin pääset wizard-runkoon.
- **Kirjaudu ulos** -nappi headerissa.

Dev-kirjautumisen eväste on allekirjoitettu ja vanhenee 12 tunnissa
(`lib/dev-session.ts`): käsin kirjoitettu `gaik_dev_session=dev@gaik.local`
ei ole istunto. Allekirjoitusavain on `DEV_AUTH_SECRET` tai sen puuttuessa
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` (compose ja Rahti asettavat sen jo). Jos
kumpaakaan ei ole, käytetään julkista varavaihtoehtoa ja lokiin tulee varoitus,
koska silloin eväste on taas väärennettävissä.

Dev-kirjautumisen yritykset on rajattu (`lib/login-throttle.ts`): kun samalle
tilille tai samasta osoitteesta tulee liian monta epäonnistunutta yritystä
lyhyessä ajassa, uudet yritykset torjutaan hetkeksi samalla yleisellä
"väärä sähköposti tai salasana" -viestillä (myös oikealla salasanalla), eikä
vastaus kerro, onko tili olemassa. Onnistuneita kirjautumisia ei lasketa eikä
viivästetä. Audit-tapahtumassa `auth.login` (`denied`) on silloin
`reason: "throttled"`.

| Muuttuja | Oletus | Merkitys |
| --- | --- | --- |
| `WIZARD_DEV_LOGIN_MAX_FAILURES` | `5` | epäonnistumisia ikkunassa ennen torjuntaa |
| `WIZARD_DEV_LOGIN_WINDOW_S` | `600` | laskentaikkuna sekunteina |
| `WIZARD_DEV_LOGIN_LOCKOUT_S` | `600` | torjunnan kesto sekunteina |
| `WIZARD_TRUSTED_PROXY_HOPS` | ei asetettu | montako `X-Forwarded-For`-otsakkeeseen lisäävää proxya on edessä (Rahtissa reititin: `1`) |

Asiakkaan osoite luetaan `X-Forwarded-For`-otsakkeesta vain, kun
`WIZARD_TRUSTED_PROXY_HOPS` on asetettu: silloin osoite on se merkintä, jonka
viimeinen luotettu proxy lisäsi, eikä asiakkaan itse kirjoittama. Ilman
asetusta otsake ohitetaan ja vain tilikohtainen raja on voimassa.

Laskurit ovat muistissa: web-sovellus ajetaan yhtenä replikana. Ne nollautuvat
uudelleenkäynnistyksessä eivätkä ole yhteisiä prosessien kesken; useampi
replika tarvitsisi jaetun tallennuksen (esim. Redis tai Postgres).

## Rakenne

```
app/
  layout.tsx          juuri-layout (asettaa <html lang> kielen mukaan)
  (app)/              kirjautuneen käyttäjän sivut yhteisessä kuoressa
    layout.tsx        kuori: sivupalkki (sessiot, käyttäjä) + sivu sen vieressä
    page.tsx          aloitusnäkymä: yksi kenttä, josta sessio alkaa
    sessions/[id]/
      page.tsx        session näkymä (yläpalkki ja gaterivi, työtila, chat)
      actions.ts      server actions: advance / regress / approve / reopen
  actions.ts          server actions: startSessionFromMessage, renameSession, removeSession
  locale-actions.ts   server action: setLocale (kielenvaihto)
  api/sessions/
    route.ts          POST: uusi sessio ilman ensimmäistä viestiä (testit, skriptit)
  api/sessions/[id]/chat/
    route.ts          SSE-streaming-endpoint chatin (mock) vastaukselle
    stop/route.ts     POST: pysäyttää kesken olevan vastauksen (send-nappi on silloin "Pysäytä")
  login/
    page.tsx          kirjautumis-/rekisteröitymislomake
    actions.ts        server actions: login / signup / signOut
components/
  sidebar.tsx         sivupalkki (client): sessiot, uusi sessio, käyttäjäalue
  start-view.tsx      aloitusnäkymä (client): ensimmäinen viesti luo session
  session-bar.tsx     session yläpalkki: nimi ja gaterivi (gate-timeline.tsx)
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
proxy.ts              Next.js proxy -kytkentä (Next.js 15:ssä middleware.ts)
```

## Testit ja laatu

```bash
npm run test          # unit (vitest)
npm run test:e2e      # UI mock-storea vasten (Playwright)
npm run test:all      # molemmat
npm run test:stack    # oikea wizard_api + Postgres (Docker, *-stack-specit)
npm run acceptance    # generoi docs/sprint3-acceptance.md
npm run lint          # ESLint CLI, asetukset eslint.config.mjs
```

`npm run test:e2e` ei kata `*-stack`- eikä `local-agent`-specejä: ne skippaavat
itsensä ilman `PLAYWRIGHT_STACK_E2E`- / `PLAYWRIGHT_AGENT_E2E`-muuttujaa. Mikä
hyväksyntäkriteeri jää siis PR-ajon ulkopuolelle, näkyy matriisista
[`docs/sprint3-acceptance.md`](docs/sprint3-acceptance.md) — stack-ajo pyörii
öisin workflow'ssa `wizard-v2-acceptance.yml`.

Koko stack + CI: [`../WIZARD-DEV.md`](../WIZARD-DEV.md). Tietoturva: [`docs/SECURITY.md`](docs/SECURITY.md).

## Logitus

Strukturoitu JSON-logitus (`pino`, `lib/logger.ts`) jokaisella API-reitillä
`withLogging`-wrapperin kautta (`lib/with-logging.ts`): `traceId`, tapahtuma,
HTTP-status ja kesto joka pyynnöstä. Auth-, session- ja
blueprint/BPMN-muutokset kirjautuvat lisäksi audit-tapahtumina
(`lib/audit.ts`). `traceId` kulkee `x-trace-id`-headerissa proxystä (`proxy.ts`)
lähtien ja välittyy myös `wizard_api`-kutsuihin. Käyttäjä näkyy lokeissa ja
audit-tapahtumissa pseudonyyminä (`u_` + 16 heksamerkkiä, `lib/actor-id.ts`),
ei sähköpostiosoitteena: sama henkilö saa aina saman tunnisteen, mutta osoite
ei ole lokissa. Tunniste lasketaan avaimella `WIZARD_PSEUDONYM_KEY` tai sen
puuttuessa `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY`; ilman kumpaakin se on pelkkä
tiiviste ja lokiin tulee kerran varoitus. Sessiot omistaa `wizard_api`ssa
samalla avaimella laskettu omistajatunniste (`o_` + 32 heksamerkkiä,
`lib/owner-id.ts`), ei osoite. Avainta ei saa vaihtaa käytössä olevassa
ympäristössä: uusi avain antaa jokaiselle uuden tunnisteen, eivätkä vanhat
sessiot enää näy omistajalleen. Ei salasanoja, tokeneita,
evästeitä tai koko blueprint-/chat-sisältöä lokeissa.

Lokien lukeminen kehityksessä:

```bash
npm run dev | npx pino-pretty
```

Oletustaso on `debug` kehityksessä ja `info` tuotannossa (`lib/logger.ts`);
ohita `LOG_LEVEL`-ympäristömuuttujalla tarvittaessa (`warn`/`error` näyttää
vähemmän). Ilman `pino-pretty`-putkitusta lokit tulostuvat yhtenä
JSON-rivinä per tapahtuma (helppo grepata `traceId`:llä).

## Seuraavat askeleet

- ~~Korvaa `mock-sessions.ts` oikealla persistenssillä~~ → `WIZARD_API_URL` + `lib/sessions.ts` (Sprint 1)
- Chat: kytke SSE-endpointin mock-vastaus oikeaan agenttiin (Claude Agent SDK, Sprint 2)
- Työnkulku: bpmn-js Modeler + blueprint JSON -synkka + dynaaminen BPMN-generointi (V2 #34)
- Tuotantokirjautuminen (HAKA / Entra ID) Supabasen sijaan, jos tilaaja niin päättää
