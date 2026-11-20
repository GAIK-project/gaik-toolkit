# Account avatars

`public/avatars/avatar-1.webp` to `avatar-8.webp` are the pictures of the header's account
menu (`components/layout/account-menu.tsx`). A hash of the user id picks one
(`lib/account.ts`), so a user keeps theirs on every visit; the initials stand in while
it loads.

They were generated on 19.11.2026 as one 1536x1024 sheet with
`openai/gpt-image-2.6-sunburst` on Replicate (quality high, opaque background), then
cut into eight round 96 px WebP files. The prompt:

```text
A sheet of eight avatar illustrations in a precise grid of 4 columns and 2 rows on a plain white background. The avatars are evenly spaced, each centred in its own cell with generous white space around it, and none touch each other.

Each avatar is a playful, friendly character head on its own filled circle, for the account menu of a web app about AI tools for knowledge work:
1. a round little robot with a single antenna and big round eyes
2. a smiling paper document with a folded corner and round glasses
3. a cheerful owl with large eyes
4. a fox wearing small headphones
5. a soft cloud with a glowing light bulb above it
6. a cube-shaped robot with a happy face
7. a sleepy cat peeking over an open book
8. a microphone character with a smile and tiny arms

Style: flat vector illustration, simple bold shapes, rounded geometry, a dark navy outline of even weight, minimal detail so every face still reads at 32 pixels. One consistent style across all eight.
Circle colours, one per avatar, soft and muted: teal, mint, sky blue, lavender, peach, sand yellow, sage green, coral. The characters use white, navy and a few warm accent tones.

No text, no letters, no numbers, no logos, no borders around the cells, no drop shadows.
```

To add or replace one, generate it in the same style, save it as the next number and
raise `AVATAR_COUNT` in `lib/account.ts`.
The hash takes the count as its modulus, so raising it gives most users another
avatar; `lib/account.test.ts` pins two assignments, so update those on purpose.
