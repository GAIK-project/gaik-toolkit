@sprint-2 @SME-1 @epic-12
Feature: Describe a business problem
  As an SME manager
  I want to explain my business problem in simple language
  So that the wizard can help me turn it into a practical GenAI solution idea

  Background:
    Given I am logged in to the Solution Wizard
    And I have started a new configuration session

  Scenario: Wizard asks what problem to solve
    When I open the wizard chat
    Then the wizard asks what business or operational problem I want to solve
    And the wizard asks who will use the solution
    And the wizard asks what result I expect

  Scenario: Wizard avoids technical jargon in early dialogue
    When I describe my problem in plain language
    Then the wizard does not require me to name GAIK components or modules
    And the wizard responds in business-friendly language

  Scenario: Wizard summarizes the problem for confirmation
    Given I have described a maintenance reporting problem in plain language
    When the wizard has enough context to understand my intent
    Then the wizard presents a short summary of my business problem
    And the wizard asks me to confirm or correct the summary

  Scenario: Example input — facilities maintenance (Umair)
    When I enter:
      """
      We run a facilities maintenance team. Technicians report faults daily.
      They currently type reports by hand. We want voice messages in Finnish
      converted into structured maintenance tickets a supervisor checks first.
      """
    Then the wizard summarizes a maintenance voice-to-ticket use case
    And the wizard does not ask me to choose a transcriber or extractor by name
