import { expect, test } from "@playwright/test";

// Baselines are created with `test:visual:update`; run `test:visual` to compare.
test("home page matches baseline", async ({ page }) => {
  await page.goto("/ui");
  await expect(page).toHaveScreenshot("home.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.01,
  });
});
