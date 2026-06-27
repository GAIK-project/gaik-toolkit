@example @sprint-2 @SME-1 @SME-3 @SME-7
Feature: Example — Apple Jam guest description maintenance reporting
  Source: Dmitry — Input from user (Apple Jam guest description files)
  Concrete SME scenario with reference lists for equipment, fault types, and reasons.

  Background:
    Given I am logged in to the Solution Wizard
    And guest description reference data is available:
      | list              | example entries                          |
      | equipment         | COOK-POT-01 Stainless steel cooking pot  |
      | fault types       | FT-003 No heating, FT-008 Wrong reading    |
      | possible reasons  | RS-001 Power supply problem              |
    And I have started a session titled "Apple Jam equipment faults"

  Scenario: Observer reports fault by voice using guest context
    When I describe my use case in chat:
      """
      In our small jam production business, staff observe equipment faults during
      production. Reporting takes too long with forms. Observers should describe
      faults by voice. AI should map the report to our equipment list, fault types,
      and possible reasons. A technician reviews before the case is prioritized.
      """
    Then the wizard summarizes a voice-to-structured maintenance case for a small food producer
    And the wizard uses guest reference lists when suggesting valid equipment and fault categories

  Scenario: Voice report maps to reference equipment ID
    Given an observer says the cooking pot is not heating during jam production
    When the wizard configures structured output
    Then output may include equipment ID "COOK-POT-01" when unambiguous
    And fault type "FT-003 No heating" when supported by the utterance
    And possible reason only when explicitly stated or left empty otherwise

  Scenario: Technician enriches case after observer report
    Given a structured observer report exists
    When a technician reviews the case
    Then they can add urgency, risk assessment, and technical details
    And a senior technician can set priority for resolution
  # Pattern aligns with Dmitry — Solution wizard_test 20.6_chat.docx maintenance dialogue

  Scenario: Incomplete observer description triggers follow-up
    Given the observer voice note does not mention which equipment failed
    When the wizard runs completeness check
    Then the wizard asks a follow-up question about equipment or location
    Or leaves equipment fields empty rather than guessing
