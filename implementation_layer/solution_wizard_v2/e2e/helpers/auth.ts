import type { Page } from "@playwright/test";

export const DEV_USERS = {
  primary: { email: "dev@gaik.local", password: "gaik" },
  secondary: { email: "dev2@gaik.local", password: "gaik2" },
} as const;

export type DevUser = (typeof DEV_USERS)[keyof typeof DEV_USERS];

/** @deprecated use DEV_USERS.primary */
export const DEV_EMAIL = DEV_USERS.primary.email;
/** @deprecated use DEV_USERS.primary */
export const DEV_PASSWORD = DEV_USERS.primary.password;

/** Log in via dev-auth form (NEXT_PUBLIC_DEV_AUTH=true). */
export async function loginAsDev(page: Page, user: DevUser = DEV_USERS.primary) {
  await page.goto("/login");
  await page.getByLabel("Sähköposti").fill(user.email);
  await page.getByLabel("Salasana").fill(user.password);
  await page.getByRole("button", { name: "Kirjaudu" }).click();
  await page.waitForURL("/");
}

/**
 * Opens the menu of the sidebar's account row (the language, the privacy
 * notice, signing out), unless it is open already. The full column and the
 * rail each have their own button; the one in view is pressed.
 */
export async function openAccountMenu(page: Page) {
  const items = page.locator('[data-testid="account-menu-items"]:visible');
  if ((await items.count()) === 0) {
    await page.locator('[data-testid="account-menu"]:visible').click();
  }
  await items.waitFor();
  return items;
}

export async function signOutDev(page: Page) {
  const menu = await openAccountMenu(page);
  await menu.getByRole("button", { name: "Kirjaudu ulos" }).click();
  await page.waitForURL("/login");
}
