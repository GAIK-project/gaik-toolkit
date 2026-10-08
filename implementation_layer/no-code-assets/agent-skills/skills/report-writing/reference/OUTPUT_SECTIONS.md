# Output Sections Reference

Guidance on crafting each section of the report deliverable.

## Contents
- Section Overview
- Universal Sections (Always Include)
- Conditional Sections (Content-Triggered)
- Template/Sample Processing
- Handling Missing Information

---

## Section Overview

| Section | Type | When to Include |
|---------|------|-----------------|
| Header (Title, Date) | Universal | Always |
| Summary | Universal | Always (even if brief) |
| Key Points | Universal | Always |
| Decisions Made | Conditional | Only if decision signals found |
| Action Items | Conditional | Only if task assignments found |
| Open Questions | Conditional | Only if unresolved questions found |
| Data/Findings | Conditional | Only if data/statistics present |
| Recommendations | Conditional | Only if suggestions found |
| Timeline/Schedule | Conditional | Only if dates/milestones discussed |
| Risks & Issues | Conditional | Only if concerns/blockers mentioned |
| Next Steps | Conditional | Only if actionable follow-ups identified |

**Key principle:** Never invent content. If information for a section doesn't exist in the inputs, omit the entire section. Never create empty sections with placeholder text.

---

## Universal Sections (Always Include)

### Report Header

**Purpose:** Establish document identity and context.

**Always include:**
- Report title (extracted from content or user-provided)
- Date (event date if identifiable, otherwise generation date)

**Conditionally include:**
- Prepared by: [If author identifiable]
- Participants: [If multiple speakers/attendees identified]

**Format:**
```
REPORT
======

Title: [Report title]
Date: [Date]
Prepared by: [Name, if known]
Participants: [Names, if identifiable]
```

---

### Summary

**Purpose:** Provide a concise overview of all content from the inputs.

**Content Requirements:**
- 2-4 paragraphs maximum
- Factual and objective tone
- Cover main topics in order of importance
- Mention key outcomes without duplicating other sections

**What to Include:**
- Purpose/context (if stated)
- Main topics covered
- High-level outcomes
- Any significant concerns raised

**What to Avoid:**
- Detailed action items (these go in their section)
- Verbatim quotes (unless critical)
- Speculation or interpretation beyond source material

**Example:**
```
This analysis examined the Q4 product roadmap and resource allocation
strategy. The team reviewed three major initiatives: the customer portal
redesign, API modernization, and mobile app launch.

Discussion centered on resource constraints, with particular attention
to the engineering team's capacity through the holiday season. Several
trade-offs were evaluated regarding timeline versus feature scope.

The outcome was alignment on a phased approach, with the portal redesign
taking priority due to customer commitments.
```

---

### Key Points

**Purpose:** Highlight the most important takeaways from the content.

**Content Requirements:**
- Bulleted list format
- 3-10 points typically
- Ordered by importance
- Each point should be concise but complete

**Format:**
```
KEY POINTS
----------
- [Major point 1]
- [Major point 2]
- [Major point 3]
```

**What Qualifies:**
- Primary conclusions or outcomes
- Critical facts or data points
- Important agreements or alignments
- Significant concerns or considerations

---

## Conditional Sections (Content-Triggered)

### Decisions Made

**Include when:** Content contains explicit decision signals.

**Identification Signals:**
- "We decided..."
- "The decision is..."
- "We agreed to..."
- "It was concluded that..."
- "Going forward, we will..."
- "The final call is..."

**Format:**
```
DECISIONS MADE
--------------
1. [Clear statement of decision]
   - Context: [Brief background if available]

2. [Clear statement of decision]
   - Context: [Brief background if available]
```

**What Qualifies as a Decision:**
- Explicit agreement on a course of action
- Selection between alternatives
- Approval or rejection of a proposal
- Commitment to a timeline or approach

**What Does NOT Qualify:**
- Discussion of options (without resolution)
- Tentative plans pending approval
- Individual opinions
- Topics for future consideration

**When to Omit:**
If no explicit decisions found, omit this section entirely.

---

### Action Items

**Include when:** Content mentions tasks assigned to specific people.

**Identification Signals:**
- "[Name] will..."
- "Action: [task]"
- "TODO: [task]"
- "Next step: [task]"
- "Assigned to [name]"
- "By [date], we need to..."
- "Follow up on..."

**Table Format:**
```
ACTION ITEMS
------------
| # | Action Item | Owner | Due Date | Priority |
|---|-------------|-------|----------|----------|
| 1 | [description] | [name] | [date] | [H/M/L] |
```

**Field Handling:**

**Action Item:**
- Write as specific, actionable task
- Start with action verb
- Include enough context to be standalone

**Owner:**
- Use name exactly as mentioned in inputs
- If multiple owners: "[Name1], [Name2]"
- If unclear: "TBD"

**Due Date:**
- Use date format from inputs
- If relative ("next week"): Convert to actual date if current date known
- If not specified: "TBD"

**Priority:**
- H (High): Blocking other work, urgent
- M (Medium): Important but not urgent
- L (Low): Nice to have
- If not indicated: Leave blank or mark "TBD"

**When to Omit:**
If no action items found, omit this section entirely.

---

### Open Questions

**Include when:** Unresolved questions or items needing follow-up are found.

**Identification Signals:**
- Questions explicitly deferred
- Unresolved debates
- Items needing external input
- Pending research or investigation
- "We need to figure out..."
- "The question is..."
- "TBD on..."

**Format:**
```
OPEN QUESTIONS
--------------
1. [Question as clear statement]
   - Assigned to: [name, if any]

2. [Question as clear statement]
```

**What Qualifies:**
- Explicit unresolved questions
- Topics requiring further investigation
- Decisions pending additional information
- Items deferred to future discussion

