import { test, expect } from "@playwright/test";
import path from "node:path";
test("register, login, upload, verify, correct, cite, search, export", async ({
  page,
}) => {
  const email = `browser-${Date.now()}@example.test`;
  await page.goto("/register");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-test-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: /Your cases/ })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page
    .getByLabel("Case name", { exact: true })
    .fill("Browser procurement");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await page.getByRole("link", { name: /Browser procurement/ }).click();
  await page
    .getByLabel("Upload PDFs", { exact: true })
    .setInputFiles([
      path.resolve("../sample_data/both_po.pdf"),
      path.resolve("../sample_data/both_invoice.pdf"),
    ]);
  await expect(page.getByTestId("finding-quantity_difference")).toBeVisible();
  await expect(page.getByTestId("finding-unit_price_difference")).toBeVisible();
  await expect(page.getByTestId("finding-subtotal_difference")).toContainText(
    "2,200.00",
  );
  await page.getByRole("button", { name: /both_invoice.pdf invoice/ }).click();
  await expect(page.getByLabel("Quantity 1", { exact: true })).toHaveValue(
    "120",
  );
  await page.getByLabel("Quantity 1", { exact: true }).fill("100");
  await page.getByLabel("Unit price 1", { exact: true }).fill("80");
  await page.getByLabel("Amount 1", { exact: true }).fill("8000");
  await page.getByLabel("subtotal", { exact: true }).fill("8000");
  await page.getByLabel("total", { exact: true }).fill("8000");
  await page.getByRole("button", { name: "Save review & verify" }).click();
  await expect(page.getByTestId("review-save-status")).toContainText(
    "Verification and exports are up to date",
  );
  const source = page.getByRole("link", { name: "Open PDF", exact: true });
  await expect(source).toHaveAttribute(
    "href",
    /\/api\/documents\/.+\/file#page=1$/,
  );
  const sourceResponse = await page.request.get(
    (await source.getAttribute("href"))!,
  );
  expect(sourceResponse.status()).toBe(200);
  expect(sourceResponse.headers()["content-type"]).toContain("application/pdf");
  const popupPromise = page.waitForEvent("popup");
  await source.click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/file#page=1/);
  await popup.close();
  await page.getByRole("tab", { name: "Verification" }).click();
  await expect(
    page.getByRole("heading", { name: "No findings to show" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Evidence search" }).click();
  await page.getByLabel("Document question").fill("Copper cable");
  await page.getByRole("button", { name: "Search evidence" }).click();
  await expect(
    page.getByText("Evidence search — answer generation not configured.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Retrieved evidence/ }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("docverify-findings.csv");
  const jsonExport = await page.request.get(
    `${new URL(page.url()).pathname.replace("/cases/", "/api/cases/")}/export.json`,
  );
  expect(jsonExport.status()).toBe(200);
  expect((await jsonExport.json()).findings).toEqual([]);
  await page.screenshot({
    path: "test-results/case-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/case-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
