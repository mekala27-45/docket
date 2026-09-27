import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { Bundle, DocumentItem } from "../lib/types";
import type {
  Measurement,
  SweepRow,
  SweepFloor,
  RuleScore,
} from "../components/benchmark";

const recorded = JSON.parse(
  readFileSync("public/data/demo.json", "utf8"),
) as Bundle;
const measured = (value: number | null, n = 24): Measurement => ({
  value,
  ci:
    value == null
      ? [null, null]
      : [Math.max(0, value - 0.05), Math.min(1, value + 0.05)],
  n,
  reason: value == null ? "No eligible observations" : undefined,
});
async function serveFixture(page: Page, bundle: Bundle) {
  await page.route("**/data/demo.json", (route) =>
    route.fulfill({ json: bundle }),
  );
}

test("six small multiples preserve severity order, intervals, missingness and recorded floors", async ({
  page,
}) => {
  const bundle = structuredClone(recorded);
  const kinds = ["blur", "downscale", "jpeg", "noise", "photograph", "skew"];
  const rows: SweepRow[] = [],
    floors: SweepFloor[] = [];
  for (const kind of kinds) {
    const levels =
      kind === "jpeg"
        ? [95, 75, 50, 25, 10]
        : kind === "downscale"
          ? [1, 0.75, 0.5, 0.25, 0.1]
          : [0, 1, 2, 3, 4];
    for (const backend of ["rules", "tokens"]) {
      levels.forEach((level, index) =>
        rows.push({
          kind,
          level,
          level_index: index,
          backend,
          n: 24,
          field_f1: measured(
            index === 2 ? null : [0.98, 0.9, 0.8, 0.7, 0.5][index],
          ),
        }),
      );
      floors.push({ kind, backend, floor: 0.8, first_below: levels[3] });
    }
  }
  bundle.evaluation.degradation = rows;
  bundle.evaluation.degradation_floors = floors;
  bundle.evaluation.degradation_policy = { field_f1_floor: 0.8 };
  await serveFixture(page, bundle);
  await page.goto("lab/");
  await expect(page.locator(".small-multiples-grid .sweep-card")).toHaveCount(
    6,
  );
  await expect(page.locator(".sweep-card").first()).toContainText(
    "5 levels · n=24 documents per level",
  );
  const jpeg = page.getByRole("region", { name: "Jpeg degradation results" });
  await expect(jpeg).toContainText("Below floor at 25");
  await expect(jpeg.locator(".sweep-mark")).toHaveCount(8);
  const circles = await jpeg
    .locator(".series-0 circle")
    .evaluateAll((elements) =>
      elements.map((el) => ({
        x: Number(el.getAttribute("cx")),
        label: el.getAttribute("aria-label"),
      })),
    );
  expect(circles[0].label).toContain("level 95");
  expect(circles.at(-1)?.label).toContain("level 10");
  expect(circles[0].x).toBeLessThan(circles.at(-1)!.x);
  await jpeg.getByRole("button", { name: /Jpeg, tokens, level 25:/ }).click();
  await expect(page.getByLabel("Degradation", { exact: true })).toHaveValue(
    "jpeg",
  );
  await expect(page.getByLabel("Recorded level", { exact: true })).toHaveValue(
    "25",
  );
  await jpeg.getByRole("button", { name: "Jpeg: show table" }).click();
  await expect(jpeg.getByText("Not measured", { exact: true })).toHaveCount(2);
  await expect(
    jpeg.getByText("95% CI 85.0% to 95.0%", { exact: true }),
  ).toHaveCount(2);
  expect(
    await page
      .locator("body")
      .evaluate((el) => el.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("rule precision recall come from labeled outcomes and zero denominators stay unmeasured", async ({
  page,
}) => {
  const bundle = structuredClone(recorded);
  const rules: RuleScore[] = [
    {
      id: "arithmetic",
      name: "Amounts reconcile",
      source: "generated",
      split: "test",
      n: 24,
      precision: measured(0.5, 4),
      recall: measured(1, 2),
      fired: 4,
      expected: 2,
      tp: 2,
      fp: 2,
      fn: 0,
      tn: 20,
    },
    {
      id: "currency",
      name: "Currency is supported",
      source: "generated",
      split: "test",
      n: 24,
      precision: { ...measured(null, 0), reason: "Rule did not fire" },
      recall: {
        ...measured(null, 0),
        reason: "No planted defects for this rule",
      },
      fired: 0,
      expected: 0,
      tp: 0,
      fp: 0,
      fn: 0,
      tn: 24,
    },
  ];
  bundle.evaluation.rules = rules;
  await serveFixture(page, bundle);
  await page.goto("rules/");
  const scorecard = page.getByRole("region", {
    name: "Rule detection benchmark",
  });
  const arithmetic = scorecard
    .getByRole("row")
    .filter({ hasText: "Amounts reconcile" });
  await expect(arithmetic).toContainText("50.0%");
  await expect(arithmetic).toContainText("denominator n=4");
  await expect(arithmetic).toContainText("2 / 2 / 0 / 20");
  const currency = scorecard
    .getByRole("row")
    .filter({ hasText: "Currency is supported" });
  await expect(currency.getByText("Not measured", { exact: true })).toHaveCount(
    2,
  );
  await expect(currency).toContainText("No planted defects for this rule");
  await expect(
    page.getByRole("heading", { name: "Current queue outcomes" }),
  ).toBeVisible();
});

test("calibration identifies repeated variants and independently labeled populations", async ({
  page,
}) => {
  const bundle = structuredClone(recorded);
  bundle.evaluation.calibration = [
    {
      field: "total",
      backend: "rules",
      population: "generated",
      scope: "clean_and_degraded",
      n: 600,
      independent_documents: 24,
      ece_before: 0.2,
      ece_after: 0.04,
      bins: [
        { confidence: 0.2, accuracy: 0.3, count: 200 },
        { confidence: 0.6, accuracy: 0.65, count: 200 },
        { confidence: 0.9, accuracy: 0.91, count: 200 },
      ],
    },
    {
      field: "total",
      backend: "rules",
      population: "cord",
      scope: "original",
      n: 100,
      independent_documents: 100,
      ece_before: 0.2,
      ece_after: 0.05,
      bins: [
        { confidence: 0.4, accuracy: 0.5, count: 50 },
        { confidence: 0.8, accuracy: 0.75, count: 50 },
      ],
    },
  ];
  await serveFixture(page, bundle);
  await page.goto("evaluation/");
  await expect(page.locator("#calibration")).toContainText(
    "24 independent documents",
  );
  await expect(page.locator("#calibration")).toContainText(
    "600 field observations",
  );
  await page.getByLabel("Calibration field").selectOption("rules:cord:total");
  await expect(page.locator("#calibration")).toContainText(
    "100 independent documents",
  );
  await expect(page.locator("#calibration")).toContainText("Cord");
  await expect(page.locator("#calibration .curve-dot")).toHaveCount(2);
});

test("routing exposes populations with no automatic approvals", async ({
  page,
}) => {
  const bundle = structuredClone(recorded);
  const operating = bundle.evaluation.operating_point as Record<
    string,
    unknown
  >;
  operating.by_source = [
    {
      source: "generated",
      n: 24,
      auto_approved: 14,
      review_rate: measured(10 / 24, 24),
      auto_approval_error: measured(0, 14),
    },
    {
      source: "cord",
      n: 100,
      auto_approved: 0,
      review_rate: measured(1, 100),
      auto_approval_error: {
        value: null,
        ci: [null, null],
        n: 0,
        reason: "No documents auto-approved",
      },
    },
  ];
  await serveFixture(page, bundle);
  await page.goto("evaluation/");
  const row = page
    .locator(".routing-breakdown")
    .getByRole("row")
    .filter({ hasText: "Cord" });
  await expect(row).toContainText("100.0%");
  await expect(row).toContainText("Not measured");
  await expect(row).toContainText("denominator n=0");
  await expect(row).not.toContainText("0.0% to 0.0%");
});

test("missing priority is explicit and rule failures only break equal-score ties", async ({
  page,
}) => {
  const bundle = structuredClone(recorded);
  const original = bundle.documents.find(
    (d) => d.source === "generated" && d.type === "invoice",
  )!;
  const make = (
    id: string,
    risk: number | null,
    failures: number,
  ): DocumentItem => ({
    ...structuredClone(original),
    id,
    number: id,
    total: 100,
    currency: "USD",
    risk,
    status: "needs_review",
    minimum_confidence: 1,
    rules: Array.from({ length: failures }, (_, i) => ({
      id: String(i),
      name: "Test check",
      status: "fail",
      message: "Fixture expected failure",
    })),
  });
  const high = make("HIGH-SCORE", 50, 1),
    moreRules = make("RULE-TIE", 0, 3),
    fewerRules = make("FEWER-RULES", 0, 1),
    missing = make("MISSING-TOTAL", null, 1);
  missing.total = null;
  missing.extraction.fields.total.value = null;
  missing.extraction.fields.total.confidence = 0;
  bundle.documents = [fewerRules, moreRules, high, missing];
  await serveFixture(page, bundle);
  await page.goto("./");
  const rows = page.locator(".queue-table tbody tr");
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(0)).toContainText("MISSING-TOTAL");
  await expect(rows.nth(0)).toContainText("Unavailable");
  await expect(rows.nth(0)).toContainText("Unknown");
  await expect(rows.nth(1)).toContainText("HIGH-SCORE");
  await expect(rows.nth(2)).toContainText("RULE-TIE");
  await expect(rows.nth(3)).toContainText("FEWER-RULES");
});

test("expanded benchmark charts are reviewable on desktop and mobile", async ({
  page,
}, testInfo) => {
  await page.goto("lab/");
  await expect(page.locator(".small-multiples-grid .sweep-card")).toHaveCount(
    6,
  );
  for(const card of await page.locator('.small-multiples-grid .sweep-card').all()) {
    await expect(card).toContainText('5 levels · n=24 documents per level');
  }
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-lab-expanded.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.goto("rules/");
  await expect(
    page.getByRole("region", { name: "Rule detection benchmark" }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-rule-scorecard.png`,
    fullPage: true,
    animations: "disabled",
  });
});
