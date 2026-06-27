@sprint-2 @SME-2 @epic-12
Feature: Choose the right type of GenAI solution
  As an SME manager
  I want the wizard to suggest the most suitable solution type
  So that I do not need to know which GenAI tools or modules are needed

  Background:
    Given I am logged in to the Solution Wizard
    And I have confirmed my business problem summary

  Scenario: Wizard suggests a solution type in plain language
    When the wizard analyzes my confirmed problem
    Then the wizard suggests a solution type such as one of:
      | type                  |
      | document processing   |
      | audio processing      |
      | image-based extraction|
      | knowledge search      |
      | chatbot               |
      | report generation     |
      | validation            |
    And the wizard explains the recommendation in simple business terms

  Scenario: Manager can accept the suggested solution type
    Given the wizard suggested "audio processing" for my voice reporting case
    When I accept the suggestion
    Then the wizard records audio processing as the approved solution type
    And the wizard continues to requirement collection

  Scenario: Manager can correct the suggested solution type
    Given the wizard suggested "document processing"
    When I say the input is primarily voice messages not typed forms
    Then the wizard updates the solution type to "audio processing"
    And the wizard confirms the correction before continuing

  Scenario: Wizard supports combined solution types
    Given my use case needs transcription followed by structured extraction
    When the wizard recommends a combined pipeline
    Then the wizard explains the steps in business language
    And the wizard does not expose internal module names unless I ask for details

  Scenario: Example — hospital voice plus PDF (Umair)
    Given I confirmed a hospital admissions documentation problem
    When the wizard classifies inputs as voice notes and PDF referral letters
    Then the wizard suggests a combined audio and document processing solution
    And the wizard explains that structured clinical fields will be extracted for review
