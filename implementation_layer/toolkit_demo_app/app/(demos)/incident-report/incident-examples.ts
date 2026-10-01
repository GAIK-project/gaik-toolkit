// The ready-made reports of the Incident Reporting example. They are long enough to hold
// the details the extraction looks for: who, when, where, what, why and what was done.

export type IncidentExample = {
  id: string;
  title: string;
  summary: string;
  kind: "text" | "audio";
  language: "English" | "Finnish";
  /** The report itself (text examples) or the audio file to transcribe. */
  text?: string;
  audioUrl?: string;
};

export const SLIP_TEXT = `hi, this is Tomi from the warehouse, I need to report something that happened this morning. so it was around ten to eight, the start of the shift, 12th of January. I was carrying a pile of empty boxes from loading dock 2 over to packing and the floor by the dock door was soaking wet, I guess snow came in on the forklift tyres and melted. there was no wet floor sign and the dock mat was just folded up against the wall. anyway I slipped and went down on my right side, boxes everywhere. Ville was working like five metres away and saw the whole thing.

I'm ok mostly, just a bruised right arm and my hip is a bit sore. no doctor needed, Marja the supervisor gave me a cold pack and told me to sit for 15 minutes. I didn't lose any work time and nothing got broken, the boxes were fine.

Ville mopped the floor straight away and put two signs by the door, and Marja put the mat back down. she also told the forklift guys to wipe their tyres before they come in. I think this wouldn't have happened if the signs were out and the mat was down. Marja said she'll add a floor check to the start of shift list and get a second mat for dock 2.`;

const NEAR_MISS_TEXT = `Hey, it's Laura, shift supervisor. I want to write down a close call from today, 3rd of March, about 2:20 in the afternoon. out in the yard between the goods-in door and storage hall 2.

Jussi was backing a forklift out of hall 2 with a full pallet and he didn't beep the horn at the door. the reversing alarm was on but he couldn't see past the pallet. at the same time Peter Holm, the roof drainage contractor who's visiting, was walking across the yard towards goods-in. he heard the alarm a bit late and jumped back about a metre, the forklift went right past him. nobody got hit, no injuries and nothing damaged, but it was really close.

Anna from goods-in saw it all from the door, and Mika who was waiting in his truck at door 3 saw it too and told me what he saw.

I stopped the yard traffic for ten minutes and had a word with Jussi, he said he was just concentrating on the pallet. I checked the horn and the alarm and both work fine. we closed the crossing with barriers for the rest of the shift. Peter also wasn't wearing a hi-vis so I gave him one.

for later I'd say we need a marked walkway for visitors, a rule to always honk at the hall doors, a mirror at the corner of hall 2, and a quick talk with all the forklift drivers about reversing with a big load. could have been really bad.`;

const TWO_INCIDENTS_TEXT = `NIGHT SHIFT LOG - PLANT 2
Date: 21 April 2026
Shift: 22:00 - 06:00
Shift leader: Hanna Virtanen

22:05 - Hydraulic hose burst on press 4.
The hose on the clamping cylinder of press 4 burst while the press was running a normal cycle. Operator Sami Nieminen was standing at the control panel and was sprayed with hydraulic oil on his left sleeve and left hand. He was sent to the first-aid room, where the oil was washed off. He had mild skin irritation on the hand, was given a cream and went home at 23:15. No sick leave is expected. About 40 litres of oil ended up on the floor around the press. The press was stopped for the rest of the night and the area was closed off. Maintenance technician Kari Salo replaced the hose at 23:30 and the spill was cleaned up with absorbent by the cleaning team. The hose was about six years old and no replacement date was recorded in the maintenance plan.

02:40 - Pallet of sheet metal fell from the rack in aisle C.
A truck driven by Heikki Rantala caught a support beam of the pallet rack in aisle C while turning with a pallet. A pallet of sheet metal on the second level slipped off and fell to the floor. Nobody was in the aisle at the time, and the driver was not hurt. Two sheets were bent and the beam of the rack was damaged. Aisle C was closed with tape until the rack has been inspected by the safety officer, Pirkko Laine, on the morning of 22 April. Heikki said the aisle is narrow for the new, wider pallets. Hanna asked for the aisle width and the rack guards to be reviewed.`;

