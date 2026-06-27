@example @sprint-2 @SME-1 @SME-2 @SME-3 @SME-7
Feature: Example — Facilities maintenance voice to structured tickets
  Source: Umair — solution wizard example use cases.docx (use case 1)
  End-to-end validation scenario linking SME stories for a Finnish maintenance team.

  Background:
    Given I am logged in to the Solution Wizard
    And I have started a new session titled "Facilities maintenance voice reporting"

  Scenario: SME describes voice-to-ticket maintenance workflow
    When I describe my use case in chat:
      """
      We run a facilities maintenance team. Our field technicians report faults
      they observe daily. They describe what's broken, where it is, and how
      urgent it is. Currently they type into our maintenance system by hand.
      It is slow and details get missed. We want technicians to report faults
      through voice messages in Finnish, converted into structured maintenance
      tickets in Finnish that a supervisor checks before they enter the system.
      """
    Then the wizard summarizes a maintenance voice-reporting problem
    And the wizard suggests an audio processing solution with human supervisor review
    And the wizard asks practical follow-up questions about users, inputs, and ticket fields

  Scenario: Output rules for maintenance tickets
    Given requirement collection is complete for the maintenance use case
    When the wizard defines expected output
    Then structured ticket fields include location, equipment, fault description, and urgency
    And output language is Finnish
    And a supervisor review step is included before system submission

  Scenario: Gate 1 demo path for Sprint 2 MVP
    Given specifications and component selection are complete
    When I approve Gate 1
    Then I can view a read-only workflow and JSON blueprint for the maintenance pipeline
    And the chat history for this example remains in my session
