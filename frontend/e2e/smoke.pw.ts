import { expect, test } from "@playwright/test";

test("quarantine page lists mock sessions and rows", async ({ page }) => {
  const response = await page.goto("/ui");
  expect(response?.ok()).toBe(true);
  await expect(page).toHaveTitle(/Memory Quarantine/);
  await expect(page.getByRole("heading", { name: "Quarantine" })).toBeVisible();
  await expect(page.getByTestId("quarantine-row").first()).toBeVisible();
});

test("audit page reports chain_valid", async ({ page }) => {
  await page.goto("/ui/audit");
  await expect(page.getByTestId("chain-status")).toContainText(
    "chain_valid: true",
  );
});
