# Q2 Product Planning Meeting Report

## Executive Summary

The available source material does not describe a Q2 product planning meeting held on September 10, 2024. It describes a Q3 Product Roadmap Review dated December 15, 2024, focused on reviewing progress and planning for three areas: the mobile app launch status, the dashboard redesign, and the API modernization project (meeting_recording.mp3). Lisa Park also reported that user testing with 12 participants found very positive feedback overall, with the main issue being a confusing onboarding flow that the team approved simplifying from five steps to three (meeting_recording.mp3; notes.txt).

Overall, the meeting was aligned on continuing all three initiatives while reducing delivery risk through targeted fixes and phased rollout decisions. Key outcomes included approval to simplify the mobile app onboarding flow, approval to phase the API migration by using read-only GraphQL first and moving write operations to Q4, and approval to use AWS rather than on-premises infrastructure for load testing. The discussion also highlighted near-term execution priorities, including closing the remaining critical dashboard defects and preparing for the mobile app's January 15 beta release, while noting resource and operational constraints such as assigning two developers to onboarding work, setting up an AWS load-testing environment, and working around the holiday deployment freeze from December 23, 2024, to January 2, 2025 (notes.txt) (deployment-freeze-policy.pdf).

## Decisions Made

- **Phase the API migration** - Approved phasing the migration, with GraphQL read-only work first and write operations moved to Q4. This implementation approach was reflected in the meeting notes and sketch, which both separate read-only and write work into different timeframes (notes.txt, sketch.png).

- **Use AWS for load testing** - Approved using AWS rather than on-prem infrastructure for load testing. The decision was recorded directly in the notes and repeated in the sketch, and the notes also show immediate follow-up to set up an AWS load-testing environment (notes.txt, sketch.png).

- **Simplify the mobile app onboarding flow** - Approved reducing onboarding from five steps to three. The main reason was user-testing feedback that the flow was somewhat confusing, and the team agreed it could be completed before beta because it was described as a relatively small change (meeting_recording.mp3, notes.txt, sketch.png).

## Action Items

# Action Items

| **Action Item** | **Owner** | **Due Date** | **Priority** |
| --------------------------------- | --------- | ------------ | ------------ |
| Assign 2 developers to simplify the mobile app onboarding flow from five steps to three | Mike | End of next week | Not stated |
| Provide final app screenshots for the press kit | Lisa | Dec 18, 2024 | Not stated |
| Set up AWS load testing environment | David + Mike | Not stated | Not stated |
| Fix the remaining 3 critical dashboard bugs | Dev team | Wednesday | Not stated |

## Open Questions

- What’s the budget for AWS load testing? (notes.txt)
- Who’s covering for Lisa during holiday break? (notes.txt)
- Do we need stakeholder approval for the API phasing? (notes.txt)

## Next Steps

The immediate focus is on completing the near-term delivery items assigned in the meeting and preparing for holiday delivery constraints.

1. Complete the onboarding simplification by the end of next week, with Mike assigning two developers to reduce the flow from five steps to three (notes.txt).
2. Fix the remaining three critical dashboard bugs by Wednesday, following the update that five of the eight critical issues had already been resolved (notes.txt, sketch.png).
3. Hold the AWS load-testing setup meeting scheduled for tomorrow and proceed with environment setup by David and Mike (notes.txt).
4. Deliver the final app screenshots by December 18 so Marketing has them ahead of the December 20 press kit deadline (notes.txt, sketch.png).

The next team check-in is scheduled for January 3 (notes.txt). The team also needs to account for the holiday deployment freeze, which runs from December 23, 2024, at 5:00 PM through January 2, 2025, at 9:00 AM, and complete the required pre-freeze checklist before December 23 (notes.txt, deployment-freeze-policy.pdf).