const NEAR_MISS_FI_TEXT = `Hei, Antti täällä, työnjohtaja. Täytyy kertoa yks läheltä piti -tilanne konepajalta tänään 15.6. kolmen jälkeen, siis 13.40. Konepaja 3, sorvi 12 ja viereinen kulkuväylä.

Kalle Jokinen vaihtoi työkappaletta sorvissa 12 ja unohti istukan avaimen kiinni istukkaan. Sitten se käynnisti koneen ja kone heitti avaimen irti, se lensi varmaan kolme metriä viereiselle kulkuväylälle ja pamahti seinään. Väylällä käveli just silloin huoltoasentaja Juha Mattila, noin kaksi metriä lentoradasta. Avain ei osunut kehenkään, ei loukkaantumisia, vaan seinäpeltiin tuli pieni lommo.

Näin tilanteen itse koneen ovelta, ja Juha näki sen myös. Pysäytin koneen heti ja muistutin Kallea että avain pois ennen käynnistystä. Avain löytyi ja tarkistin sen. Väylä suljettiin nauhalla sorvin 12 kohdalta loppupäiväksi.

Syy oli kai vaan kiire ja rutiinin unohtuminen, eikä sorvissa ole mitään lukitusta joka estäisi käynnistyksen avain kiinni. Ehdotan että vaihdetaan itsepalautuviin avaimiin, tehdään suojaseinä sorvien 11-13 kohdalle ja käydään asia läpi työpaikkakokouksessa. Seuraan itse että homma etenee, kuukauden verran.`;

const FINNISH_TEXT = `Moi, Elina tässä pakkauslinjalta, pitää ilmoittaa tapaturma. Se tapahtui tänään 8.5. noin kymmenen jälkeen (10.15 vähän) tuotantohallissa 1, pakkauslinja 2.

Olin viemässä valmista laatikkoa lavalle ja lattialla kulkureitillä oli sähköjohto, joka oli jäänyt siihen aamun huoltotöiden jälkeen. Ei mitään suojakourua eikä mitään merkkiä. Kompastuin siihen ja kaaduin suoraan eteenpäin, otin vastaan oikealla kädellä. Laatikko lensi lattialle ja kolme tuotetta meni rikki, ehkä 120 euron edestä.

Ranne meni venähtämään ja polveen tuli iso mustelma. Pekka Laine viereiseltä linjalta kuuli kun kaaduin ja tuli heti auttamaan, ja soitti Matti Ojalalle, joka vei mut työterveyteen. Siellä sain kolme päivää sairaslomaa ja tukisiteen ranteeseen.

Johto siirrettiin pois reitiltä ja alue tarkistettiin. Matti kävi jutun läpi koko vuoron kanssa palaverissa. Mun mielestä syy on se, ettei johtoa siirretty eikä suojattu huollon jälkeen, eikä kukaan tarkistanut aluetta. Ehdotan että huollon jälkeen aina tarkistetaan kulkureitit ja että väliaikaiset johdot laitetaan kourun alle, ja että linjalle saadaan pistorasia kattoon niin ei tarvitse vetää johtoja lattialla.`;

export const INCIDENT_EXAMPLES: IncidentExample[] = [
  {
    id: "slip",
    title: "Slip on a wet floor",
    summary:
      "A warehouse worker tells in their own words how they slipped on a wet floor.",
    kind: "text",
    language: "English",
    text: SLIP_TEXT,
  },
  {
    id: "near-miss",
    title: "Forklift near miss",
    summary:
      "A supervisor reports a close call in the yard, casually, as if by phone. No one was hurt.",
    kind: "text",
    language: "English",
    text: NEAR_MISS_TEXT,
  },
  {
    id: "two-incidents",
    title: "Shift log with two incidents",
    summary:
      "An English night-shift log that describes two separate incidents. Each is extracted as its own report.",
    kind: "text",
    language: "English",
    text: TWO_INCIDENTS_TEXT,
  },
  {
    id: "finnish",
    title: "Työtapaturma (Finnish)",
    summary:
      "A worker reports in casual Finnish how they tripped over a cable.",
    kind: "text",
    language: "Finnish",
    text: FINNISH_TEXT,
  },
  {
    id: "near-miss-fi",
    title: "Vaaratilanne (Finnish)",
    summary:
      "A foreman reports in casual Finnish a chuck key thrown from a lathe. Nobody was hurt.",
    kind: "text",
    language: "Finnish",
    text: NEAR_MISS_FI_TEXT,
  },
  {
    id: "audio",
    title: "Spoken report (audio)",
    summary:
      "A recorded report. The audio is transcribed first, then the incident is extracted.",
    kind: "audio",
    language: "English",
    audioUrl: "/sample.m4a",
  },
];
