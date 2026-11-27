import { expect, test } from "@playwright/test";

test("quarantine page lists mock sessions and rows", async ({ page }) => {
  const response = await page.goto("/ui");
  expect(response?.ok()).toBe(true);
  await expect(page).toHaveTitle(/Memory Quarantine/);
  await expect(page.getByRole("heading", { name: "Quarantine" })).toBeVisible();
  await expect(page.getByTestId("quarantine-row").first()).toBeVisible();
});

test("review: inspect, require a reason, override and verify the receipt", async ({
  page,
}) => {
  await page.goto("/ui");
  const inspector = page.getByTestId("inspector");
  await expect(inspector.getByTestId("judge-boost")).toContainText("115");
  await expect(inspector.getByTestId("failed-rules").locator("li")).toHaveCount(
    4,
  );
  await expect(inspector.getByText("9/13 passed").first()).toBeVisible();

  await inspector
    .getByRole("button", { name: "Override", exact: true })
    .click();
  await expect(inspector.getByRole("alert")).toContainText("need a reason");
  await inspector
    .getByLabel(/Reason to override/)
    .fill("Checked with the sales lead");
  await inspector
    .getByRole("button", { name: "Override", exact: true })
    .click();
  await expect(page.getByTestId("receipt-status")).toContainText(
    "Signature valid",
  );
  await page.getByRole("button", { name: "Verify a tampered copy" }).click();
  await expect(page.getByText("Tampered copy rejected")).toBeVisible();
});

test("review: pending judge shows Evaluating, failed judge shows escalation", async ({
  page,
}) => {
  await page.goto("/ui");
  await page
    .getByTestId("quarantine-row")
    .filter({ hasText: "discount sheet" })
    .getByRole("button")
    .click();
  await expect(page.getByTestId("judge-evaluating")).toBeVisible();
  await page
    .getByTestId("quarantine-row")
    .filter({ hasText: "monthly billing" })
    .getByRole("button")
    .click();
  await expect(page.getByTestId("judge-failed")).toContainText("Escalated");
});

test("review: purge goes through a confirm dialog", async ({ page }) => {
  await page.goto("/ui");
  await page
    .getByTestId("quarantine-row")
    .filter({ hasText: "renewal call" })
    .getByRole("button")
    .click();
  await page.getByRole("button", { name: "Purge", exact: true }).click();
  await page.getByRole("button", { name: "Purge and sign" }).click();
  await expect(page.getByTestId("receipt-status")).toContainText(
    "Signature valid",
  );
});

test("audit page reports chain_valid", async ({ page }) => {
  await page.goto("/ui/audit");
  await expect(page.getByTestId("chain-status")).toContainText(
    "chain_valid: true",
  );
});

test("crawl page submits a URL and shows the sandbox result", async ({
  page,
}) => {
  await page.goto("/ui/crawl");
  await expect(
    page.getByRole("heading", { name: "Crawl a page" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Crawl" }).click();
  await expect(page.getByRole("heading", { name: "Mock page" })).toBeVisible();
  await expect(page.getByText("network none")).toBeVisible();
});
