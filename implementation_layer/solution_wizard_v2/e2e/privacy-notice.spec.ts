import { test, expect } from "@playwright/test";
import { loginAsDev, openAccountMenu } from "./helpers/auth";

test("the privacy notice opens from the sign-in page without signing in", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("privacy-link").click();
  await page.waitForURL("/privacy");
  await expect(page.getByRole("heading", { name: "Tietosuojaseloste", level: 1 })).toBeVisible();
  await expect(page.getByTestId("privacy-draft-note")).toBeVisible();
});

test("the sign-in page links back to the GAIK demos", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("link", { name: "GAIK-demot" })).toHaveAttribute(
    "href",
    "https://gaik-demo.2.rahtiapp.fi/",
  );
});

test("a signed-in user finds it in the sidebar, and a way back from it", async ({ page }) => {
  await loginAsDev(page);
  await page.goto("/");
  // In the menu of the account row at the sidebar's foot.
  await openAccountMenu(page);
  await page.getByTestId("sidebar").getByTestId("privacy-link").click();
  await page.waitForURL("/privacy");
  await expect(page.getByRole("heading", { name: "Tietosuojaseloste", level: 1 })).toBeVisible();
  // The notice is outside the shell: its own link leads back to the wizard.
  await page.getByRole("link", { name: "Takaisin" }).click();
  await page.waitForURL("/");
  await expect(page.getByTestId("start-view")).toBeVisible();
});

test("the help page is in the same menu, and leads back to the wizard", async ({ page }) => {
  await loginAsDev(page);
  await page.goto("/");
  await openAccountMenu(page);
  await page.getByTestId("sidebar").getByTestId("help-link").click();
  await page.waitForURL("/help");
  await expect(page.getByRole("heading", { name: "Ohje", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Vaiheet ja gatet" })).toBeVisible();
  await page.getByRole("link", { name: "Takaisin" }).click();
  await page.waitForURL("/");
  await expect(page.getByTestId("start-view")).toBeVisible();
});

test("the help page needs a signed-in user", async ({ page }) => {
  await page.goto("/help");
  await page.waitForURL(/\/login/);
});
