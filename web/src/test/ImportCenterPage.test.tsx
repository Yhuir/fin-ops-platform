import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAuthenticatedAppAt as renderAppAt } from "./renderHelpers";
import * as etcApi from "../features/etc/api";

const INVOICE_DRAFT_STORAGE_KEY = "finops:pageSession:v1:101:imports.invoice:previewSession";

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

async function selectReadyEtcTask(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText("ETC对账任务");
  await user.selectOptions(screen.getByLabelText("ETC对账任务"), "etc_task_ready_001");
}

describe("Import pages", () => {
  test("bank transaction import uses the standalone route and sends bank mapping overrides", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "银行流水导入" })).not.toBeInTheDocument();

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
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(screen.getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    expect(previewButton).toBeEnabled();
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
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
  });

  test("bank transaction import displays preview audit counts and confirm copy", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

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

    expect(await screen.findByLabelText("审计汇总 原始 18")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 唯一 16")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 重复 2")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 已存在 2")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 可导入 14")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "文件内重复" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "跨文件重复" })).toBeInTheDocument();
    expect(screen.getByText("将导入 14 条唯一记录，跳过 4 条重复。")).toBeInTheDocument();
  });

  test("invoice import uses the standalone route and sends per-file directions", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();

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
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
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

  test("invoice import displays preview audit counts and review copy", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

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

    expect(await screen.findByLabelText("审计汇总 原始 28")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 唯一 24")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 可导入 22")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 异常 1")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "已存在" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "可导入" })).toBeInTheDocument();
    expect(screen.getByText("将导入 22 条唯一记录，跳过 4 条重复，2 条需复核。")).toBeInTheDocument();
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
    expect(await screen.findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));

    expect(await screen.findByText("预览后数据已变化，请重新预览后再确认。")).toBeInTheDocument();
  });

  test("invoice import keeps selected files and preview when navigating away and back", async () => {
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

    expect(await screen.findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();
    expect(screen.getAllByText("一月发票.xlsx").length).toBeGreaterThan(0);
    expect(screen.getAllByText("14").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "发票导入" }));
    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.getByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();
    expect(screen.getAllByText("一月发票.xlsx").length).toBeGreaterThan(0);
    expect(screen.getAllByText("14").length).toBeGreaterThan(0);
  });

  test("invoice import restores preview from sessionStorage after remount", async () => {
    const fetchMock = installMockApiFetchWithInvoicePreviewSession();
    seedInvoicePreviewSession();
    renderAppAt("/imports/invoices");

    expect((await screen.findAllByText("一月发票.xlsx")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("14").length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/sessions/import_session_0001")).toBe(true);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "清空" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "清空" }));
    expect(window.sessionStorage.getItem(INVOICE_DRAFT_STORAGE_KEY)).toBeNull();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();
  });

  test("invoice import clears persisted preview when files are cleared", async () => {
    installMockApiFetchWithInvoicePreviewSession();
    seedInvoicePreviewSession();
    const { unmount } = renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem(INVOICE_DRAFT_STORAGE_KEY)).toContain("import_session_0001");
    expect((await screen.findAllByText("一月发票.xlsx")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "清空" }));
    expect(window.sessionStorage.getItem(INVOICE_DRAFT_STORAGE_KEY)).toBeNull();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();

    unmount();
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByText("一月发票.xlsx")).not.toBeInTheDocument();
  });

  test("invoice import keeps preview result when navigating away before preview finishes", async () => {
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
    await waitFor(() => {
      expect(window.sessionStorage.getItem(INVOICE_DRAFT_STORAGE_KEY)).toContain("import_session_0001");
    });

    await user.click(screen.getByRole("link", { name: "发票导入" }));
    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(await screen.findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();
    expect(screen.getAllByText("一月发票.xlsx").length).toBeGreaterThan(0);
    expect(screen.getAllByText("14").length).toBeGreaterThan(0);
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

  test("ETC invoice import explains unavailable reconciliation tasks when no task is ready", async () => {
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
    expect(await screen.findByText("已找到 1 个 ETC 对账任务，但当前不可导入：")).toBeInTheDocument();
    expect(screen.getByText("新建ETC对账批次 / reviewing")).toBeInTheDocument();
    expect(screen.getByText("请先在 ETC 对账页确认对账。")).toBeInTheDocument();
    expect(screen.getByLabelText("ETC对账任务")).toBeDisabled();
  });

  test("ETC invoice import previews zip files with the ETC API and skips generic preview", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await selectReadyEtcTask(user);
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
      new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
    expect(screen.getByText("etc_import_session_0001")).toBeInTheDocument();
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

    expect(await screen.findByLabelText("审计汇总 原始 4")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 唯一 3")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 重复 1")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 已存在 1")).toBeInTheDocument();
    expect(screen.getByLabelText("审计汇总 可导入 1")).toBeInTheDocument();
    expect(screen.getByText("将导入 1 条唯一记录，跳过 2 条重复，1 条需复核。")).toBeInTheDocument();
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

    expect(await screen.findByText("ETC对账任务缺失项")).toBeInTheDocument();
    expect(screen.getByText("2026-04-27 12:22:09")).toBeInTheDocument();
    expect(screen.getByText("126.35")).toBeInTheDocument();
    expect(screen.getByText("云ADA0381")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认导入" })).toBeDisabled();
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
    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();

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
    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入" }));

    expect(await screen.findByText("对账任务已更新，请重新预览 ETC zip 后再确认导入。")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "ETC导入预览" })).not.toBeInTheDocument();
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

    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
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

  test("ETC invoice import keeps preview result when navigating away before preview finishes", async () => {
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
      expect(screen.queryByRole("heading", { name: "ETC导入预览" })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("link", { name: "ETC发票导入" }));
    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
    expect(screen.getByText("etc_import_session_0001")).toBeInTheDocument();
    expect(screen.getByText("ETC-2026-005")).toBeInTheDocument();
  });
});
