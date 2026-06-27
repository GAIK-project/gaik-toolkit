@example @sprint-2 @SME-1 @SME-3 @SME-7
Feature: Example — Factory safety observation by voice (Finnish)
  Source: Umair — solution wizard example use cases.docx (use case 3)
  Mobile web reporting with ordered Finnish fields and controlled defaults.

  Background:
    Given I am logged in to the Solution Wizard
    And I have started a new session titled "Factory safety observations"

  Scenario: Worker reports safety observation by voice on mobile
    When I describe my use case in chat:
      """
      Workers on the factory floor must report safety observations and incidents.
      Finding a computer is slow and many areas have no terminal nearby.
      We want workers to open a web app on their phone, speak naturally in Finnish,
      and have AI transcribe and extract structured information. The worker reviews
      the result, confirms or corrects it, and a supervisor saves it to our ERP.
      """
    Then the wizard suggests audio processing with worker validation and supervisor approval
    And the wizard confirms both voice input and structured output are in Finnish

  Scenario Outline: Safety form fields returned in fixed order
    Given output field rules are configured for the factory use case
    When a voice report is processed
    Then field "<field>" appears in the structured output in the agreed order

    Examples:
      | field                                      |
      | observation type                           |
      | observation subtype                        |
      | date                                       |
      | employer                                   |
      | reporter name                              |
      | employee type                              |

  Scenario: Default only where explicitly defined
    Given the observation type cannot be determined from the voice input
    When the extraction rules specify default "safety observation" for that field
    Then that default is applied
    But for fields without an explicit default rule
    Then an empty string is returned instead of a guessed value

  Scenario: Worker confirms before supervisor review
    Given the worker sees extracted fields on screen after speaking
    When the worker corrects a field and submits
    Then the corrected values are sent for supervisor review
    And only after supervisor approval is the report saved to the ERP system