**When to Omit:**
If all questions were resolved, omit this section entirely.

---

### Data/Findings

**Include when:** Numerical data, statistics, or analysis results are present in the content.

**Identification Signals:**
- Numbers, percentages, measurements
- Data tables or charts described
- Analysis results
- Statistical findings
- Metrics or KPIs mentioned

**Format:**
```
DATA/FINDINGS
-------------
[Summary of key data points]

Key metrics:
- [Metric 1]: [Value]
- [Metric 2]: [Value]

[Optional table for structured data]
| Category | Value | Change |
|----------|-------|--------|
```

**What to Include:**
- Key data points and their significance
- Trends or patterns identified
- Comparisons (year-over-year, baseline, etc.)
- Relevant context for the numbers

**When to Omit:**
If no data or statistics present, omit this section entirely.

---

### Recommendations

**Include when:** Suggestions or proposed actions are mentioned in the content.

**Identification Signals:**
- "We recommend..."
- "I suggest..."
- "Should consider..."
- "The proposal is..."
- "Best approach would be..."
- "Advice is to..."

**Format:**
```
RECOMMENDATIONS
---------------
1. [Recommendation]
   - Rationale: [Brief explanation if available]

2. [Recommendation]
   - Rationale: [Brief explanation if available]
```

**What Qualifies:**
- Explicit suggestions for action
- Proposed solutions
- Strategic recommendations
- Best practice guidance

**When to Omit:**
If no recommendations found, omit this section entirely.

---

### Timeline/Schedule

**Include when:** Specific dates, milestones, or deadlines are discussed.

**Identification Signals:**
- Specific dates mentioned
- Milestone names with timeframes
- Deadline references
- Phase or stage timing
- "By [date]..."
- "Target date is..."

**Format:**
```
TIMELINE/SCHEDULE
-----------------
| Milestone | Date | Status |
|-----------|------|--------|
| [Milestone 1] | [Date] | [Status] |
| [Milestone 2] | [Date] | [Status] |
```

Or chronological list:
```
- [Date]: [Event/milestone]
- [Date]: [Event/milestone]
```

**When to Omit:**
If no timeline elements found, omit this section entirely.

---

### Risks & Issues

**Include when:** Concerns, blockers, or potential problems are mentioned.

**Identification Signals:**
- "Risk of..."
- "Concern is..."
- "Issue with..."
- "Blocker:"
- "Problem:"
- "Challenge:"
- "Potential obstacle..."

**Format:**
```
RISKS & ISSUES
--------------
| Risk/Issue | Impact | Mitigation |
|------------|--------|------------|
| [Description] | [H/M/L or description] | [Proposed solution if any] |
```

Or list format:
```
1. [Risk/Issue]
   - Impact: [Description]
   - Mitigation: [Proposed solution if mentioned]
```

**When to Omit:**
If no risks or issues mentioned, omit this section entirely.

---

### Next Steps

**Include when:** Actionable follow-up items are identified that don't fit as formal action items.

**Identification Signals:**
- General follow-up tasks without specific owners
- Future agenda items
- Planned activities
- "Next, we will..."
- "Follow up needed on..."

**Format:**
```
NEXT STEPS
----------
- [Action or follow-up 1]
- [Action or follow-up 2]
```

**Difference from Action Items:**
- Action Items have specific owners and are tracked
- Next Steps are more general or collective tasks

**When to Omit:**
If no next steps identified, omit this section entirely.

---

## Template/Sample Processing

### When Template is Provided

1. **Read template structure:**
   - Identify all section headings
   - Note placeholder patterns: `[Insert here]`, `{{content}}`, `<placeholder>`
   - Preserve table structures
   - Keep logos, headers, footers intact

2. **Map content to template sections:**
   - Match extracted content to appropriate template sections
   - Use semantic understanding to place content correctly

3. **Fill template:**
   - Replace placeholders with relevant content
   - Preserve ALL template formatting
   - Do NOT add sections not in template
   - Do NOT remove template sections (leave empty if no content)

### When Sample is Provided (no template)

1. **Analyze sample structure:**
   - Extract section headings in order
   - Note approximate length per section
   - Identify tone (formal/informal)
   - Note formatting patterns (bullets vs prose, table usage)

2. **Build style profile:**
   - Section order to follow
   - Target length per section
   - Tone to match
   - Formatting to emulate

3. **Apply to output:**
   - Use same section structure as sample
   - Match approximate section lengths
   - Emulate tone and style
   - Do NOT add sections not in sample

### When Both Template and Sample Provided

- **Structure:** From template (takes precedence)
- **Style/tone/length:** From sample
- Template determines what sections exist
- Sample guides how to write the content

---

## Handling Missing Information

### Principle
**Never invent information.** All content must be traceable to input materials.

### Missing Participants/Authors
If not identifiable:
```
Participants: [Not specified in source materials]
```
Or simply omit the field from the header.

### Missing Dates
If date not determinable:
```
Date: [To be confirmed]
```

### Missing Owners for Action Items
```
| 1 | Complete budget review | TBD | 2024-01-15 | M |
```

### Missing Due Dates
```
| 1 | Complete budget review | Sarah | TBD | M |
```

### Partial Information
If only some information is available, include what exists:
```
Participants: John, Sarah, and others (full list not captured)
```

### Conflicting Information
If inputs contain contradictions:
1. Note the discrepancy
2. Present both versions
3. Mark for verification

```
Note: Date appears as both Dec 15 and Dec 16 in notes.
Please verify and correct.
```

### Entire Sections
If no relevant content exists for a conditional section, omit the section entirely. Never include:
- "None"
- "N/A"
- "No [items] found"
- Empty tables
- Placeholder text
