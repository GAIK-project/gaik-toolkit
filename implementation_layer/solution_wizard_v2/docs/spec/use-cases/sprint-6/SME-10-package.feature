@sprint-6 @SME-10 @epic-15 @gate-4
Feature: Prepare a ready-to-share solution package
  As an SME manager
  I want the wizard to prepare a complete solution package
  So that I can share it with a developer, consultant, vendor, or decision-maker

  Background:
    Given I am logged in to the Solution Wizard
    And my prototype has been tested and approved at Gate 3

  Scenario: Package includes all approved artefacts
    When the wizard prepares the solution package
    Then the package includes:
      | artefact              |
      | approved prototype    |
      | solution plan         |
      | prompts and settings  |
      | workflow diagrams     |
      | tests                 |
      | documentation         |
    And all items match the approved blueprint version

  Scenario: Documentation for business and technical audiences
    When I open the generated documentation
    Then business documentation explains purpose, benefits, and how to use the solution
    And technical documentation explains how to run, extend, and evaluate the solution

  Scenario: Package is reusable for future work
    Given the solution package is complete
    When I return to the project later
    Then I can reuse the package as a baseline for improvements or full implementation

  Scenario: Gate 4 — full package validation
    Given the full installable package is generated
    When Gate 4 runtime validation runs in the wizard UI
    Then the test suite and evaluation scripts execute successfully
    And the package is marked production-ready only after Gate 4 passes

  Scenario: Example — share hospital extraction package with IT
    Given my approved solution extracts clinical fields from voice and PDF inputs
    When the package is generated
    Then the business guide explains reviewer workflow for nurses and doctors
    And the developer guide explains how to run extraction against new patient documents
