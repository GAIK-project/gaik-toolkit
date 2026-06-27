@sprint-2 @SME-7 @epic-12
Feature: Define the expected output
  As an SME manager
  I want to define what the final output should look like
  So that the solution produces information in a useful format for my business

  Background:
    Given I am logged in to the Solution Wizard
    And I am configuring a structured-output use case

  Scenario: Wizard asks for required fields or report sections
    When the wizard collects output requirements
    Then the wizard asks which fields, sections, or report parts are needed
    And the wizard offers examples if I am unsure

  Scenario: Wizard shows an example of expected output
    Given I have listed my required output fields
    When the wizard prepares the output specification
    Then the wizard shows an example structure of the expected output
    And I can approve or change the output format

  Scenario: Missing values stay empty — hospital example (Umair)
    Given my use case is clinical information extraction
    And a field such as "referring doctor" is not mentioned in the inputs
    When the wizard documents output rules
    Then the rule states that missing fields must be left blank
    And the wizard must not invent values for missing fields

  Scenario: Ordered fields with defaults — factory safety example (Umair)
    Given my use case is Finnish safety observation reporting
    When the wizard captures output field rules
    Then fields are returned in the agreed order
    And predefined default values apply only where explicitly specified in requirements
    And otherwise empty string is returned when a field cannot be determined

  Scenario: Guest description reference data — Apple Jam equipment fault
    Given guest description reference lists equipment, fault types, and possible reasons
    When I configure output for a jam factory maintenance report
    Then the wizard can use reference lists to suggest valid equipment IDs and fault categories
    And extracted output aligns with the agreed field structure for supervisor review

  # Mapping note: output requirements are also collected during SME-3 rounds (V1 phase 2);
  # extraction schema is designed before blueprint generation (V1 phase 5).
