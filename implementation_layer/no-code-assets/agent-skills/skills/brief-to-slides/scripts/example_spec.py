"""Worked example spec: a 15-minute, 5-slide teaching deck + references.
Copy this file, keep the structure, replace the content. Build with:
  python build.py example_spec.py --out example.pptx --preview example.html
  python check_deck.py --pptx example.pptx --minutes 15 --preview example.html
Placeholders in [brackets] stand for intake answers. The example organisation is invented;
say so only in speaker notes, never with words like 'fictional' or 'mock-up' on slides.
"""
from dsl import *

TITLE = 'Writing Better Meeting Notes with AI'
SECTIONS = [('cover', 'Opening and goals'), ('workflow', 'Method and practice'), ('references', 'References')]
# Intake answers. None = the user declined or was not asked -> leave it off the slide.
OPENING_QUESTION = 'What went wrong the last time a meeting summary was shared?'
PRESENTER = None        # e.g. 'Dr Jane Doe' only if the user gave it
AFFILIATION = None      # e.g. 'Example University' only if the user gave it
# Intake answers for layout (references/intake-questions.md Q6-Q9); defaults shown.
THEME = dict(
    show_kicker=False,            # Q6: True = small section label above titles
    footer_text=None,             # Q7: e.g. TITLE or 'Course name · Autumn 2026'
    page_numbers=True,            # Q7
    logo=None,                    # Q8/Q9: dict(path='logo.png', position='top-right', alt='Organisation logo')
)   

SLIDES = []

# 1. Cover: cover() only. Opening question and presenter appear ONLY because the user gave them
#    (ask in the intake; if declined, omit the argument). No illustrations or cards on the cover.
SLIDES.append(dict(id='cover', kind='title', title='Better Meeting Notes', minutes=2, els=cover(
    subtitle='From recording to reliable action items',
    kicker='Team workshop',
    question=OPENING_QUESTION,
    presenter=PRESENTER, affiliation=AFFILIATION,
), notes="""[2 min] SAY: Welcome. In 15 minutes you will learn a simple method to turn a meeting recording or transcript into notes people can act on, and how to check the AI's draft before it goes out.
OPENING QUESTION (about 60 seconds): Read the question on the slide aloud, give the group 15 seconds to think, then take two or three answers. Typical answers: a wrong deadline, a missing owner, a decision recorded that was never actually made. Write them on a flip chart; we come back to them on the recap slide.
EXAMPLE: We follow a small team at "Northwind Studio" planning a client event. (Presenter note: the company and people are invented for this session; say so if asked.)
TRANSITION: "Here is what you will be able to do by the end.\""""))

# 2. Goals — pattern: recap panel + numbered goals with accent bars --------------------
els = [label(0.89, 1.75, 6, 'By the end, you can…')]
y = 2.2
for i, g in enumerate(['Give the AI the context a good note-taker would need',
                       'Ask for decisions, owners and deadlines in a fixed format',
                       'Check every action item against the transcript'], 1):
    h = text_h(g, 5.9, 20) + 0.02
    els += [BAR(0.91, y, h + 0.02), T(1.1, y, 0.4, h, str(i), size=20, bold=True, color=ORANGE), T(1.5, y, 5.9, h, g, size=20)]
    y += h + 0.35
# visual: before/after mini comparison
els += [R(7.9, 1.75, 4.55, 1.75, CREAM, CREAMLINE, r=0.08), label(8.1, 1.88, 4, 'Typical AI summary', size=12),
        T(8.1, 2.25, 4.15, 1.15, 'The team discussed the event and several next steps were agreed.', size=15, italic=True, color=GREY2),
        ARW(10.0, 3.6, 0.36, 0.32, 'd'),
        R(7.9, 4.05, 4.55, 2.05, BLUETINT, r=0.08), label(8.1, 4.18, 4, 'Specified notes', size=12, color=BLUE),
        T(8.1, 4.55, 4.15, 1.5, [P([('Decision: ', {'bold': True}), ('riverside venue', {})]), P([('Tom: ', {'bold': True}), ('budget by Fri', {})]),
                                 P([('Catering: ', {'bold': True}), ('owner not agreed', {'color': BURNT, 'bold': True})])], size=15, gap=0.06)]
SLIDES.append(dict(id='goals', kind='content', kicker='OPENING', title='Three Things You Will Practise', els=els, minutes=2, notes="""[2 min] SAY: Three practical goals. First, context: the AI only knows what is in the transcript and what you tell it. Second, format: decisions, owners and deadlines in a table you can scan. Third, checking: every action item must be traceable to a line in the transcript.
VISUAL: On the right, the same meeting summarised twice. The top version is what a vague prompt usually produces: fluent, but nobody can act on it. The bottom version comes from a specified prompt: one decision, one owner with a deadline, and an explicit gap where nobody took the task. The gap is a feature, not a failure.
ASK: "Which of these do you skip most often?" Usually the third.
TRANSITION: "Let's see the method as a workflow.\""""))

# 3. Workflow — pattern: step row + check chips + takeaway banner -------------------
els = step_row([('1', 'Collect', 'Transcript, agenda, attendee list'), ('2', 'Instruct', 'Purpose, audience, format, if unsure'),
                ('3', 'Draft', 'AI lists decisions and actions'), ('4', 'Check', 'Trace each item to the transcript'),
                ('5', 'Share', 'Send after a person signs off')], y=1.8, h=1.5, dark=(3,))
