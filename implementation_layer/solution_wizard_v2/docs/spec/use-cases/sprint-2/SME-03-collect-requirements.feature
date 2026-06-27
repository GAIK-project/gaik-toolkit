@sprint-2 @SME-3 @epic-12
Feature: Collect only the necessary requirements
  As an SME manager
  I want the wizard to ask only the questions needed to configure the solution
  So that the setup process feels simple and not overwhelming

  Background:
    Given I am logged in to the Solution Wizard
    And I have approved a solution type for my session

  Scenario: Questions are asked in small steps
    When the wizard collects requirements
    Then the wizard asks one thematic topic at a time
    And the wizard does not present a long questionnaire on a single screen

  Scenario: Wizard focuses on practical information
    When the wizard asks follow-up questions
    Then questions cover practical topics such as:
      | topic              |
      | input files        |
      | expected output    |
      | users and reviewers|
      | quality needs      |
      | business constraints|
    And the wizard skips questions already answered in my earlier messages

  Scenario: Follow-up only when information is missing
    Given I stated that output must be in Finnish
    When the wizard checks requirement completeness
    Then the wizard does not ask again which language the output should use
    But the wizard asks a follow-up if I have not described who approves the output

  Scenario: Short summary before continuing
    Given I have answered the questions for the current requirement round
    When the wizard completes that round
    Then the wizard shows a short summary of what it understood
    And the wizard asks me to confirm before moving to specification

  Scenario: Completeness gate — missing critical field
    Given my use case requires structured extraction
    And I have not described which fields must appear in the output
    When the wizard runs the completeness check
    Then the wizard asks specifically for required output fields
    And the wizard does not silently assume default fields
