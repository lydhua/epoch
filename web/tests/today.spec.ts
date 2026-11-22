import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { canonical } from "../src/Forms";
import { localDay, timing } from "../src/practice";

test("link canonicalization detects LeetCode variants without guessing problem numbers", () => {
  expect(
    canonical("https://www.leetcode.com/problems/two-sum/description/?x=1"),
  ).toBe("https://leetcode.com/problems/two-sum/");
  expect(canonical("javascript:alert(1)")).toBe("");
});

test("recommendation, alternatives, timing, activity days and persisted dark mode", async ({
  page,
}) => {
  const today = new Date();
  const todayKey = localDay(today);
  const collection = {
    id: "collection",
    owner_id: "owner",
    name: "Interview prep",
  };
  const build = (
    id: string,
    title: string,
    difficulty: string,
    due: string,
  ) => ({
    id,
    title,
    collection_id: "collection",
    tags: ["Hidden hint"],
    target_seconds: 1200,
    content: {
      type: "coding_problem",
      url: `https://leetcode.com/problems/${id}/`,
      difficulty,
    },
    schedule: {
      decision: {
        state: "consolidating",
        attempts: 1,
        independent_successes: 1,
        reason: "consolidating",
        next_due_at: due,
      },
    },
  });
  const problems = [
    build(
      "easy",
      "1. Two Sum",
      "easy",
      new Date(today.getTime() - 86400000).toISOString(),
    ),
    build(
      "medium",
      "146. LRU Cache",
      "medium",
      new Date(today.getTime() - 2 * 86400000).toISOString(),
    ),
    build(
      "hard",
      "4. Median of Two Sorted Arrays",
      "hard",
      today.toISOString(),
    ),
  ];
  const attempt = {
    id: "attempt1",
    occurred_at: today.toISOString(),
    outcome: "independent",
    timing: { measured_seconds: 1680, corrected_seconds: 1500 },
    confidence: null,
  };
  const receipt = { attempt, decision: problems[0].schedule.decision };
  expect(timing(receipt)).toBe("25 min");
  await page.addInitScript(() =>
    sessionStorage.setItem("epoch:token", "synthetic"),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/collections")
      ? [collection]
      : path.endsWith("/attempts")
        ? path.includes("/medium/")
          ? [receipt]
          : []
        : problems;
    await route.fulfill({ json });
  });
  await page.goto("/");
  const recommendation = page.getByRole("region", { name: "Next review" });
  await expect(
    recommendation.getByRole("link", { name: "146. LRU Cache" }),
  ).toHaveAttribute("target", "_blank");
  await expect(recommendation.getByText("25 min · Independent")).toBeVisible();
  await expect(
    recommendation.getByText("20 min", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Hidden hint")).toHaveCount(0);
  await page.getByLabel("Difficulty filter").selectOption("easy");
  await expect(
    page.getByRole("button", { name: "Practice 1. Two Sum" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Practice 4. Median of Two Sorted Arrays",
    }),
  ).toHaveCount(0);
  await expect(
    recommendation.getByRole("link", { name: "146. LRU Cache" }),
  ).toBeVisible();
  const day = page.getByRole("button", {
    name: `${today.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}: 1 attempt`,
    exact: true,
  });
  await day.click();
  await expect(page.locator(".activity-day")).toContainText("146. LRU Cache");
  await expect(page.locator(".activity-day")).toContainText("25 min");
  await page.getByLabel("Appearance").selectOption("dark");
  expect(
    await page.evaluate(
      () => getComputedStyle(document.documentElement).backgroundColor,
    ),
  ).toBe("rgb(0, 0, 0)");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.reload();
  await expect(page.getByLabel("Appearance")).toHaveValue("dark");
  expect(await page.evaluate(() => localStorage.getItem("epoch:theme"))).toBe(
    "dark",
  );
  expect(todayKey).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});
