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

test("crawl page shows run_id and an expandable run log", async ({ page }) => {
  await page.goto("/ui/crawl");
  await page.getByRole("button", { name: "Crawl" }).click();
  await expect(page.getByTestId("run-id")).toBeVisible();
  await page.getByText("Run log", { exact: true }).click();
  await expect(page.getByTestId("run-log-line").first()).toBeVisible();
  await expect(page.getByTestId("run-log-line").last()).toContainText(
    "run end",
  );
});

test("failed crawl shows run_id from the error body and its run log", async ({
  page,
}) => {
  await page.goto("/ui/crawl");
  await page.getByLabel("Page URL").fill("https://nowhere.invalid");
  await page.getByRole("button", { name: "Crawl" }).click();
  await expect(page.getByRole("alert")).toContainText("fetch_failed");
  await expect(page.getByTestId("run-id")).toBeVisible();
  await page.getByText("Run log", { exact: true }).click();
  await expect(page.getByTestId("run-log-line").last()).toContainText(
    "fetch_failed",
  );
});

test("chat: the starter prompt streams a blocked write, contained email and simulated order", async ({
  page,
}) => {
  await page.goto("/ui");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav.getByRole("link", { name: "Chat" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Crawl" })).toHaveCount(0);
  await nav.getByRole("link", { name: "Chat" }).click();

  await expect(
    page.getByRole("heading", { name: "Shopping agent" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Order 2 reams of A4/ }).click();
  await expect(page.getByLabel("Task for the agent")).toBeFocused();

  const steps = page.getByTestId("chat-step");
  const remember = steps.filter({ hasText: "Quarantined as BLOCKED" });
  await expect(remember).toBeVisible({ timeout: 15_000 });
  await expect(remember.getByText("Blocked", { exact: true })).toBeVisible();
  await expect(remember).toContainText("Risk 100");
  await expect(page.locator("[data-tool=send_email]")).toContainText(
    "Egress contained",
    { timeout: 15_000 },
  );
  await expect(page.locator("[data-tool=place_order]")).toContainText(
    "Simulated",
    { timeout: 15_000 },
  );
  await expect(page.getByTestId("chat-done")).toContainText("network none", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("chat-reply")).toContainText("SIM-7Q2K9");
  await expect(page.getByLabel("Task for the agent")).toBeFocused();

  await remember.getByRole("link", { name: "Open in review" }).click();
  await expect(page.getByTestId("inspector")).toContainText(
    "card details to billing@paper-deals.example",
  );
});
