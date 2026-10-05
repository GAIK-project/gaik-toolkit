import type { Page } from "@playwright/test";

export const DEV_EMAIL = "dev@gaik.local";
export const DEV_PASSWORD = "gaik";

/** Log in via dev-auth form (NEXT_PUBLIC_DEV_AUTH=true). */
export async function loginAsDev(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Sähköposti").fill(DEV_EMAIL);
  await page.getByLabel("Salasana").fill(DEV_PASSWORD);
  await page.getByRole("button", { name: "Kirjaudu" }).click();
  await page.waitForURL("/");
}
