@sprint-2 @SME-5 @epic-12 @gate-1
Feature: Create a simple solution plan
  As an SME manager
  I want the wizard to create a clear solution plan
  So that I can understand what the solution will do before it is built

  Background:
    Given I am logged in to the Solution Wizard
    And component selection is complete for my session

  Scenario: Structured solution plan is generated
    When the wizard generates the solution plan
    Then the plan describes:
      | section      |
      | inputs       |
      | process steps|
      | outputs      |
      | checks       |
      | assumptions  |
    And the plan is written in understandable business language

  Scenario: Manager approves the plan before files are generated
    Given the solution plan is displayed in the workspace
    When I review the plan
    Then I can approve the plan
    Or I can request changes in chat before any blueprint files are created

  Scenario: Gate 1 — specification approval
    Given the wizard has produced business, technical, and target output specifications
    When I approve Gate 1
    Then the session advances to schema and blueprint generation
    But if I reject Gate 1
    Then the wizard returns to requirement or specification revision
    And no blueprint is marked as approved

  Scenario: Rejected plan returns to dialogue
    Given I request changes to the solution plan
    When I describe what should be different
    Then the wizard updates the plan
    And the wizard asks for approval again before continuing
