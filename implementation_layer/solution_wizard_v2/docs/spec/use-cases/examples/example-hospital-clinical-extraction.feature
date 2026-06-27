@example @sprint-2 @SME-1 @SME-3 @SME-7
Feature: Example — Hospital admissions voice and PDF to clinical record
  Source: Umair — solution wizard example use cases.docx (use case 2)
  Combined audio and document processing with strict empty-field rules.

  Background:
    Given I am logged in to the Solution Wizard
    And I have started a new session titled "Hospital admissions documentation"

  Scenario: SME describes hybrid voice and PDF clinical extraction
    When I describe my use case in chat:
      """
      Doctors record patient notes verbally after examination. Staff also receive
      referral letters and PDFs from external clinics. We manually enter information
      into our patient management system. We want voice notes transcribed, combined
      with PDF documents, and key clinical information extracted into a structured
      record reviewed by a supervisor or senior nurse before submission.
      """
    Then the wizard suggests combined audio and document processing
    And the wizard asks who reviews extracted records before submission

  Scenario Outline: Required clinical fields
    Given the wizard collects output field requirements
    When I confirm the clinical field list
    Then the output schema includes "<field>"

    Examples:
      | field                        |
      | full name                    |
      | date of birth                |
      | known allergies                |
      | date and time of admission   |
      | main symptom                   |
      | current medications with dosage|
      | suspected diagnosis            |
      | immediate management plan      |

  Scenario: Unmentioned fields remain blank
    Given a referral PDF and voice note do not mention the referring doctor
    When the wizard documents extraction rules
    Then "referring doctor" must be left blank in output
    And the wizard must not infer missing clinical values

  Scenario: Supervisor review before submission
    Given structured extraction output is produced in a PoC or preview
    When a senior nurse reviews the record
    Then they can approve or reject before data enters the patient management system
