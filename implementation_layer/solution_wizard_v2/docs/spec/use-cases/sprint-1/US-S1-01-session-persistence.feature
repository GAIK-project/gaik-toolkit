@sprint-1 @US-S1-01 @epic-3
Feature: Session persistence — create, save, and resume
  As a logged-in wizard user
  I want to create a session, leave, and resume later with my progress intact
  So that I can configure a solution over multiple visits

  Background:
    Given I am logged in to the Solution Wizard web UI
    And the wizard API and database are running in the dev environment

  Scenario: Create a new session and see it in my session list
    When I start a new wizard session with title "Maintenance voice reporting"
    Then the session appears in "My sessions"
    And the session is owned by my user account

  Scenario: Resume a session after closing the browser
    Given I have an in-progress session at workflow step 3
    And the session has chat history and a seed blueprint in storage
    When I close the browser and log in again later
    And I open the session from "My sessions"
    Then I see the same workflow step as before
    And I see the previous chat messages
    And I see the saved blueprint state

  Scenario: Session survives API restart
    Given I have an in-progress session with saved state
    When the wizard API process is restarted
    And I open the session again
    Then my session state is unchanged

  Scenario: Another user cannot see my sessions
    Given user "Alice" has a wizard session
    When user "Bob" is logged in
    Then Bob does not see Alice's session in "My sessions"
    And Bob cannot open Alice's session by direct URL

  Scenario: Runnable in Docker Compose dev stack
    Given the Docker Compose stack is up with Postgres, wizard API, and UI
    When I complete the create and resume flow above
    Then all steps succeed without manual database intervention
