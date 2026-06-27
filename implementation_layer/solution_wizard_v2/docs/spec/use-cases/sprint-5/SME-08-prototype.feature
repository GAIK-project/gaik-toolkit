@sprint-5 @SME-8 @epic-14 @gate-3
Feature: Create a small working prototype
  As an SME manager
  I want the wizard to create a small working prototype
  So that I can test the idea before investing more effort

  Background:
    Given I am logged in to the Solution Wizard
    And Gate 2 workflow approval is complete
    And my session has an approved JSON blueprint

  Scenario: Minimal runnable prototype is generated
    When the wizard scaffolds the PoC
    Then a minimal runnable prototype is created from the approved solution plan
    And the prototype includes prompts, settings, required files, and run instructions

  Scenario: Wizard explains how to test with sample data
    When the PoC is ready
    Then the wizard explains how to test using sample or real business data
    And the instructions are understandable without developer tooling expertise

  Scenario: Prototype focuses on proving business value
    Given the PoC is generated
    Then the prototype demonstrates the core business outcome
    And the prototype is not a full production system

  Scenario: Gate 3 — run PoC in the wizard UI
    Given the PoC tab is available in the workspace
    When I run the PoC from the wizard UI
    Then I see run status and output or logs in the workspace
    And I can share results with the wizard for refinement

  Scenario: Example — maintenance voice reporting PoC
    Given my approved plan converts Finnish voice fault reports to structured tickets
    When I run the PoC with a sample voice input
    Then I receive structured output matching the approved field schema
    And a supervisor can review the result before system submission
