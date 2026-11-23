# Solution Wizard v2 web app

The repository's `AGENTS.md` applies here too. For anything a user sees:

- Say a thing once per screen: no line that repeats the heading, the steps or the chat.
- No filler: badges, counters, eyebrow labels, helper text that restates a label.
- No raw identifiers (`component_selection`, a JSON key): plain labels in Finnish and English.
- No card inside a card, no scroll box inside a scrolling view, no new UI or animation
  library.
- The AI notices (AI Act art. 50) stay in view.
- An animation starts from a user action, never from `router.refresh()` or a re-render.
- Look at the view in a browser at 1440 px and 390 px before the pull request.
