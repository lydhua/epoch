import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { elapsed, pause, fresh, clockChanged } from "../src/timer";

const owner = "11111111-1111-4111-8111-111111111111";
const itemId = "22222222-2222-4222-8222-222222222222";
const collectionId = "33333333-3333-4333-8333-333333333333";
const collection = {
  id: collectionId,
  owner_id: owner,
  name: "Problem patterns",
};
const item = {
  id: itemId,
  collection_id: collectionId,
  title: "Two Sum",
  content: {
    type: "coding_problem",
    url: "https://leetcode.com/problems/two-sum/",
    difficulty: "easy",
  },
  tags: ["Arrays"],
  target_seconds: null,
  is_due: true,
  schedule: {
    decision: {
      state: "learning",
      attempts: 0,
      independent_successes: 0,
      next_due_at: "2026-01-01T00:00:00Z",
      reason: "new_item",
    },
  },
};

async function setup(page: Page) {
  await page.addInitScript(() =>
    sessionStorage.setItem("epoch:token", "test-token"),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const data = path.endsWith("/attempts")
      ? []
      : path.endsWith("/collections")
        ? [collection]
        : [item];
    await route.fulfill({ json: data });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Practice Two Sum" }),
  ).toBeVisible();
}

test("workspace and study dialog pass automated accessibility checks", async ({
  page,
}) => {
  await setup(page);
  const scan = () =>
    new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
  expect((await scan()).violations).toEqual([]);
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  await expect(
    page.getByRole("button", { name: "Start & open" }),
  ).toBeEnabled();
  expect((await scan()).violations).toEqual([]);
});

test("timer excludes pauses, detects clock changes, and retains evidence", () => {
  const d = { ...fresh(), elapsed: 1000, started: 2000, measured: true };
  const stopped = pause(d, 7000);
  expect(elapsed(stopped, 20000)).toBe(6000);
  expect(elapsed({ ...stopped, started: 20000 }, 24000)).toBe(10000);
  expect(clockChanged(d, 1000)).toBe(true);
  expect(clockChanged(d, 2000 + 13 * 3600000)).toBe(true);
});

