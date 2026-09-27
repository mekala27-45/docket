import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const bundle = JSON.parse(readFileSync("public/data/demo.json", "utf8"));
const generated =
  bundle.documents.find(
    (d: { id: string; source: string; status: string }) =>
      d.source !== "cord" && d.status === "needs_review",
  ) || bundle.documents.find((d: { source: string }) => d.source !== "cord");

test("inbox filters real documents and exposes empty state", async ({
  page,
}) => {
  await page.goto("./");
  await expect(
    page.getByRole("heading", { name: "Your document inbox." }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).not.toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Search documents" })
    .fill("no-document-matches-xyz");
  await expect(page.getByText("No documents match your search.")).toBeVisible();
  await page.getByRole("button", { name: "Show all documents" }).click();
  await expect(
    page.getByRole("tab", { name: /All documents/ }),
  ).toHaveAttribute("aria-selected", "true");
  await page
    .getByLabel("Document type", { exact: true })
    .selectOption("invoice");
  await expect(page.locator("tbody tr")).not.toHaveCount(0);
  expect(
    await page
      .locator("body")
      .evaluate((el) => el.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("review evidence, correction and line items persist only in browser", async ({
  page,
}) => {
  await page.goto(`review/?id=${generated.id}`);
  await expect(
    page.getByRole("heading", { name: "Check the details" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Show Vendor evidence" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Why this value?" }).first().click();
  await expect(page.getByLabel("Vendor extraction trace")).toBeVisible();
  await page
    .getByLabel("Vendor", { exact: true })
    .fill("Practice Vendor Updated");
  await page.getByRole("tab", { name: /Line items/ }).click();
  await page
    .getByLabel("Description", { exact: true })
    .first()
    .fill("Reviewed practice line");
  await page.getByRole("button", { name: /Accept document/ }).click();
  await expect(
    page.getByText("Review saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Vendor", { exact: true })).toHaveValue(
    "Practice Vendor Updated",
  );
  await expect(
    page.getByText(
      "Human-corrected value. Original model confidence does not measure this revision.",
    ),
  ).toBeVisible();
  await page.goto("./");
  await page.getByRole("tab", { name: /Approved/ }).click();
  await page
    .getByRole("textbox", { name: "Search documents" })
    .fill("Practice Vendor Updated");
  await expect(page.locator("tbody tr")).toHaveCount(1);
});

test("evaluation renders paired OCR evidence and chart table toggles", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("evaluation/");
  await expect(
    page.getByRole("heading", { name: "Know what you can trust." }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "GOLD OCR · FIELD F1" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "REAL OCR · FIELD F1" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Show table" }).first().click();
  await expect(
    page.getByRole("columnheader", { name: "THRESHOLD", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Show table" }).first().click();
  await expect(
    page.getByRole("columnheader", { name: "OBSERVED CORRECT" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("local SQL executes an actual aggregation and rejects mutations", async ({
  page,
}) => {
  await page.goto("explore/");
  await expect(page.getByRole("button", { name: "Run query" })).toBeEnabled({
    timeout: 20000,
  });
  await page
    .getByRole("textbox", { name: "SQL query" })
    .fill("SELECT COUNT(*) AS count FROM documents;");
  await page.getByRole("button", { name: "Run query" }).click();
  await expect(
    page.getByRole("cell", {
      name: String(bundle.documents.length),
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "SQL query" })
    .fill("DELETE FROM documents;");
  await page.getByRole("button", { name: "Run query" }).click();
  await expect(page.locator(".query-error")).toContainText("read-only SELECT");
});

test("all routes disclose recorded demo and render without client errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const route of ["rules/", "models/", "lab/", "report/"]) {
    await page.goto(route);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.locator("footer")).toContainText(
      "Practice reviews stay in this browser.",
    );
    expect(
      await page
        .locator("body")
        .evaluate((el) => el.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
  expect(errors).toEqual([]);
});

test("API upload is explicit and demo never silently sends files", async ({
  page,
}) => {
  await page.goto("./");
  await page
    .getByRole("button", { name: "Upload document", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Connect an API to process uploads" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Connection settings", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "The URL and token stay in memory for this session.",
  );
  await page.getByRole("button", { name: "Close dialog" }).click();
});

test("connected reviews retain session across navigation and use API response", async ({
  page,
}) => {
  let posted = false;
  await page.route("http://127.0.0.1:7777/v1/**", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        },
      });
      return;
    }
    if (route.request().url().includes("/review/")) {
      expect(route.request().headers().authorization).toBe(
        "Bearer test-session-token",
      );
      posted = true;
      await route.fulfill({
        json: {
          document: {
            ...generated,
            vendor: "API canonical vendor",
            status: "accepted",
            extraction: {
              ...generated.extraction,
              fields: {
                ...generated.extraction.fields,
                vendor: {
                  ...generated.extraction.fields.vendor,
                  value: "API canonical vendor",
                  confidence: null,
                  reviewed: true,
                },
              },
            },
          },
        },
        headers: { "Access-Control-Allow-Origin": "*" },
      });
    } else
      await route.fulfill({
        json: [generated],
        headers: { "Access-Control-Allow-Origin": "*" },
      });
  });
  await page.goto("./");
  await page
    .getByRole("button", { name: "Upload document", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Connection settings", exact: true })
    .click();
  await page
    .getByLabel("API URL", { exact: true })
    .fill("http://127.0.0.1:7777");
  await page
    .getByLabel("Write token", { exact: true })
    .fill("test-session-token");
  await page.getByRole("button", { name: "Connect API", exact: true }).click();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Review next", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Check the details" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Accept document/ }).click();
  await expect(
    page.getByText("Review saved by API", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Vendor", { exact: true })).toHaveValue(
    "API canonical vendor",
  );
  expect(posted).toBe(true);
});

test("clearing an extracted total retains missingness after a practice review", async ({
  page,
}) => {
  await page.goto(`review/?id=${generated.id}`);
  await page.getByLabel("Total", { exact: true }).fill("");
  await page.getByRole("button", { name: /Accept document/ }).click();
  await expect(
    page.getByText("Review saved in this browser", { exact: true }),
  ).toBeVisible();
  const saved = await page.evaluate(
    (id) => JSON.parse(localStorage.getItem("docket:practice:v1") || "{}")[id],
    generated.id,
  );
  expect(saved.total).toBeNull();
  expect(saved.extraction.fields.total.value).toBeNull();
  expect(saved.extraction.fields.total.confidence).toBeNull();
});

test("capture responsive inbox and reviewer", async ({ page }, testInfo) => {
  await page.goto("./");
  await expect(page.locator("tbody tr")).not.toHaveCount(0);
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-inbox.png`,
    fullPage: true,
  });
  await page.goto(`review/?id=${generated.id}`);
  await expect(
    page.getByRole("heading", { name: "Check the details" }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-reviewer.png`,
    fullPage: true,
  });
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click();
  }
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Close navigation" }).click({position:{x:350,y:100}});
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".document-paper")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await page.screenshot({path:`test-results/${testInfo.project.name}-reviewer-dark.png`,fullPage:true,animations:"disabled"});
  await page.goto("evaluation/");
  await expect(page.getByRole("heading", { name: "Know what you can trust." })).toBeVisible();
  await page.screenshot({path:`test-results/${testInfo.project.name}-evaluation-dark.png`,fullPage:true,animations:"disabled"});
});
