import { readFileSync } from "node:fs";

import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAuthenticatedAppAt as renderAppAt } from "./renderHelpers";
import * as etcApi from "../features/etc/api";

const INVOICE_DRAFT_STORAGE_KEY = "finops:pageSession:v1:101:imports.invoice:previewSession";
const ROUTE_RENDER_TIMEOUT = 5000;

function seedInvoicePreviewSession() {
  const now = Date.now();
  window.sessionStorage.setItem(
    INVOICE_DRAFT_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      updatedAt: now,
      expiresAt: now + 60_000,
      value: { sessionId: "import_session_0001" },
    }),
  );
}

function installMockApiFetchWithInvoicePreviewSession() {
  return installMockApiFetch({
    initialImportPreviewFileNames: ["一月发票.xlsx"],
    initialImportPreviewOverrides: [
      {
        template_code: "invoice_export",
        batch_type: "output_invoice",
      },
    ],
  });
}

afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

function getUploadInput(...labels: string[]) {
  for (const label of labels) {
    const input = screen.queryByLabelText(label);
    if (input) {
      return input as HTMLInputElement;
    }
  }
  throw new Error(`Missing upload input for labels: ${labels.join(", ")}`);
}

function getPreviewFormData(fetchMock: ReturnType<typeof installMockApiFetch>) {
  const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
  expect(previewCall).toBeTruthy();
  return (previewCall?.[1] as RequestInit).body as FormData;
}

function getEtcPreviewFormData(fetchMock: ReturnType<typeof installMockApiFetch>) {
  const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/preview");
  expect(previewCall).toBeTruthy();
  return (previewCall?.[1] as RequestInit).body as FormData;
}

function getFileOverrides(formData: FormData) {
  return JSON.parse(String(formData.get("file_overrides")));
}

function expectProjectImportShell() {
  const page = screen.getByTestId("import-workflow-page");
  expect(page).toHaveClass("import-workflow-page");
  expect(page).not.toHaveClass("MuiBox-root");

  const actions = screen.getByTestId("import-workflow-actions");
  expect(actions).toHaveClass("import-workflow-actions");
  expect(actions).not.toHaveClass("MuiStack-root");
}

function expectProjectUploadZone(label: string) {
  const input = getUploadInput(label, "上传文件");
  const zone = input.closest("label");
  expect(zone).not.toBeNull();
  const uploadZone = zone as HTMLElement;
  expect(uploadZone).toHaveClass("import-workflow-upload-zone");
  expect(uploadZone).not.toHaveClass("MuiBox-root");
  return input;
}

function expectProjectNotice(message: HTMLElement) {
  const notice = message.closest('[role="alert"], [role="status"]');
  expect(notice).not.toBeNull();
  const noticeRoot = notice as HTMLElement;
  expect(noticeRoot).toHaveClass("import-workflow-notice");
  expect(noticeRoot).not.toHaveClass("MuiAlert-root");
}

function expectProjectSummaryMetric(label: string) {
  const metric = screen.getByLabelText(label);
  expect(metric).toHaveClass("import-workflow-summary__metric");
  expect(metric).not.toHaveClass("MuiPaper-root");
}

function expectProjectPreviewTable(name: string) {
  const table = screen.getByRole("grid", { name });
  const tableRoot = table.closest(".finance-table");
  expect(tableRoot).not.toBeNull();
  expect(table).not.toHaveClass("MuiDataGrid-root");
}

function expectProjectDetailTabs() {
  const tabs = screen.getByRole("tablist", { name: "导入预览明细" });
  expect(tabs).toHaveClass("import-workflow-detail-tabs");
  expect(tabs).not.toHaveClass("MuiTabs-root");
}

async function selectReadyEtcTask(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText("ETC对账任务");
  await user.selectOptions(screen.getByLabelText("ETC对账任务"), "etc_task_ready_001");
}