test("adding a saved problem is not activity and duplicate links are rejected", async ({
  page,
}) => {
  await setup(page);
  await expect(page.locator(".activity-total")).toContainText("0 attempts");
  await page.getByRole("button", { name: "Add a problem" }).click();
  await page
    .getByLabel("Problem link")
    .fill("https://www.leetcode.com/problems/two-sum/description/?from=list");
  await expect(page.getByLabel("Problem title")).toHaveValue("Two Sum");
  await page.getByRole("button", { name: "Add problem", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "already in your library",
  );
});

test("keyboard navigation, filtering, mobile layout and dialog focus", async ({
  page,
}) => {
  await setup(page);
  await page.getByRole("textbox", { name: "Search problems" }).fill("not here");
  await expect(page.getByText("No matching problems.")).toBeVisible();
  await page.getByRole("textbox", { name: "Search problems" }).clear();
  const practice = page.getByRole("button", { name: "Practice Two Sum" });
  await practice.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(practice).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("start opens an isolated problem tab; pause, reset confirmation and manual time", async ({
  page,
  context,
}) => {
  await setup(page);
  await context.route("https://leetcode.com/**", (route) =>
    route.fulfill({ body: "<h1>Problem</h1>" }),
  );
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Start & open" }).click();
  const popup = await popupPromise;
  await popup.waitForURL("https://leetcode.com/problems/two-sum/");
  expect(await popup.evaluate(() => window.opener === null)).toBe(true);
  await popup.close();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start & open" }),
  ).toBeVisible();
  await page.getByLabel("Manual / corrected minutes").fill("0");
  let body: any;
  await page.route("**/api/items/*/attempts", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    body = route.request().postDataJSON();
    await route.fulfill({
      json: {
        attempt: body,
        decision: { next_due_at: "2026-12-01T00:00:00Z" },
      },
    });
  });
  await page.getByRole("button", { name: "Save attempt", exact: true }).click();
  await expect(page.getByText(/Attempt saved/)).toBeVisible();
  expect(body.timing).toEqual({ corrected_seconds: 0 });
});

test("blocked popup is reported; reload restores timer and stable retry payload", async ({
  page,
}) => {
  await setup(page);
  await page.evaluate(() => {
    window.open = () => null;
  });
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  await page.getByRole("button", { name: "Start & open" }).click();
  await expect(page.getByText(/problem tab was blocked/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  await expect(
    page.getByRole("button", { name: "Pause", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Manual / corrected minutes").fill("12");
  await page.getByLabel("Used a hint").check();
  const submissions: any[] = [];
  await page.route("**/api/items/*/attempts", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    submissions.push(route.request().postDataJSON());
    if (submissions.length === 1) await route.abort();
    else
      await route.fulfill({
        json: {
          attempt: submissions[0],
          decision: { next_due_at: "2026-12-01T00:00:00Z" },
        },
      });
  });
  await page.getByRole("button", { name: "Save attempt", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Retry saved attempt" }),
  ).toBeEnabled();
  await page.reload();
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  await page.getByRole("button", { name: "Retry saved attempt" }).click();
  await expect(page.getByText(/Attempt saved/)).toBeVisible();
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(submissions[0].outcome).toBe("with_hints");
  expect(submissions[0].timing.corrected_seconds).toBe(720);
  expect(submissions[0].timing.measured_seconds).toBeGreaterThanOrEqual(0);
  expect(
    await page.evaluate(
      (key) => localStorage.getItem(key),
      `epoch:draft:v1:${owner}:${itemId}`,
    ),
  ).toBeNull();
});

test("another tab cannot acquire the same active attempt", async ({
  page,
  context,
}) => {
  await setup(page);
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  await expect(
    page.getByRole("button", { name: "Start & open" }),
  ).toBeEnabled();
  const second = await context.newPage();
  await setup(second);
  await second.getByRole("button", { name: "Practice Two Sum" }).click();
  await expect(second.getByText(/open in another tab/)).toBeVisible();
  await expect(
    second.getByRole("button", { name: "Save attempt", exact: true }),
  ).toBeDisabled();
});

test("create collection and problem through the keyboard; server errors remain visible", async ({
  page,
}) => {
  await setup(page);
  await page.getByRole("button", { name: "New collection" }).click();
  await page.getByLabel("Collection name").fill("Graphs");
  let created: any;
  await page.route("**/api/collections", async (route) => {
    created = route.request().postDataJSON();
    await route.fulfill({ json: { ...collection, ...created } });
  });
  await page.getByLabel("Collection name").press("Enter");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(created.name).toBe("Graphs");
  await page.getByRole("button", { name: "Add a problem" }).click();
  await page.getByLabel("Problem title").fill("Valid Parentheses");
  await page
    .getByLabel("Problem link")
    .fill("https://leetcode.com/problems/valid-parentheses/");
  await page.route("**/api/items", (route) =>
    route.fulfill({ status: 503, json: { detail: "Database unavailable" } }),
  );
  await page.getByRole("button", { name: "Add problem", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Database unavailable");
  await expect(page.getByLabel("Problem title")).toHaveValue(
    "Valid Parentheses",
  );
});

test("untimed attempts keep duration absent and double-click submits once", async ({
  page,
}) => {
  await setup(page);
  await page.getByRole("button", { name: "Practice Two Sum" }).click();
  let count = 0;
  let attempt: any;
  await page.route("**/api/items/*/attempts", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    count++;
    attempt = route.request().postDataJSON();
    await route.fulfill({
      json: { attempt, decision: { next_due_at: "2026-12-01T00:00:00Z" } },
    });
  });
  await page
    .getByRole("button", { name: "Save attempt", exact: true })
    .dblclick();
  await expect(page.getByText(/Attempt saved/)).toBeVisible();
  expect(count).toBe(1);
  expect(attempt.timing).toEqual({});
});
