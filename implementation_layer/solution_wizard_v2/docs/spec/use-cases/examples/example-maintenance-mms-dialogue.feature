@example @sprint-2 @SME-1 @SME-2 @SME-3
Feature: Example — Maintenance MMS dialogue pattern from wizard test
  Source: Dmitry — Solution wizard_test 20.6_chat.docx
  Validates wizard questioning behaviour for equipment fault reporting (V1 reference flow).

  Background:
    Given I am logged in to the Solution Wizard
    And I have started a new session

  Scenario: Initial vague request triggers clarifying questions
    When I say "We want to improve our Maintenance Management System and make equipment fault reporting quicker with AI"
    Then the wizard classifies the case as audio or document structured reporting
    And the wizard asks how technicians currently report faults
    And the wizard asks who reports faults and who reviews them

  Scenario: Pain point shifts solution toward voice input
    Given the wizard asked about current reporting process
    When I explain observers avoid reporting because forms take too much time
    And I say observers should describe faults by audio instead of typing
    Then the wizard updates the recommended pattern to voice-based structured reporting
    And the wizard asks about language and required structured fields

  Scenario: Three-role process is preserved in requirements
    Given the process has observers, technicians, and senior technicians
    When requirements are summarized
    Then the plan includes observer initial report
    And technician on-site assessment and enrichment
    And senior technician priority decision
