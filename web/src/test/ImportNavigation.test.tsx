import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { importEntryFor, importEntryPath } from "../features/imports/importRoutes";
import { installMockApiFetch } from "./apiMock";
import { renderAuthenticatedAppAt } from "./renderHelpers";

afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

const entries = [
  { path: "/bank-details", source: "bank-details", button: "导入流水", title: "银行流水导入", back: "返回银行明细", permission: "imports.bank-transactions" },
  { path: "/input-invoice-usage", source: "input-invoice-usage", button: "导入进项发票", title: "发票导入", back: "返回进项发票", permission: "imports.invoices" },
  { path: "/output-invoice-collections", source: "output-invoice-collections", button: "导入销项发票", title: "发票导入", back: "返回销项发票", permission: "imports.invoices" },
] as const;

describe("business import navigation", () => {
  test("accepts only matching registered entry contexts", () => {
    expect(importEntryPath("input-invoice-usage")).toBe("/imports/invoices?from=input-invoice-usage");
    expect(importEntryFor("invoice", "input-invoice-usage")?.invoiceBatchType).toBe("input_invoice");
    for (const source of [null, "", "https://example.com", "__proto__", "bank-details"]) {
      expect(importEntryFor("invoice", source)).toBeNull();
    }
  });

  test.each(entries)("opens and returns through $source without mutation", async (entry) => {
    const fetchMock = installMockApiFetch();
    const user = userEvent.setup();
    renderAuthenticatedAppAt(entry.path, { backgroundTasks: true });
    await user.click(await screen.findByRole("button", { name: entry.button, exact: true }));
    expect(await screen.findByRole("heading", { name: entry.title, exact: true })).toBeVisible();
    await user.click(screen.getByRole("button", { name: entry.back }));
    expect(await screen.findByRole("button", { name: entry.button, exact: true })).toBeVisible();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method && !["GET", "HEAD"].includes(init.method))).toEqual([]);
  });

  test.each(entries)("hides $button without target import permission", async (entry) => {
    installMockApiFetch();
    renderAuthenticatedAppAt(entry.path, { session: { allowedPageKeys: [entry.source] }, backgroundTasks: true });
    await screen.findByRole("heading", { name: entry.path === "/bank-details" ? "银行明细" : entry.path === "/input-invoice-usage" ? "进项发票使用情况" : "销项发票收款情况" });
    expect(screen.queryByRole("button", { name: entry.button, exact: true })).not.toBeInTheDocument();
  });

  test.each(["input", "output"] as const)("preselects %s only for new files and protects local choices", async (direction) => {
    installMockApiFetch();
    const user = userEvent.setup();
    renderAuthenticatedAppAt(`/imports/invoices?from=${direction}-invoice-${direction === "input" ? "usage" : "collections"}`, { backgroundTasks: true });
    await screen.findByLabelText("上传发票文件");
    const input = document.querySelector<HTMLInputElement>("input[type=file]")!;
    const file = new File(["data"], "票据.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", lastModified: 123 });
    await user.upload(input, file);
    const select = await screen.findByLabelText("票据方向 票据.xlsx");
    expect(select).toHaveValue(`${direction}_invoice`);
    await user.selectOptions(select, direction === "input" ? "output_invoice" : "input_invoice");
    await user.click(within(screen.getByRole("navigation", { name: "测试导航" })).getByRole("link", { name: "发票导入", exact: true }));
    expect(screen.getByLabelText("票据方向 票据.xlsx")).toHaveValue(direction === "input" ? "output_invoice" : "input_invoice");
    await user.click(screen.getByRole("button", { name: "返回关联台" }));
    const dialog = await screen.findByRole("dialog", { name: "放弃未上传的文件？" });
    await user.click(within(dialog).getByRole("button", { name: "继续导入" }));
    expect(screen.getByLabelText("票据方向 票据.xlsx")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "返回关联台" }));
    await user.click(screen.getByRole("button", { name: "放弃并返回" }));
    await waitFor(() => expect(screen.queryByTestId("import-workflow-page")).not.toBeInTheDocument());
  });

  test("does not offer a return to a revoked source page", async () => {
    installMockApiFetch();
    renderAuthenticatedAppAt("/imports/invoices?from=input-invoice-usage", {
      session: { allowedPageKeys: ["imports.invoices"] }, backgroundTasks: true,
    });
    expect(await screen.findByRole("button", { name: "返回进项发票" })).toBeDisabled();
  });
});
