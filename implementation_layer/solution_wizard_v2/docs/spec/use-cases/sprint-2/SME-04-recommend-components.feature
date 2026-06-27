@sprint-2 @SME-4 @epic-12
Feature: Recommend suitable solution components
  As an SME manager
  I want the wizard to choose suitable GAIK components for me
  So that I do not need technical knowledge to design the solution

  Background:
    Given I am logged in to the Solution Wizard
    And I have an approved requirement specification for my session

  Scenario: Wizard selects components from approved requirements
    When the wizard performs component selection
    Then the wizard selects GAIK components or modules that match my approved requirements
    And each selection is linked to a requirement rationale

  Scenario: Selection is explained in plain language
    When the wizard presents its component selection
    Then the wizard explains why each part of the pipeline fits my use case
    And the explanation avoids unnecessary implementation detail

  Scenario: Wizard asks only about business-impacting options
    Given a selected component has behaviour-changing options
    When the option affects my business outcome
    Then the wizard asks me to choose or confirm that option
    But the wizard does not ask about internal defaults that do not affect my outcome

  Scenario: Unsupported requirement is stated clearly
    Given my requirement cannot be fulfilled with available GAIK components
    When the wizard completes selection
    Then the wizard states clearly what cannot be done with current toolkit scope
    And the wizard suggests an alternative or scope reduction if possible

  Scenario: Example — voice to structured maintenance ticket
    Given my approved requirements describe Finnish voice fault reporting
    When the wizard selects the pipeline
    Then the selection includes transcription and structured extraction suitable for maintenance tickets
    And the wizard explains the pipeline as "speech to structured report" not as internal package names
