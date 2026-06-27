@sprint-2 @SME-6 @epic-12 @gate-2
Feature: Show the workflow visually
  As an SME manager
  I want to see a simple visual workflow
  So that I can review the solution with colleagues or decision-makers

  Background:
    Given I am logged in to the Solution Wizard
    And Gate 1 specification approval is complete
    And an executable JSON blueprint exists for my session

  Scenario: Wizard generates a process diagram
    When the wizard generates the visual workflow
    Then I see a diagram from input to final output
    And the diagram highlights main processing and review steps
    And the diagram avoids unnecessary low-level technical detail in the default view

  Scenario: Workflow is visible in the workspace centre
    When I open the Workflow tab in the workspace
    Then the diagram is shown in the central workspace area
    And I can review it alongside the chat

  Scenario: Gate 2 — workflow approval
    Given the BPMN or simplified workflow view is displayed
    When I approve Gate 2
    Then the workflow is marked approved for PoC scaffolding
    But if I request workflow changes
    Then changes are applied to the JSON blueprint first
    And the visual workflow is regenerated from the updated blueprint

  Scenario: Change in workflow updates plan before artefacts
    Given I request a change to a workflow step in chat
    When the wizard accepts the change as a business intent change
    Then the solution plan and JSON blueprint are updated before diagrams are regenerated
