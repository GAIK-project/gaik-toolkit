import type { Locator, Page } from "@playwright/test";

/** The two choices of a first message, in the tools row of the message field. */
export type StartChoice = "chat-background" | "chat-pace";

/** The pill that names what is chosen and opens the choice's menu. */
export function choicePill(page: Page, choice: StartChoice): Locator {
  return page.getByTestId(choice).getByRole("button");
}

/** One option of an open menu, by its name ("Tekninen", not "En ole tekninen"). */
export function choiceOption(page: Page, choice: StartChoice, name: string): Locator {
  return page
    .getByTestId(choice)
    .getByRole("menuitemradio")
    .filter({ has: page.getByText(name, { exact: true }) });
}

/** Opens the choice's menu, unless it is open, and presses `name` in it. */
export async function choose(page: Page, choice: StartChoice, name: string): Promise<void> {
  const pill = choicePill(page, choice);
  if ((await pill.getAttribute("aria-expanded")) !== "true") await pill.click();
  await choiceOption(page, choice, name).click();
}
