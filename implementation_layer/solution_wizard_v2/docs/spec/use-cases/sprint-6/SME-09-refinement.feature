@sprint-6 @SME-9 @epic-15 @gate-3
Feature: Improve the prototype after testing
  As an SME manager
  I want to give feedback after testing the prototype
  So that the wizard can improve the solution step by step

  Background:
    Given I am logged in to the Solution Wizard
    And I have run the PoC at least once

  Scenario: Manager shares test results and comments
    When I provide feedback after a PoC run
    Then I can share test results, errors, or improvement comments in chat
    And the wizard acknowledges what kind of change is requested

  Scenario: Business change updates plan before regeneration
    Given my feedback changes approved business intent
    When the wizard classifies the change as a business change
    Then the solution plan and blueprint are updated first
    And affected files are regenerated only after I approve the updated plan

  Scenario: Technical fix without business intent change
    Given my feedback is a technical fix that does not change approved business goals
    When the wizard classifies the change as an implementation fix
    Then the wizard patches the PoC directly
    And the approved business specification remains unchanged

  Scenario: Repeat test until acceptable
    Given I have submitted refinement feedback
    When the wizard applies the approved changes
    Then I can run the PoC again
    And I can repeat the test-and-feedback cycle until the result is acceptable

  Scenario: Example — incomplete maintenance ticket extraction
    Given my PoC output missed the urgency field for a voice report
    When I report the missing field after testing
    Then the wizard determines whether the schema, prompt, or extraction logic must change
    And I review the proposed fix before the next PoC run
