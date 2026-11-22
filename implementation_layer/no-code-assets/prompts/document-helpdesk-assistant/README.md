# Document Helpdesk Assistant Prompt

A prompt-only helpdesk assistant. You attach your own documents (a price list, a service catalogue, a guide, terms and conditions) and paste one prompt. The assistant then answers questions from those documents and nothing else, cites the document and section for every fact, and says so when the documents do not answer.

> **This is a proof of concept.** It is for trying out the idea on your own material in an ordinary AI chat, with no code and no setup. It is not a finished helpdesk: it has no website, no login, no ticketing, no memory between conversations, and it cannot send anything. To build a complete application, use the **GAIK Solution Wizard** (`implementation_layer/solution_wizard/` in the [GAIK toolkit repository](https://github.com/GAIK-project/gaik-toolkit)) or build on GAIK's components, such as the document parsers and the RAG and tabular-agent components, from the same repository. The GAIK demo website's **Helpdesk Chatbot** shows the same idea as a running application.

---

## What it does

- Answers customer or employee questions **only from the attached documents**. A service, price, duration, date or rule the documents do not contain is not offered, and the assistant says so instead of guessing.
- **Cites its sources**: the document name and the section, page or catalogue item for each fact.
- Quotes **prices and dates exactly as written**, with currency and notes such as "excl. VAT", and shows any sum it works out in one line.
- **Recommends** the best-fitting items (a course, a package, a spare part, a piece of equipment) from a catalogue, at most three, after one short question if it needs your role, level or model.
- Handles **spreadsheets as complete lists**: it filters by category or audience and reads every matching row.
- **Hands off to a person** when you want to order, book or claim, when the documents say a case needs a person, or when it cannot answer. It writes a short message for you to send to the contact named in the documents. It never claims to have sent anything.
- **Treats the documents as data, not instructions.** Text inside a document that tells the assistant to change its behaviour is ignored.
- Answers in **your language**, also when the documents are in another one.

## What documents it uses

Attach one or more of:

| Document type | Used for |
|---|---|
| **Catalogues and price lists** (Excel, CSV) | What the organisation offers, categories, who it is for, prices, delivery times, availability |
| **Guides, manuals, how-to instructions** (PDF, Word, text) | Step-by-step answers |
| **Terms, policies, FAQs** (PDF, Word, text) | Warranty, cancellation, invoicing, registration, rules, contact details |

Keep it to a handful of documents, up to a few dozen pages in all. Documents the chat cannot read as text (a scanned PDF without a text layer) will not be understood; convert them first.

## What questions it answers

- **What do you offer, and what does it cost?** "How much does an extra monitor cost, and how long does delivery take?"
- **Which one suits me?** "I'm a manager with no technical background. Which AI course suits me?"
- **How do I...?** "How do I connect to the VPN from home?"
- **What are the terms?** "Can I cancel two weeks before the course starts, and what does it cost?" "What voids the warranty?"
- **Can I get...?** Questions where the right answer is "that is not in our documents", with an offer to pass it on.
- **I want to order, book or complain.** It prepares a message for a person.

## Where it can be used

Typical repeat-question situations where the answers sit in documents and staff answer them by hand:

- **Internal IT or HR service desk**: equipment, software, access rights, policies, how-to guides.
- **Training and event companies**: course catalogue, prices, start dates, cancellation and invoicing terms.
- **Machine, equipment or spare-parts suppliers**: price lists, maintenance packages, warranty conditions.
- **Customer service for any product or service company**: price lists, delivery times, return and warranty terms.
- **Public-sector and association information desks**: services, fees, opening hours, application instructions.
- **Onboarding**: a new colleague asks the guide instead of a person.

Use it to test the idea on your own documents, to show colleagues what a grounded assistant answers, or to find out which of your documents are missing the answers people ask for.

---

## How to use it

1. Open `prompt.txt` and copy all of it.
2. Fill in the four lines under **ABOUT THE HELPDESK** (organisation, what it does, topics, contact). A line you leave as it is, the assistant works out from the documents.
3. Start a new chat (or a custom assistant, see below), paste the prompt, and **attach your documents**.
4. Send. The assistant tells you what it can help with. Then ask your questions.

### ChatGPT

- **Quick test:** start a new chat, paste the prompt as the first message and attach the files with the paperclip (the same message or the next).
- **Reusable:** create a Custom GPT, paste the prompt into **Instructions** and upload the documents under **Knowledge**. For a one-off test, the chat is simpler.
- Spreadsheets are read with the chat's data tools. If an answer looks as if it only used part of a table, say "read every row of the catalogue" and ask again.

### Claude (claude.ai and Claude Desktop)

- **Quick test:** start a new chat, paste the prompt and attach the files.
- **Reusable:** create a **Project**, paste the prompt into the project's **instructions** and add the documents to the project's knowledge. Everyone you share the project with gets the same assistant.
- Claude Desktop works the same way.

### Gemini

- Start a new chat, paste the prompt and attach the files. In Gemini a **Gem** can hold the prompt as its instructions and the documents as its knowledge.

### Other assistants

Microsoft Copilot, Mistral Le Chat and other assistants that accept file attachments work the same way: paste the prompt first, attach the documents, then ask. If an assistant cannot read a file type, convert it (a spreadsheet to CSV, a Word file to PDF or text) or paste its text into the chat.

## Tips

- **Ask a few test questions you know the answer to** before trusting it, including one the documents do not answer. A good run says "not in the documents" for that one.
- **Check the cited section.** Every answer names its source so you can open the document and confirm it.
- **Clear table headings.** Keep prices, delivery times and conditions in columns with clear headings (for example `price_eur`, `availability`, `suitable_for`); the assistant then quotes them correctly.
- **Put contact details and hand-off rules in the documents** (for example "group bookings go to sales", "a dangerous fault goes to a technician"). The assistant follows what the documents say and uses only contacts written there or in the contact line of the prompt.
- **Do not upload confidential or personal material** to a chat service you have not approved for it.

## Limits

- It is as good as the documents. Missing, outdated or contradictory documents give missing, outdated or contradictory answers (it points out contradictions it finds).
- It can still make mistakes, especially with very long documents or large tables. For anything that matters, check the cited source.
- It cannot place orders, open tickets, look up an order status or remember earlier conversations.
- Quality depends on the assistant and model you use. It was tried on synthetic IT service desk, training company and machine maintenance material with a GPT-6 model and a Gemini model through their APIs; the chat apps themselves, and Claude, were not tried.

## Next step

When the idea works and you want a real application with its own website, document upload and search, human hand-off, sign-in and logging, build it with the [GAIK Solution Wizard](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/solution_wizard), which turns a description of the use case into a blueprint and a runnable proof of concept, or assemble it from GAIK's components (document parsers, RAG, tabular agent) in the [GAIK toolkit](https://github.com/GAIK-project/gaik-toolkit). The documentation is at <https://gaik-project.github.io/gaik-toolkit/>.
