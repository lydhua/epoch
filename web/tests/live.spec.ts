import { test, expect } from "@playwright/test";

test("real API: collection → problem → attempt → next review and history", async ({
  page,
}) => {
  test.skip(
    !process.env.EPOCH_E2E_TOKEN,
    "Set EPOCH_E2E_TOKEN for a disposable local/test API.",
  );
  await page.goto("/");
  await page.getByText("Connect to your local API", { exact: true }).click();
  await page
    .getByLabel("Local bearer token")
    .fill(process.env.EPOCH_E2E_TOKEN!);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "New collection" }).click();
  const suffix = crypto.randomUUID().slice(0, 8);
  await page.getByLabel("Collection name").fill(`Practice preview ${suffix}`);
  await page
    .getByRole("button", { name: "Create collection", exact: true })
    .click();
  await page
    .getByRole("button", { name: `Practice preview ${suffix}`, exact: true })
    .click();
  await page.getByRole("button", { name: "Add a problem" }).click();
  await page.getByLabel("Problem title").fill(`Valid Parentheses ${suffix}`);
  await page
    .getByLabel("Problem link")
    .fill(`https://leetcode.com/problems/synthetic-${suffix}/`);
  await page
    .getByRole("dialog")
    .getByRole("combobox", { name: /^Difficulty/ })
    .selectOption("easy");
  await page.getByRole("button", { name: "Add problem", exact: true }).click();
  await page
    .getByRole("button", { name: `Practice Valid Parentheses ${suffix}` })
    .click();
  await page.getByLabel("Manual / corrected minutes").fill("8");
  await page.getByRole("button", { name: "Save attempt", exact: true }).click();
  await expect(page.getByText(/Attempt saved. Next practice:/)).toBeVisible();
  await expect(page.getByText(/Goal:|Last: 8 min/)).toBeVisible();
  await page
    .getByRole("button", { name: `Practice Valid Parentheses ${suffix}` })
    .click();
  await page.getByText("Attempt history · 1", { exact: true }).click();
  await expect(page.getByText("Independent", { exact: true })).toBeVisible();
});