els += [label(0.89, 3.6, 6, 'What you check at each step')]
for i, c in enumerate(['Right meeting', 'Clear rules', 'Nothing invented', 'Owner + date', 'Right recipients']):
    els += chip(0.89 + i * 2.36, 3.98, 2.12, 0.46, c, fill=CREAM, line=CREAMLINE, size=14)
els += banner('The AI drafts; a person decides what is shared', y=5.55, icon='shield-check')
SLIDES.append(dict(id='workflow', kind='content', kicker='METHOD', title='From Transcript to Action Items', els=els, minutes=4, notes="""[4 min] SAY: Five steps, read left to right. Collect the transcript, agenda and attendee list. Instruct the AI with the purpose of the notes, the audience, the format and what to do when something is unclear. Draft. Check, which is highlighted because it is the step people skip: every action item must point to a line in the transcript. Share only after a person signs off.
VISUAL: The chips under each step say what you check there.
EXAMPLE: Northwind's draft listed "Book venue" with no owner; the transcript shows nobody volunteered, so the note says "owner to be agreed" instead of guessing.
TRANSITION: "Your turn.\""""))

# 4. Activity: ONLY when the user asked for activities and described or approved them.
#    Pattern: brief card + numbered task cards + timing chips
els = [R(0.89, 1.70, 5.4, 4.5, CREAM, CREAMLINE, r=0.08), label(1.1, 1.85, 5, 'Transcript excerpt'),
       T(1.1, 2.25, 5.0, 3.8, [P('Mia: We go with the riverside venue.'), P('Tom: I can send the budget by Friday.'),
                                P('Mia: Someone needs to book catering.'), P('Tom: And the client wants a draft agenda.')], size=15, gap=0.12)]
for i, (t, d) in enumerate([('Decisions', 'What was decided?'), ('Actions', 'Who does what, by when?'), ('Gaps', 'What has no owner or date?')]):
    yy = 1.70 + i * 1.0
    els += [R(6.6, yy, 5.85, 0.85, BLUETINT, r=0.08), E(6.78, yy + 0.2, 0.45, 0.45, ORANGE),
            T(6.78, yy + 0.2, 0.45, 0.45, str(i + 1), size=16, bold=True, color=WHITE, align='c', valign='m'),
            T(7.4, yy + 0.08, 4.9, 0.36, t, size=16, bold=True), T(7.4, yy + 0.44, 4.9, 0.34, d, size=13, font=B, color=GREY2)]
els += chip(6.6, 5.0, 2.8, 0.6, '1 · Pairs · 3 min', fill=NAVY, color=LIGHT, size=14, bold=True)
els += chip(9.65, 5.0, 2.8, 0.6, '2 · Debrief · 1 min', fill=NAVY, color=LIGHT, size=14, bold=True)
SLIDES.append(dict(id='activity', kind='content', kicker='ACTIVITY · 4 MINUTES · IN PAIRS', title='Extract the Action Items', els=els, minutes=4, notes="""[4 min: 3 min in pairs, 1 min debrief]
EXACT INSTRUCTIONS: "In pairs, read the transcript excerpt. Write the decisions, the action items with owner and deadline, and the gaps. Three minutes."
SAMPLE ANSWER: Decision: riverside venue. Actions: Tom sends the budget by Friday. Gaps: catering has no owner or date; the draft agenda has no owner or date.
DEBRIEF: Take two pairs. A good AI draft would list the same gaps instead of inventing an owner. That is exactly what the "if unsure" line in the instructions asks for. Point out that "the client wants a draft agenda" is a request, not yet an action item, until someone takes it; good notes keep that distinction.
TRANSITION: "Let's wrap up.\""""))

# 5. Recap — pattern: numbered dark cards ----------------------------------------
els = numbered_cards([(None, 'Context first', 'Purpose, audience and format'), (None, 'Fixed format', 'Decisions, owners, deadlines'),
                      (None, 'Trace and sign off', 'Every item back to the transcript')], y=1.8, h=2.6, dark=True)
SLIDES.append(dict(id='recap', kind='content', kicker='WRAP-UP', title='Three Takeaways', els=els, minutes=3, notes="""[3 min] SAY: Three takeaways. Context first: tell the AI what the notes are for and who reads them. Fixed format: decisions, owners and deadlines in the same table every time. Trace and sign off: every item goes back to a line in the transcript, and a person approves before sharing.
EXIT QUESTION: "Which meeting this week will you try this on?" Take two answers.
VISUAL: Three dark cards, one per habit, matching the three goals from the start, so participants can check they reached each one.
CLOSE: Thank the group and point to the references slide. Remind them not to paste confidential meeting content into tools their organisation has not approved."""))

# 6. References — untimed --------------------------------------------------------
SLIDES.append(dict(id='references', kind='content', kicker='REFERENCES', title='References', minutes=0, els=[
    T(0.89, 1.70, 11.56, 4.0, [ref('Example Org (2026).', 'Title of a guideline you actually used', '. Publisher.', 'example.org/guide', 'https://example.org/guide')], size=14),
    ],
    notes='References slide, not part of the timed session (0 min). Replace the placeholder with the sources you really used, give the date the facts were checked, and say which facts are likely to change and should be re-checked before the deck is reused.'))
