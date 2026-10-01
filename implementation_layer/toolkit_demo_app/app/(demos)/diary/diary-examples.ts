// The ready-made diaries of the Construction Diary example. They are written the way a
// site supervisor types quick notes or dictates them on the phone at the end of the day.

import type { ExtractionExample } from "@/components/demo/extraction/config";

export const TYPED_TEXT = `Site diary 15 Jan, Riverside Office Complex phase 2, John Smith (site supervisor)

ok so quick notes for today. week 3. it was cold, around 5 degrees, wind about 3 m/s and cloudy but no rain so nothing stopped because of the weather.

we had 2 supervisors (me and Karen), 5 of our own guys and 6 subcontractors, electrical and plumbing, so 13 people altogether.

what we did: kept going with the interior demolition on the 3rd floor, the electricians pulled cables on the 2nd floor, and the plumbers started the rough-in in the basement. did the weekly site safety walk in the afternoon, all fine.

phases: plumbing in the basement started today. demolition and electrical are still going. asbestos removal and the first site prep are now done and signed off.

one thing, the concrete saw broke around lunch, so we lost about two hours on the 3rd floor. rental place is bringing a new one tomorrow morning. also the delivery of the pipe fittings came a day late but it didn't really hurt us.

overall we are on schedule, safety was good, nobody hurt. tomorrow: finish demolition on the east side of the 3rd floor and start the electrical on the 1st floor. photos of the basement are in the shared folder.`;

const DICTATED_TEXT = `hi this is Sara Lindqvist, I'm the site manager at the Harbour View apartments, building B. it's Tuesday the 4th of March, week ten, and I'm just doing the diary on the way to the car.

weather today was minus two in the morning and it warmed up to plus three, light wind, a bit of sleet around ten but it passed.

so on site we had three of our own people, four formwork guys from Nordbuild, and two crane operators, so nine plus me, ten.

work today, the formwork team finished the wall forms on the second floor and we poured the walls in the afternoon, about forty cubic metres of concrete. the crane was busy all day with rebar for the third floor. we also had the mobile compressor running for the heating tents.

the building inspector came by at two and checked the rebar on the third floor slab. he was happy but wants a photo of the lap lengths, so I will take that tomorrow.

problems, the concrete truck was forty minutes late and we had to stop the pour for a bit, nothing serious. one of the formwork guys cut his finger, small cut, first aid, he carried on working. I wrote it in the accident book.

tomorrow we strip the forms on the first floor and start laying the rebar mats on the third. that's it, bye.`;

const WEEK_TEXT = `Diary for Harbour View B, week 11 (Mon 10 - Wed 12 March), Sara Lindqvist, site manager

Monday 10.3. Cold and windy, about 0 degrees. Crew: 4 of ours, 5 formwork, 1 crane operator. Stripped the first floor forms and started laying rebar mats on the third floor slab. Inspector's photo of lap lengths sent, he approved it. Nothing special, no accidents.

Tuesday 11.3. Snow in the morning, -4 degrees, wind 6 m/s so the crane was stopped for 3 hours before noon. Crew 4 + 5 + 1. Rebar mats on the third floor finished in the afternoon. Delivery of insulation boards came, stored in the yard. Deviation: the pour planned for today was moved to Wednesday because of the wind.

Wednesday 12.3. Clear, -1, light wind. Crew 4 + 5 + 1 and two electricians who started the conduits on the second floor. Poured the third floor slab, about 55 cubic metres, finished at 18:30. Concrete supplier was on time. Slab pour is complete, the rebar work is finished, formwork on the third floor is ongoing. Requested one extra day for the curing of the slab. All safe, no incidents.`;

