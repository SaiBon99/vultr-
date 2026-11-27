import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Strict: any axe violation fails. Starter templates ship with violations, so this is not part of check:full.
// Run `test:a11y` once your own markup replaces the template, then add it to the check.
// Axe finds about half of WCAG issues; keyboard, focus and screen reader checks stay manual.
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

test("home page has no axe violations", async ({ page }) => {
  await page.goto("/ui");
  await page.getByTestId("quarantine-row").first().waitFor(); // SPA: wait for client render
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
});

test("crawl page has no axe violations", async ({ page }) => {
  await page.goto("/ui/crawl");
  await page.getByRole("heading", { name: "Crawl a page" }).waitFor(); // SPA: wait for client render
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
});

// A hide rule that loses to a later display rule leaves hidden elements on screen.
test("no hidden element is rendered", async ({ page }) => {
  await page.goto("/ui");
  const shown = await page.evaluate(() =>
    [...document.querySelectorAll("[hidden]")]
      .filter((el) => getComputedStyle(el).display !== "none")
      .map((el) => el.outerHTML.slice(0, 80)),
  );
  expect(shown).toEqual([]);
});
