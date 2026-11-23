import type { Locale } from "@/lib/i18n";

/**
 * The user's guide behind "Help" in the account menu: what a session is, how
 * the steps and gates go, what the tabs hold, and what happens to the data.
 * Short on purpose; the names match the buttons and tabs the user sees.
 */
export type HelpSection = { heading: string; text?: string; items?: string[] };

export type HelpGuide = { title: string; lead: string; sections: HelpSection[]; back: string };

export function helpGuide(locale: Locale): HelpGuide {
  if (locale === "en") {
    return {
      title: "Help",
      back: "Back",
      lead: "The Solution Wizard is an AI assistant that turns a description of a business problem into a GenAI solution built from GAIK components: requirements, a solution design, a workflow diagram, a runnable proof of concept (PoC) and its documentation.",
      sections: [
        {
          heading: "A session",
          text: "Each use case is a session of its own. Start one with New session and describe the problem in your own words; the wizard asks what it needs to know. Your sessions are in the sidebar, and only you can see them.",
        },
        {
          heading: "Steps and gates",
          text: "A session goes through 13 steps. The wizard moves the steps on as the work progresses; at four gates it stops and asks you to check the result:",
          items: [
            "Gate 1, requirements: what the solution must do, with what material and for whom.",
            "Gate 2, solution design: the components chosen and the workflow diagram.",
            "Gate 3, test run: the PoC package is run, and you approve the run's result.",
            "Gate 4, handover: the documentation and the deployment package; approving it ends the work, and the package can be downloaded.",
          ],
        },
        {
          heading: "Approve or request changes",
          text: "At a gate, Approve lets the wizard go on. Request changes takes the gate to the chat, where you tell the wizard what to change. An approved gate can be opened again for a change; it and the gates after it are then approved again.",
        },
        {
          heading: "The tabs beside the chat",
          items: [
            "Blueprint: the solution step by step and Fields to extract.",
            "Workflow: the workflow diagram, from the diagram step on.",
            "PoC: the generated package and its test runs, from Gate 2 on.",
          ],
        },
        {
          heading: "AI output",
          text: "The wizard's answers, the blueprint, the diagram and the PoC package are produced by AI. Check them before you use them.",
        },
        {
          heading: "Your data",
          items: [
            "Do not upload personal data or confidential documents unless the use case needs them and you may share them.",
            "From the session list you can download a session's data as a ZIP file, and delete the session. Deleting cannot be undone.",
            "A session is removed when nobody has changed it for 90 days. A chat message, a gate decision or an edit counts as a change; opening the session does not.",
            "More in the privacy notice, in the same menu.",
          ],
        },
      ],
    };
  }
  return {
    title: "Ohje",
    back: "Takaisin",
    lead: "Solution Wizard on tekoälyavustaja, joka muotoilee liiketoimintaongelman kuvauksesta GAIK-komponenteista rakentuvan GenAI-ratkaisun: vaatimukset, ratkaisun rakenteen, työnkulkukaavion, ajettavan kokeiluversion (PoC) ja sen dokumentaation.",
    sections: [
      {
        heading: "Sessio",
        text: "Jokainen käyttötapaus on oma sessionsa. Aloita painamalla Uusi sessio ja kuvaa ongelma omin sanoin; wizard kysyy, mitä se tarvitsee. Sessiosi ovat sivupalkissa, ja vain sinä näet ne.",
      },
      {
        heading: "Vaiheet ja gatet",
        text: "Sessio etenee 13 vaiheen läpi. Wizard siirtää vaihetta työn edetessä; neljässä gatessa se pysähtyy ja pyytää sinua tarkistamaan tuloksen:",
        items: [
          "Gate 1, vaatimukset: mitä ratkaisun pitää tehdä, millä aineistolla ja kenelle.",
          "Gate 2, ratkaisun rakenne: valitut komponentit ja työnkulkukaavio.",
          "Gate 3, testiajo: PoC-paketti ajetaan, ja hyväksyt ajon tuloksen.",
          "Gate 4, luovutus: dokumentaatio ja käyttöönottopaketti; hyväksyntä päättää työn, ja paketin voi ladata.",
        ],
      },
      {
        heading: "Hyväksy tai pyydä muutoksia",
        text: "Gatessa Hyväksy päästää wizardin jatkamaan. Pyydä muutoksia vie gaten chattiin, jossa kerrot wizardille, mitä muutetaan. Hyväksytyn gaten voi avata uudelleen muutosta varten; se ja sitä seuraavat gatet hyväksytään silloin uudelleen.",
      },
      {
        heading: "Chatin vieressä olevat välilehdet",
        items: [
          "Blueprint: ratkaisu vaihe vaiheelta ja Poimittavat tiedot.",
          "Työnkulku: työnkulkukaavio kaaviovaiheesta alkaen.",
          "PoC: generoitu paketti ja sen testiajot Gate 2:n jälkeen.",
        ],
      },
      {
        heading: "Tekoälyn tuottama sisältö",
        text: "Wizardin vastaukset, blueprint, kaavio ja PoC-paketti ovat tekoälyn tuottamia. Tarkista ne ennen käyttöä.",
      },
      {
        heading: "Tietosi",
        items: [
          "Älä lataa henkilötietoja tai luottamuksellisia dokumentteja, ellei käyttötapaus niitä vaadi ja saat jakaa ne.",
          "Session listalta voit ladata session tiedot ZIP-tiedostona ja poistaa session. Poistoa ei voi perua.",
          "Sessio poistetaan, kun sitä ei ole muutettu 90 päivään. Muutokseksi lasketaan chat-viesti, gate-päätös tai muokkaus; pelkkä avaaminen ei.",
          "Lisää tietosuojaselosteessa samassa valikossa.",
        ],
      },
    ],
  };
}
