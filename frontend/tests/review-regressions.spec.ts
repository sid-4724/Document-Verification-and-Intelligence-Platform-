import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { DocumentDetail } from "../lib/types";

async function setup(page: Page) {
  const registration = await page.request.post("/api/auth/register", {
    data: {
      email: `review-${randomBytes(8).toString("hex")}@example.test`,
      password: randomBytes(24).toString("base64url"),
    },
  });
  expect(registration.status()).toBe(201);
  const headers = { "X-CSRF-Token": (await registration.json()).csrf };
  const created = await page.request.post("/api/cases", {
    headers,
    data: { name: "Browser regression case" },
  });
  expect(created.status()).toBe(201);
  const caseId = (await created.json()).id;
  const documents: string[] = [];
  for (const filename of ["both_po.pdf", "both_invoice.pdf"]) {
    const response = await page.request.post(`/api/cases/${caseId}/documents`, {
      headers,
      multipart: {
        files: {
          name: filename,
          mimeType: "application/pdf",
          buffer: readFileSync(path.resolve(`../sample_data/${filename}`)),
        },
      },
    });
    expect(response.status()).toBe(201);
    documents.push((await response.json())[0].id);
  }
  await expect
    .poll(async () => {
      const details = await Promise.all(
        documents.map(async (identifier) =>
          (await page.request.get(`/api/documents/${identifier}`)).json(),
        ),
      );
      return details.every((document) =>
        ["completed", "needs_review"].includes(document.status),
      );
    })
    .toBe(true);
  return { caseId, documents, headers };
}

test("a delayed A response cannot replace B or change B's save target", async ({
  page,
}) => {
  const { caseId, documents } = await setup(page);
  const [a, b] = documents;
  let releaseA!: () => void;
  let started!: () => void;
  let handled!: () => void;
  const gate = new Promise<void>((resolve) => {
    releaseA = resolve;
  });
  const aStarted = new Promise<void>((resolve) => {
    started = resolve;
  });
  const aHandled = new Promise<void>((resolve) => {
    handled = resolve;
  });
  await page.route(`**/api/documents/${a}`, async (route) => {
    const response = await route.fetch();
    started();
    await gate;
    try {
      await route.fulfill({ response });
    } catch {
      /* The guarded loader can cancel A after B is selected. */
    } finally {
      handled();
    }
  });
  await page.goto(`/cases/${caseId}`);
  await page
    .getByRole("button", { name: /both_po.pdf purchase order/ })
    .click();
  await aStarted;
  await page.getByRole("button", { name: /both_invoice.pdf invoice/ }).click();
  await expect(page.getByLabel("document number", { exact: true })).toHaveValue(
    "INV-2001",
  );
  releaseA();
  await aHandled;
  await expect(page.getByLabel("document number", { exact: true })).toHaveValue(
    "INV-2001",
  );
  await expect(page.getByLabel("Quantity 1", { exact: true })).toHaveValue(
    "120",
  );
  await page
    .getByLabel("supplier", { exact: true })
    .fill("Reviewed B only (fictional)");
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      request.url().endsWith(`/documents/${b}/correction`),
  );
  await page.getByRole("button", { name: "Save review & verify" }).click();
  const request = await requestPromise;
  expect(request.postDataJSON().document_number).toBe("INV-2001");
  await expect(page.getByTestId("review-save-status")).toBeVisible();
  const afterB = await (await page.request.get(`/api/documents/${b}`)).json();
  const afterA = await (await page.request.get(`/api/documents/${a}`)).json();
  expect(afterB.data.supplier).toBe("Reviewed B only (fictional)");
  expect(afterA.data.supplier).not.toBe("Reviewed B only (fictional)");
});

test("dirty drafts offer stay/discard and survive unrelated polling", async ({
  page,
}) => {
  const { caseId } = await setup(page);
  await page.goto(`/cases/${caseId}`);
  await page
    .getByRole("button", { name: /both_po.pdf purchase order/ })
    .click();
  await page
    .getByLabel("supplier", { exact: true })
    .fill("Unsaved supplier (fictional)");
  await page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().endsWith(`/api/cases/${caseId}`),
  );
  await expect(page.getByLabel("supplier", { exact: true })).toHaveValue(
    "Unsaved supplier (fictional)",
  );
  await page.getByRole("button", { name: /both_invoice.pdf invoice/ }).click();
  await expect(
    page.getByRole("alertdialog", { name: "Unsaved changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByLabel("supplier", { exact: true })).toHaveValue(
    "Unsaved supplier (fictional)",
  );
  await page.getByRole("button", { name: /both_invoice.pdf invoice/ }).click();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByLabel("document number", { exact: true })).toHaveValue(
    "INV-2001",
  );
  await expect(page.getByLabel("supplier", { exact: true })).not.toHaveValue(
    "Unsaved supplier (fictional)",
  );
  await page
    .getByLabel("supplier", { exact: true })
    .fill("Unsaved before sign-out");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("alertdialog", { name: "Unsaved changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByLabel("supplier", { exact: true })).toHaveValue(
    "Unsaved before sign-out",
  );
  expect((await page.request.get("/api/auth/me")).status()).toBe(200);
});

test("another tab's review conflicts without losing the local draft", async ({
  page,
}) => {
  const { caseId, documents, headers } = await setup(page);
  const docId = documents[0];
  await page.goto(`/cases/${caseId}`);
  await page
    .getByRole("button", { name: /both_po.pdf purchase order/ })
    .click();
  await page
    .getByLabel("supplier", { exact: true })
    .fill("Local unsaved review");
  const current: DocumentDetail = await (
    await page.request.get(`/api/documents/${docId}`)
  ).json();
  const otherSave = await page.request.put(
    `/api/documents/${docId}/correction`,
    { headers, data: { ...current.data, supplier: "Another browser review" } },
  );
  expect(otherSave.status()).toBe(200);
  await page.getByRole("button", { name: "Save review & verify" }).click();
  await expect(page.locator(".editor-panel").getByRole("alert")).toContainText(
    "This document changed",
  );
  await expect(page.getByLabel("supplier", { exact: true })).toHaveValue(
    "Local unsaved review",
  );
  await page.getByRole("button", { name: "Reload latest values" }).click();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByLabel("supplier", { exact: true })).toHaveValue(
    "Another browser review",
  );
});