describe("Import pages", () => {
  test("keeps import workflow premium visual treatment compact and motion-token based", () => {
    const css = readFileSync("src/app/styles.css", "utf8");

    expect(css).toContain(".import-workflow-content {\n  display: flex;\n  flex-direction: column;\n  gap: var(--fp-space-3);");
    expect(css).toContain(".import-workflow-panel {\n  min-width: 0;\n  border: 1px solid var(--fp-border);\n  border-radius: var(--fp-radius-sm);\n  background: var(--fp-surface);\n  box-shadow: none;");
    expect(css).toContain(".import-workflow-upload-zone {\n  display: grid;\n  place-items: center;\n  gap: var(--fp-space-1);\n  min-height: 112px;");
    expect(css).toContain("border-color var(--motion-base) var(--ease-standard)");
    expect(css).toContain(".import-workflow-select-field__control:focus-visible");
    expect(css).toContain(".import-workflow-summary__value {\n  margin-top: var(--fp-space-1);\n  color: var(--fp-ink);\n  font-family: var(--fp-font-data);\n  font-size: 22px;");
    expect(css).toContain(".import-workflow-grid-shell--review {\n  min-height: 320px;");
    expect(css).toContain(".import-workflow-review-drawer .finance-drawer__body");
    expect(css).toContain(".import-workflow-detail-tabs .tabs__tab:hover");
  });

  test("bank transaction import uses the standalone route and sends bank mapping overrides", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ sessionAccessTier: "admin" });

    renderAppAt("/imports/bank-transactions", {
      session: {
        accessTier: "admin",
        canAdminAccess: true,
      },
    });

    expect(await screen.findByRole("heading", { name: "银行流水导入" }, { timeout: ROUTE_RENDER_TIMEOUT })).toBeInTheDocument();
    expectProjectImportShell();
    const bankUploadInput = expectProjectUploadZone("上传银行流水文件");
    expect(screen.queryByRole("dialog", { name: "银行流水导入" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "流水录入" })).toBeInTheDocument();

    await user.upload(bankUploadInput, [
      new File(["bank-demo"], "historydetail14080.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["bank-demo-2"], "2026-01-01至2026-01-31交易明细.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(screen.getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    expect(previewButton).toBeEnabled();
    await user.click(previewButton);

    expect(await screen.findByLabelText("新增 14")).toBeInTheDocument();
    const formData = getPreviewFormData(fetchMock);
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "historydetail14080.xlsx",
      "2026-01-01至2026-01-31交易明细.xlsx",
    ]);
    expect(getFileOverrides(formData)).toEqual([
      {
        file_name: "historydetail14080.xlsx",
        batch_type: "bank_transaction",
        bank_mapping_id: "bank_mapping_8826",
        bank_name: "建设银行",
        bank_short_name: "建行",
        last4: "8826",
      },
      {
        file_name: "2026-01-01至2026-01-31交易明细.xlsx",
        batch_type: "bank_transaction",
        bank_mapping_id: "bank_mapping_8826",
        bank_name: "建设银行",
        bank_short_name: "建行",
        last4: "8826",
      },
    ]);

    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
    expect(screen.getByText(/已阻止确认导入/)).toHaveTextContent("识别账户与所选账户不一致");
    expect(screen.queryByRole("dialog", { name: "银行账户冲突确认" })).not.toBeInTheDocument();
  });

  test("bank transaction import displays preview audit counts and confirm copy", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传银行流水文件", "上传文件"), [
      new File(["bank-demo"], "historydetail14080.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["bank-demo-2"], "2026-01-01至2026-01-31交易明细.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(screen.getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 14")).toBeInTheDocument();
    expectProjectSummaryMetric("新增 14");
    expect(screen.getByLabelText("APP 已存在 2")).toBeInTheDocument();
    expect(screen.getByLabelText("本批重复 3")).toBeInTheDocument();
    expect(screen.queryByRole("grid", { name: "导入预览结果" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/review-rows"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "查看未处理明细" }));
    expect(await screen.findByRole("heading", { name: "未处理明细" })).toBeInTheDocument();
    expectProjectDetailTabs();
    expectProjectPreviewTable("重复项明细");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/review-rows"))).toBe(true);
    });
  });

  test("bank transaction import treats an all-existing preview as a completed no-op", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ bankImportAllExisting: true });

    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传银行流水文件", "上传文件"), [
      new File(["pingan-bank-demo"], "平安银行2026-08-01至2026-08-20交易明细.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(
      screen.getByLabelText("对应账户 平安银行2026-08-01至2026-08-20交易明细.xlsx"),
      "bank_mapping_0093",
    );
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 0")).toBeInTheDocument();
    expect(screen.getByLabelText("APP 已存在 48")).toBeInTheDocument();
    expect(screen.queryByText("已检查 48 笔流水，全部已存在于 APP，无需重复导入。")).not.toBeInTheDocument();
    expect(screen.getByLabelText("文件处理结果")).toHaveTextContent("无需导入");
    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/imports/files/confirm")).toHaveLength(0);
  });

  test("bank transaction import maps an unknown amount header and retries the same file", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传银行流水文件", "上传文件"), [
      new File(["bank-demo"], "建行需映射.xls", {
        type: "application/vnd.ms-excel",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("对应账户 建行需映射.xls"), "bank_mapping_8826");
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    const mappingPanel = await screen.findByRole("region", { name: "建行需映射.xls 字段映射" });
    await user.click(screen.getByRole("button", { name: /收入金额源列/ }));
    await user.click(await screen.findByRole("option", { name: "第3列 · 收到数额" }));
    await user.click(screen.getByRole("button", { name: "保存并重新解析" }));

    expect(await screen.findByText("字段映射已保存并重新完成预览。")).toBeInTheDocument();
    expect(mappingPanel).not.toBeInTheDocument();
    const retryCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/retry");
    expect(JSON.parse(String((retryCall?.[1] as RequestInit).body))).toEqual(expect.objectContaining({
      selected_file_ids: ["import_file_0001"],
      overrides: {
        import_file_0001: expect.objectContaining({
          batch_type: "bank_transaction",
          field_mapping: {
            txn_date: "0",
            debit_amount: "1",
            credit_amount: "2",
            counterparty_name: "3",
          },
        }),
      },
    }));
  });

  test("invoice import uses the standalone route and sends per-file directions", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expectProjectImportShell();
    const invoiceUploadInput = expectProjectUploadZone("上传发票文件");
    const manualEntryButton = screen.getByRole("button", { name: "发票录入" });
    const supportingDocumentButton = screen.getByRole("button", { name: "补充凭证" });
    await user.click(supportingDocumentButton);
    expect(await screen.findByRole("dialog", { name: "补充凭证" })).toBeInTheDocument();
    expect(await screen.findByText("暂无补充凭证")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭补充凭证" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "补充凭证" })).not.toBeInTheDocument());
    await user.click(manualEntryButton);
    expect(await screen.findByRole("dialog", { name: "发票录入" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭发票录入" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "发票录入" })).not.toBeInTheDocument());
    expect(screen.queryByRole("dialog", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();

    await user.upload(invoiceUploadInput, [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["invoice-input"], "二月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(previewButton);

    expect(await screen.findByLabelText("新增 22")).toBeInTheDocument();
    expect(getFileOverrides(getPreviewFormData(fetchMock))).toEqual([
      {
        file_name: "一月发票.xlsx",
        template_code: "invoice_export",
        batch_type: "output_invoice",
      },
      {
        file_name: "二月发票.xlsx",
        template_code: "invoice_export",
        batch_type: "input_invoice",
      },
    ]);
  });

  test("invoice import hides manual entry from read-only users", async () => {
    installMockApiFetch({ sessionAccessTier: "read_only" });

    renderAppAt("/imports/invoices", {
      session: {
        accessTier: "read_only",
        canMutateData: false,
      },
    });

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发票录入" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "补充凭证" })).toBeInTheDocument();
  });

  test("invoice import with no declared targets completes without probing Workbench", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText("新增 11")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));
    expect(await screen.findByText("已确认导入")).toBeInTheDocument();

    const requestedPaths = fetchMock.mock.calls.map(([input]) => String(input).split("?")[0]);
    expect(requestedPaths).not.toContain("/api/operation-barrier/status");
    expect(requestedPaths).not.toContain("/api/workbench");
  });

  test("invoice import does not expose a page Audit control", async () => {
    installMockApiFetch({ sessionAccessTier: "admin" });

    const { unmount } = renderAppAt("/imports/invoices", {
      session: {
        accessTier: "admin",
        canAdminAccess: true,
      },
    });

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Audit 发票导入" })).not.toBeInTheDocument();
    unmount();

    installMockApiFetch({ sessionAccessTier: "full_access" });
    renderAppAt("/imports/invoices");
    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Audit 发票导入" })).not.toBeInTheDocument();
  });

  test("invoice import displays preview audit counts and review copy", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["invoice-input"], "二月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 22")).toBeInTheDocument();
    expectProjectSummaryMetric("新增 22");
    expect(screen.getByLabelText("APP 已存在 2")).toBeInTheDocument();
    expect(screen.getByLabelText("本批重复 3")).toBeInTheDocument();
    expect(screen.getByLabelText("需检查 2")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/review-rows"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "查看未处理明细" }));
    expect(await screen.findByRole("heading", { name: "未处理明细" })).toBeInTheDocument();
    expectProjectDetailTabs();
    expectProjectPreviewTable("重复项明细");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/review-rows"))).toBe(true);
    });
  });

  test("file import confirm maps preview_stale to the refresh preview message", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ importConfirmPreviewStale: true });

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText("新增 11")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));

    expect(await screen.findByText("预览后数据已变化，请重新预览后再确认。")).toBeInTheDocument();
  });

  test("invoice import opens fresh after navigating away and back", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 11")).toBeInTheDocument();
    expect(screen.getAllByText("一月发票.xlsx").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "发票导入" }));
    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByLabelText("新增 11")).not.toBeInTheDocument();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();
    expect(screen.getByText("当前还没有选择文件。")).toBeInTheDocument();
  });

  test("invoice import ignores legacy browser and server preview sessions", async () => {
    const fetchMock = installMockApiFetchWithInvoicePreviewSession();
    seedInvoicePreviewSession();
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/imports/files/sessions"))).toBe(false);
  });

  test("invoice import refreshes only the preview created on the current page visit", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", { lastModified: 1 }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText("新增 11")).toBeInTheDocument();
    const sessionPath = "/imports/files/sessions/import_session_0001";
    const initialSessionReads = fetchMock.mock.calls.filter(([url]) => String(url) === sessionPath).length;

    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([url]) => String(url) === sessionPath).length).toBeGreaterThan(initialSessionReads);
    });
    expect(await screen.findByText("导入预览已刷新。")).toBeInTheDocument();
    expect(screen.getAllByText("一月发票.xlsx").length).toBeGreaterThan(0);
  });

  test("invoice import clear discards the current preview and returns to a fresh page", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", { lastModified: 1 }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText("新增 11")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空" }));
    await waitFor(() => expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument());
    expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    expect(screen.getByText("当前还没有选择文件。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/discard")).toBe(true);
    expect(screen.getByRole("button", { name: "清空" })).toBeDisabled();
  });

  test("invoice import ignores a preview response that finishes after navigation", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ importPreviewDelayMs: 80 });

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
    ]);
    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    await user.click(screen.getByRole("link", { name: "设置" }));

    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
    await new Promise((resolve) => window.setTimeout(resolve, 100));

    await user.click(screen.getByRole("link", { name: "发票导入" }));
    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();
    expect(screen.getByText("当前还没有选择文件。")).toBeInTheDocument();
  });

  test("ETC invoice import rejects non-zip files on the standalone route", async () => {
    const user = userEvent.setup({ applyAccept: false });
    installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["not zip"], "README.md", { type: "text/markdown" }),
      new File(["xlsx"], "etc.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(screen.getAllByText("ETC发票导入仅支持 zip 文件，已拒绝 2 个非 zip 文件。").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
  });

  test("ETC invoice import does not expose a page Audit control", async () => {
    installMockApiFetch({ sessionAccessTier: "admin" });
    const { unmount } = renderAppAt("/imports/etc-invoices", {
      session: { accessTier: "admin", canAdminAccess: true },
    });

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Audit ETC发票导入" })).not.toBeInTheDocument();
    unmount();

    installMockApiFetch({ sessionAccessTier: "full_access" });
    renderAppAt("/imports/etc-invoices");
    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Audit ETC发票导入" })).not.toBeInTheDocument();
  });

  test("ETC invoice import requires a ready reconciliation task before preview", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(await screen.findByText("请选择已确认的 ETC 对账任务后再预览 ETC zip。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建对账任务" })).not.toBeInTheDocument();

    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);

    expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/etc/reconciliation-tasks/ready-for-import")).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/etc/import/preview")).toBe(false);
  });

  test("ETC invoice import shows one compact recovery path when no task is ready", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchReadyEtcReconciliationTasks").mockResolvedValue({
      items: [],
      unavailableItems: [
        {
          taskId: "etc_task_reviewing_001",
          status: "reviewing",
          version: 9,
          title: "新建ETC对账批次",
          periodStart: "2026-03-28",
          periodEnd: "2026-04-27",
          oaTotalAmount: "",
          etcInvoiceCount: 0,
          supplementCount: 0,
          vehiclePlates: ["云ADA0381"],
          importBlockers: [{ code: "not_confirmed", message: "请先在 ETC 对账页确认对账。" }],
        },
      ],
    });

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(await screen.findByText("当前没有可导入的 ETC 对账任务。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往 ETC 对账" })).toHaveAttribute("href", "/etc-tickets");
    expect(screen.queryByText("新建ETC对账批次 / reviewing")).not.toBeInTheDocument();
    expect(screen.queryByText("请先在 ETC 对账页确认对账。")).not.toBeInTheDocument();
    expect(screen.getByLabelText("ETC对账任务")).toBeDisabled();
  });

  test("ETC invoice import previews zip files with the ETC API and skips generic preview", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expectProjectImportShell();
    const etcUploadInput = expectProjectUploadZone("上传ETC zip");
    await selectReadyEtcTask(user);
    await user.upload(etcUploadInput, [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
      new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 1")).toBeInTheDocument();
    expect(screen.queryByRole("grid", { name: "ETC导入预览结果" })).not.toBeInTheDocument();
    expect(screen.queryByText("etc_import_session_0001")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "查看未处理明细" }));
    expect(await screen.findByRole("heading", { name: "未处理明细" })).toBeInTheDocument();
    expectProjectPreviewTable("ETC导入预览结果");
    expect(screen.getByText("ETC-2026-005")).toBeInTheDocument();
    expect(screen.getAllByText("etc-2026-03.zip").length).toBeGreaterThan(0);
    expect(screen.getByText("新发票待导入")).toBeInTheDocument();
    expect(screen.getAllByText("附件补齐").length).toBeGreaterThan(0);

    const formData = getEtcPreviewFormData(fetchMock);
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "etc-2026-03.zip",
      "etc-2026-04.zip",
    ]);
    expect(formData.get("task_id")).toBe("etc_task_ready_001");
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/etc/import/confirm")).toBe(false);
  });

  test("ETC invoice import displays preview audit counts and confirm copy", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
      new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText("新增 1")).toBeInTheDocument();
    expectProjectSummaryMetric("新增 1");
    expect(screen.getByLabelText("APP 已存在 1")).toBeInTheDocument();
    expect(screen.getByLabelText("补齐附件 1")).toBeInTheDocument();
    expect(screen.getByLabelText("本批重复 1")).toBeInTheDocument();
    expect(screen.getByLabelText("需检查 1")).toBeInTheDocument();
    expect(screen.queryByRole("grid", { name: "ETC导入预览结果" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看未处理明细" }));
    expectProjectPreviewTable("ETC导入预览结果");
  });

  test("ETC invoice import preview lists missing reconciliation task items", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      etcImportBlockingIssues: [
        {
          error: "missing_required_etc_invoice",
          requirementId: "REQ-0011",
          transactionAt: "2026-04-27 12:22:09",
          transactionDate: "2026-04-27",
          amount: "126.35",
          vehiclePlate: "云ADA0381",
          invoiceCount: 1,
          missingInvoiceCount: 1,
          resolutionHint: "请补齐该行程对应的 ETC 发票后重新预览。",
        },
      ],
    });

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByText("发现 1 项需要处理，请查看未处理明细。")).toBeInTheDocument();
    expect(screen.queryByText("ETC对账任务缺失项")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "查看未处理明细" }));
    expect(await screen.findByText("ETC对账任务缺失项")).toBeInTheDocument();
    expectProjectNotice(screen.getByText("ETC对账任务缺失项"));
    expect(screen.getByText("2026-04-27 12:22:09")).toBeInTheDocument();
    expect(screen.getByText("126.35")).toBeInTheDocument();
    expect(screen.getByText("云ADA0381")).toBeInTheDocument();
    expect(screen.getByText("缺失行程 1")).toBeInTheDocument();
    expect(screen.getByText("缺少发票 1")).toBeInTheDocument();
    expect(screen.getByText("缺失金额 126.35")).toBeInTheDocument();
    expect(screen.getByText("请补齐该行程对应的 ETC 发票后重新预览。")).toBeInTheDocument();
  });

  test("ETC import confirm maps preview_stale to the refresh preview message", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ etcImportConfirmPreviewStale: true });

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText(/^新增 /)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));

    expect(await screen.findByText("预览后数据已变化，请重新预览后再确认。")).toBeInTheDocument();
  });

  test("ETC import stale task preview error clears preview and requires re-preview", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ etcImportConfirmStaleReconciliationTask: true });

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByLabelText(/^新增 /)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));

    expect(await screen.findByText("对账任务已更新，请重新预览 ETC zip 后再确认导入。")).toBeInTheDocument();
    expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始预览" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
  });

  test("ETC invoice import confirms the preview session and shows background job feedback", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByLabelText(/^新增 /)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /确认导入/ }));

    await waitFor(() => {
      expect(screen.getAllByText("已开始后台导入").length).toBeGreaterThan(0);
    });
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/confirm");
    expect(confirmCall).toBeTruthy();
    expect(JSON.parse(String((confirmCall?.[1] as RequestInit).body))).toEqual({
      sessionId: "etc_import_session_0001",
      taskId: "etc_task_ready_001",
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
  });

  test("ETC invoice import clears in-flight preview state after route unmount", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ etcImportPreviewDelayMs: 80 });

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    await user.click(screen.getByRole("link", { name: "设置" }));

    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("link", { name: "ETC发票导入" }));
    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
    expect(screen.getByLabelText("ETC对账任务")).toHaveValue("");
    expect(screen.queryByLabelText(/^新增 /)).not.toBeInTheDocument();
    expect(screen.queryByText("etc_import_session_0001")).not.toBeInTheDocument();
    expect(screen.queryByText("ETC-2026-005")).not.toBeInTheDocument();
  });
});