const TYPED_FI_TEXT = `Työmaapäiväkirja 8.1.2025, Asunto Oy Tampereen Puistokatu 15, peruskorjaus. Kirjaaja Matti Virtanen, työnjohtaja. Viikko 2.

Sää oli aika kolea, -3 astetta, tuuli 2 m/s ja pilvistä, ei lunta. Ei haittaa töille.

Työmaalla oli 2 työnjohtajaa, 3 omaa työntekijää ja 4 sähköurakoitsijan miestä, yhteensä 9 henkilöä.

Mitä tehtiin: sisäpurkua jatkettiin 2. kerroksessa, sähkövetoja alettiin asentaa 1. kerroksessa ja tarkistin työmaan aitauksen, yksi aitaelementti oli kallellaan niin se korjattiin heti.

Työvaiheet: sähköasennukset 1. kerroksessa aloitettiin tänään. Sisäpurku ja rungon purku on vielä käynnissä. Asbestipurku saatiin valmiiksi ja ilmanäytteet otettiin, tulokset tulee viikon sisällä. Kosteusmittaukset keskeytettiin koska mittari meni rikki, uusi tulee torstaina.

Katselmuksia: huoltoyhtiön edustaja kävi kiertämässä iltapäivällä, ei huomautettavaa. Poikkeamia ei ollut, työt etenee aikataulussa. Huomista varten: purku loppuun 2. kerroksessa ja sähköt eteenpäin. Kuvat on kansiossa.`;

const DICTATED_FI_TEXT = `Moi, tässä Pekka Korhonen Kuopion Satamakadun työmaalta, uudisrakennus, tänään on perjantai 14.3.2025 ja viikko on 11. Sanelen nyt päiväkirjan.

Sää: aamulla -6 astetta, päivällä pari pakkasastetta, pohjoistuuli noin 7 metriä sekunnissa ja välillä lumipyryä. Nosturi seisoi aamupäivällä pari tuntia tuulen takia.

Henkilöstöä oli omia kuusi, kaksi talotekniikan miestä ja kolme betonityöntekijää, eli yhteensä yksitoista ja minä.

Työt tänään: valoimme toisen kerroksen välipohjan, betonia meni noin 48 kuutiota, ja valu valmistui puoli kuuden aikaan. Talotekniikka veti putkia kellarissa. Raudoitus kolmanteen kerrokseen aloitettiin iltapäivällä.

Tapahtumia: betoniauto oli puoli tuntia myöhässä ja yksi auto jouduttiin ohjaamaan toiselle puolelle pihaa kun kaivinkone oli tiellä. Työturvallisuustarkastus tehtiin, yhdestä telineestä puuttui sivusuoja, se korjattiin heti. Kukaan ei loukkaantunut.

Poikkeama: lämmityslaitteiden vuokraaja ei tuonut kaikkia lämmittimiä ajoissa, joten osa valusta jouduttiin suojaamaan eristeillä. Pyysin lisäaikaa betonin kovettumiselle yhden päivän.

Huomenna puretaan muotit ensimmäisestä kerroksesta ja jatketaan raudoitusta. Valvoja Liisa Mäkelä käy katselmuksella maanantaina. Kiitos, se oli siinä.`;

export const DIARY_EXAMPLES: ExtractionExample[] = [
  {
    id: "typed",
    title: "Typed daily notes (English)",
    summary:
      "A site supervisor types quick notes at the end of the day: people, work, a broken saw and the plan for tomorrow.",
    kind: "text",
    language: "English",
    text: TYPED_TEXT,
  },
  {
    id: "dictated",
    title: "Dictated diary (English)",
    summary:
      "A site manager dictates the diary on the phone: a concrete pour, an inspector's visit and a small cut.",
    kind: "text",
    language: "English",
    text: DICTATED_TEXT,
  },
  {
    id: "week",
    title: "Three days in one diary",
    summary:
      "Notes for Monday to Wednesday in one text. Each day is extracted as its own diary entry.",
    kind: "text",
    language: "English",
    text: WEEK_TEXT,
  },
  {
    id: "typed-fi",
    title: "Kirjoitettu päiväkirja (Finnish)",
    summary:
      "A Finnish site diary typed in casual language: a renovation site, personnel, work phases and an inspection.",
    kind: "text",
    language: "Finnish",
    text: TYPED_FI_TEXT,
  },
  {
    id: "dictated-fi",
    title: "Sanelu (Finnish)",
    summary:
      "A Finnish diary dictated at the end of a winter day: a slab pour, delays, a safety fix and a request for more time.",
    kind: "text",
    language: "Finnish",
    text: DICTATED_FI_TEXT,
  },
  {
    id: "audio",
    title: "Sanelu äänitteenä (Finnish audio)",
    summary:
      "A recorded Finnish diary of a demolition site, about two minutes long. The audio is transcribed first, then the diary is extracted.",
    kind: "audio",
    language: "Finnish",
    audioUrl: "/diary-fi-dictation.mp3",
  },
];
