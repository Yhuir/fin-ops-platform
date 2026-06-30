import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";
import * as etcApi from "../features/etc/api";

const etcTicketSourceFiles = [
  "src/pages/EtcTicketManagementPage.tsx",
] as const;

function readWebSource(path: string) {
  return readFileSync(resolve(__dirname, "..", path.replace(/^src\//, "")), "utf8");
}

function cssRule(styles: string, selector: string, containing?: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = Array.from(styles.matchAll(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\n\\}`, "gm")));
  const match = containing ? matches.find((candidate) => candidate[1].includes(containing)) : matches.at(-1);
  if (!match) {
    throw new Error(`Missing CSS rule for ${selector}`);
  }
  return match[1];
}

async function openEtcDisclosure(
  container: HTMLElement,
  user: { click: (element: Element) => Promise<void> },
  name: RegExp | string,
) {
  const trigger = await within(container).findByRole("button", { name });
  if (trigger.getAttribute("aria-expanded") !== "true") {
    await user.click(trigger);
  }
  return trigger;
}

function businessBatchFixture(overrides: Record<string, unknown> = {}) {
  return {
    businessBatchId: "etc-business-oa-action-001",
    taskId: "etc-recon-oa-action-001",
    status: "oa_confirmation_pending",
    version: 8,
    ownerUserId: "web_finance_user",
    ownerOrgId: "finance",
    importBatchIds: ["etc-import-oa-action-001"],
    submissionBatchId: "etc-submission-oa-action-001",
    externalEtcBatchId: "ETC-2026-OA-ACTION",
    oaDraftId: "oa-draft-oa-action-001",
    oaDraftUrl: "https://oa.example.test/draft/oa-draft-oa-action-001",
    oaRowId: "",
    oaProcessStatus: "",
    invoiceSummary: { count: 2, amount: "32.26" },
    scopeMonth: "2026-05",
    amountBreakdown: { scope_month: "2026-05" },
    invoiceIds: ["etc-inv-oa-action-001", "etc-inv-oa-action-002"],
    importAttempts: [],
    auditEvents: [],
    createdAt: "2026-05-19T09:00:00+08:00",
    updatedAt: "2026-05-19T09:00:00+08:00",
    ...overrides,
  };
}

function mockFetchEtcInvoices(items: unknown[] = []) {
  return vi.spyOn(etcApi, "fetchEtcInvoices").mockResolvedValue({
    counts: { unsubmitted: items.length, submitted: 0 },
    items,
    pagination: { page: 1, pageSize: 500, total: items.length },
  } as never);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ETC ticket management page", () => {
  test("targets project primitives for page shell, lists, uploads, reconciliation tables, dialogs, and feedback", () => {
    const sourceByPath = Object.fromEntries(etcTicketSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = etcTicketSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = etcTicketSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = etcTicketSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|ReportProblemOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon|<(?:Alert|Box|Collapse|Divider|IconButton|List|ListItem|ListItemButton|ListItemText|Paper|Stack|TableBody|TableCell|TableContainer|TableHead|TableRow|TextField|Tooltip|Typography)\b/.test(source)
        ? [path]
        : [];
    });
    const pageSource = sourceByPath["src/pages/EtcTicketManagementPage.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("PageScaffold") ? null : "EtcTicketManagementPage.tsx should keep PageScaffold",
      pageSource.includes("StatePanel") ? null : "ETC loading/empty/error states should keep StatePanel",
      pageSource.includes("AppDialog") ? null : "ETC destructive/OA/upload flows should keep AppDialog",
      /etc.*list|etc.*batch/.test(pageSource) ? null : "ETC batch/task list structure should keep project classes",
      /etc.*upload/.test(pageSource) ? null : "ETC upload/drop controls should keep project classes",
      /etc.*table|finance-table/.test(pageSource) ? null : "ETC invoice and reconciliation data should stay table-based",
      /etc.*toast|etc.*feedback|etc.*notice|StatePanel/.test(pageSource) ? null : "ETC feedback/status surfaces should use project feedback classes",
      pageSource.includes("@heroui/react") ? null : "ETC page should use HeroUI primitives where appropriate",
      pageSource.includes("DisclosureGroup") && pageSource.includes("EtcDisclosureSection") ? null : "ETC workflow should use collapsible HeroUI sections",
      pageSource.includes("ToggleButtonGroup") ? null : "ETC status switcher should use HeroUI ToggleButtonGroup",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      forbiddenLegacySurfaces,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      forbiddenLegacySurfaces: [],
      missingPrimitiveTargets: [],
    });
  });

  test("keeps premium ETC list, upload, table, dialog, and motion CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const surfaceRule = cssRule(
      styles,
      ".etc-filter-bar,\n.etc-batch-list-panel,\n.etc-batch-detail-panel,\n.etc-reconciliation-workspace,\n.etc-manual-review-panel,\n.etc-oa-status-panel,\n.etc-import-attempts",
    );
    const controlMotionRule = cssRule(
      styles,
      ".etc-page-action-link,\n.etc-primary-action,\n.etc-secondary-action,\n.etc-danger-action,\n.etc-icon-action,\n.etc-status-segmented__button,\n.etc-list-row-button,\n.etc-file-picker,\n.etc-upload-drop-box,\n.etc-reconciliation-description-toggle,\n.etc-inline-icon-action",
      "--motion-fast",
    );
    const filterInputRule = cssRule(
      styles,
      ".etc-filter-field input,\n.etc-manual-review-field input,\n.etc-manual-review-field select,\n.etc-dialog-field textarea",
    );
    const rowSurfaceRule = cssRule(
      styles,
      ".etc-reconciliation-task-row,\n.etc-batch-row,\n.etc-source-file-row,\n.etc-detail-metrics > div,\n.etc-reconciliation-metrics > div,\n.etc-plate-summary-item,\n.etc-manual-review-card,\n.etc-supplement-upload-target,\n.etc-import-attempt-row",
    );
    const tagRule = cssRule(styles, ".etc-count-tag,\n.etc-status-tag");
    const uploadRule = cssRule(styles, ".etc-upload-drop-box", "min-height: 96px");
    const invoiceCellRule = cssRule(styles, ".etc-invoice-table th,\n.etc-invoice-table td,\n.etc-reconciliation-table th,\n.etc-reconciliation-table td");
    const invoiceMoneyRule = cssRule(styles, ".etc-invoice-money-column,\n.etc-invoice-tax-column,\n.etc-invoice-money-cell");
    const reconciliationBlockRule = cssRule(styles, ".etc-reconciliation-table-block");
    const reconciliationHighlightRule = cssRule(
      styles,
      ".etc-reconciliation-table-row[data-highlight=\"matched\"] > td,\n.etc-reconciliation-table-row[data-highlight=\"manual\"] > td,\n.etc-reconciliation-table-row[data-highlight=\"covered\"] > td",
    );
    const reconciliationMoneyRule = cssRule(styles, ".etc-reconciliation-money");
    const inlineActionRule = cssRule(styles, ".etc-inline-icon-action");

    expect(surfaceRule).toContain("var(--fp-border)");
    expect(surfaceRule).toContain("var(--fp-radius-sm)");
    expect(surfaceRule).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(controlMotionRule).toContain("--motion-fast");
    expect(controlMotionRule).toContain("--ease-out-quart");
    expect(filterInputRule).toContain("var(--fp-border)");
    expect(filterInputRule).toContain("--motion-fast");
    expect(rowSurfaceRule).toContain("var(--fp-surface)");
    expect(tagRule).toContain("min-height: var(--fp-tag-height-table)");
    expect(tagRule).toContain("border-radius: var(--fp-tag-radius-table)");
    expect(uploadRule).toContain("min-height: 96px");
    expect(invoiceCellRule).toContain("--motion-fast");
    expect(invoiceMoneyRule).toContain("text-align: right");
    expect(invoiceMoneyRule).toContain("font-variant-numeric: tabular-nums");
    expect(reconciliationBlockRule).toContain("--etc-reconciliation-row-height: 32px");
    expect(reconciliationHighlightRule).toContain("var(--fp-success-soft)");
    expect(reconciliationMoneyRule).toContain("font-variant-numeric: tabular-nums");
    expect(inlineActionRule).toContain("var(--fp-primary)");
    expect([
      surfaceRule,
      controlMotionRule,
      filterInputRule,
      rowSurfaceRule,
      tagRule,
      uploadRule,
      invoiceCellRule,
      invoiceMoneyRule,
      reconciliationHighlightRule,
      inlineActionRule,
    ].join("\n")).not.toMatch(/0\.16s ease|#2563eb|#dbe3ef|#f9fbfe|#eff6ff|#fef2f2|#fffbeb|#172033/i);
  });

  test("refreshes batch list when ETC import background job completes", async () => {
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          job_id: "job_etc_import_0001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "导入 ETC发票完成 4/4",
          status: "succeeded",
          phase: "complete",
          current: 4,
          total: 4,
          percent: 100,
          message: "ETC发票导入完成。",
          result_summary: {
            created: 1,
            imported: 1,
            updated: 1,
            attachments_completed: 1,
            duplicates: 1,
            failed: 1,
            total: 4,
            affected_months: ["2026-04"],
            operation_barrier_targets: [
              { read_model_key: "workbench_relation", scope_key: "2026-04" },
              { read_model_key: "cost_statistics", scope_key: "active:2026-04" },
            ],
          },
          error: null,
          created_at: "2026-05-03T10:00:00+00:00",
          updated_at: "2026-05-03T10:00:04+00:00",
          finished_at: "2026-05-03T10:00:04+00:00",
        },
      ],
    });
    renderAppAt("/etc-tickets");

    await screen.findByTestId("etc-ticket-management-page", {}, { timeout: 5000 });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/operation-barrier/status",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            targets: [
              { read_model_key: "workbench_relation", scope_key: "2026-04" },
              { read_model_key: "cost_statistics", scope_key: "active:2026-04" },
            ],
          }),
        }),
      );
    });
    await waitFor(() => {
      const batchListCalls = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/etc/business-batches?"));
      expect(batchListCalls.length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      const taskCalls = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/etc/reconciliation-tasks");
      expect(taskCalls.length).toBeGreaterThanOrEqual(2);
    });
    const taskCreateCalls = fetchMock.mock.calls.filter(([url, init]) =>
      String(url) === "/api/etc/reconciliation-tasks" && init?.method === "POST"
    );
    expect(taskCreateCalls).toHaveLength(0);
  });

  test("unsubmitted mode shows batch list and whole-batch OA submit action", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).getByRole("heading", { name: "ETC票据" })).toBeInTheDocument();
    expect(within(page).getByRole("radiogroup", { name: "ETC批次状态" })).toBeInTheDocument();
    expect(await within(page).findByRole("radio", { name: "未提交 2" })).toBeInTheDocument();
    expect(within(page).getByRole("radio", { name: "已提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("region", { name: "ETC批次列表区" })).toBeInTheDocument();
    expect(within(page).getByRole("list", { name: "ETC批次列表" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("3月批次");
    await waitFor(() => expect(within(page).getByRole("button", { name: "提交审批" })).toBeEnabled());
    expect(within(page).getAllByText("3月批次").length).toBeGreaterThanOrEqual(1);
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/business-batches?status=active&page=1&page_size=100",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/etc/invoices?"))).toBe(false);
  });

  test("recovers business batches after a transient list failure when refreshed", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    let businessBatchFailuresRemaining = 1;
    fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (
        url.pathname === "/api/etc/business-batches"
        && (init?.method ?? "GET").toUpperCase() === "GET"
        && businessBatchFailuresRemaining > 0
      ) {
        businessBatchFailuresRemaining -= 1;
        return new Response(JSON.stringify({
          error: "etc_business_batches_temporarily_unavailable",
          message: "ETC业务批次加载暂时失败，请刷新后重试。",
        }), { status: 503, headers: { "Content-Type": "application/json" } });
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(input)}`);
      }
      return baseFetch(input, init);
    });
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("ETC业务批次加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    expect(within(page).queryByText("无匹配批次。")).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /^刷新$/ }));

    await waitFor(() => {
      expect(within(page).queryByText("ETC业务批次加载暂时失败，请刷新后重试。")).not.toBeInTheDocument();
      expect(within(page).getByRole("radio", { name: "未提交 2" })).toHaveAttribute("aria-checked", "true");
      expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("3月批次");
    });
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();

    const businessBatchRequests = fetchMock.mock.calls.filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/etc/business-batches" && (init?.method ?? "GET").toUpperCase() === "GET";
    });
    expect(businessBatchRequests.length).toBeGreaterThanOrEqual(2);
  });

  test("filters business batches, switches submitted tab, and keeps task-only actions out of submitted mode", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("radio", { name: "未提交 2" })).toHaveAttribute("aria-checked", "true");
    expect(within(page).getByRole("heading", { name: "批次列表" })).toBeInTheDocument();
    expect(within(page).getAllByRole("heading", { name: "批次列表" })).toHaveLength(1);
    expect(within(page).getByRole("link", { name: "导入发票" })).toHaveAttribute("href", "/imports/etc-invoices");

    fireEvent.change(within(page).getByLabelText("月份"), { target: { value: "2026-03" } });
    await user.type(within(page).getByLabelText("车牌"), "云ADA0381");
    await user.type(within(page).getByLabelText("关键词"), "ETC-2026");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches?status=active&month=2026-03&plate=%E4%BA%91ADA0381&keyword=ETC-2026&page=1&page_size=100",
        expect.objectContaining({ method: "GET" }),
      );
    });

    await user.click(within(page).getByRole("radio", { name: /已提交/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches?status=submitted&month=2026-03&plate=%E4%BA%91ADA0381&keyword=ETC-2026&page=1&page_size=100",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(within(page).getByRole("radio", { name: /已提交/ })).toHaveAttribute("aria-checked", "true");
    expect(within(page).queryByRole("region", { name: "ETC对账任务列表" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "新建批次" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "提交审批" })).not.toBeInTheDocument();
  });

  test("business batch tab counts use the same month filter as the visible list", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("radio", { name: "已提交 1" })).toBeInTheDocument();

    fireEvent.change(within(page).getByLabelText("月份"), { target: { value: "2026-04" } });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches?status=active&month=2026-04&page=1&page_size=100",
        expect.objectContaining({ method: "GET" }),
      );
    });

    await waitFor(() => {
      expect(within(page).getByRole("radio", { name: "已提交 0" })).toBeInTheDocument();
    });
    expect(within(page).queryByRole("radio", { name: "已提交 1" })).not.toBeInTheDocument();

    await user.click(within(page).getByRole("radio", { name: "已提交 0" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches?status=submitted&month=2026-04&page=1&page_size=100",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(within(page).getByRole("radio", { name: "已提交 0" })).toHaveAttribute("aria-checked", "true");
    expect(within(page).getByText("无匹配批次。")).toBeInTheDocument();
  });

  test("keeps submitted business batches visible when their workflow task shares the ETC batch id", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const closedWorkflowTask = {
      taskId: "ETC-RECON-000026",
      status: "closed",
      version: 17,
      title: "新建ETC批次",
      periodStart: "2026-03-28",
      periodEnd: "2026-04-27",
      statementPeriodStart: "2026-03-28",
      statementPeriodEnd: "2026-04-27",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "0381",
      oaTotalAmount: "1673.30",
      etcInvoiceAmount: "1673.30",
      supplementAmount: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云A361HX", "云A516HJ", "云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "etc_20260520_001",
      etcBatchId: "etc_20260520_001",
      hasImportedInvoices: true,
      importedInvoiceCount: 37,
      importedInvoiceAmount: "1673.30",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "2026-06-09T01:21:07+08:00",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
      sourceFiles: [],
      parseIssues: [],
    };
    const submittedBusinessBatch = businessBatchFixture({
      businessBatchId: "etc_business_batch_0004",
      taskId: "ETC-RECON-000026",
      status: "manually_marked_submitted",
      version: 39,
      importBatchIds: ["etc_20260520_001"],
      submissionBatchId: "etc_batch_0032",
      externalEtcBatchId: "etc_20260520_001",
      oaProcessStatus: "manual_without_oa_row",
      invoiceSummary: { count: 37, amount: "1673.30" },
      invoiceIds: [],
    });
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [closedWorkflowTask] } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockImplementation((query = {}) => Promise.resolve({
      counts: { active: 0, submitted: 1 },
      items: query.status === "submitted" ? [submittedBusinessBatch] : [],
      pagination: { page: 1, pageSize: 100, total: query.status === "submitted" ? 1 : 0 },
    } as never));
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue({
      ...submittedBusinessBatch,
      invoiceItems: [],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("radio", { name: "已提交 1" })).toBeInTheDocument();
    await user.click(within(page).getByRole("radio", { name: "已提交 1" }));

    const submittedRow = await within(page).findByTestId("etc-batch-row-etc_business_batch_0004");
    expect(submittedRow).toHaveTextContent("人工确认已提交");
    expect(submittedRow).toHaveTextContent("1673.30");
    expect(within(page).queryByText("无匹配批次。")).not.toBeInTheDocument();
  });

  test("clears stale workflow detail when no workflow batch remains visible", async () => {
    installMockApiFetch();
    const hiddenClosedWorkflowTask = {
      taskId: "ETC-RECON-000026",
      status: "closed",
      version: 17,
      title: "新建ETC批次",
      periodStart: "2026-03-28",
      periodEnd: "2026-04-27",
      statementPeriodStart: "2026-03-28",
      statementPeriodEnd: "2026-04-27",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "0381",
      oaTotalAmount: "1673.30",
      etcInvoiceAmount: "1673.30",
      supplementAmount: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云A361HX", "云A516HJ", "云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "etc_20260520_001",
      etcBatchId: "etc_20260520_001",
      hasImportedInvoices: true,
      importedInvoiceCount: 37,
      importedInvoiceAmount: "1673.30",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "2026-06-09T01:21:07+08:00",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 0, submitted: 1 },
      items: [],
      pagination: { page: 1, pageSize: 100, total: 0 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [hiddenClosedWorkflowTask] } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("无匹配批次。")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(page).queryByText("新建ETC批次 / v17")).not.toBeInTheDocument();
    });
    expect(within(page).getByText("选择左侧批次，或新建批次。")).toBeInTheDocument();
  });

  test("does not render orphan reconciliation tasks as visible ETC batches", async () => {
    installMockApiFetch();
    const orphanWorkflowTask = {
      taskId: "ETC-RECON-000011",
      status: "draft",
      version: 7,
      title: "新建ETC对账批次",
      periodStart: null,
      periodEnd: null,
      statementPeriodStart: null,
      statementPeriodEnd: null,
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 0, submitted: 0 },
      items: [],
      pagination: { page: 1, pageSize: 100, total: 0 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [orphanWorkflowTask] } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("radio", { name: "未提交 0" })).toBeInTheDocument();
    expect(await within(page).findByText("无匹配批次。")).toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-ETC-RECON-000011")).not.toBeInTheDocument();
    expect(within(page).queryByText("新建ETC批次")).not.toBeInTheDocument();
  });

  test("renders a unified ETC batch workflow list without a separate reconciliation task list", async () => {
    installMockApiFetch();

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("list", { name: "ETC批次列表" })).toBeInTheDocument();
    expect(within(page).queryByRole("region", { name: "ETC对账任务列表" })).not.toBeInTheDocument();
    expect(within(page).queryByText("对账任务")).not.toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("3月批次");
  });

  test("shows business batch load errors without rendering a real empty batch state", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockRejectedValue(new Error("业务批次服务不可用，请稍后重试。"));

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("业务批次服务不可用，请稍后重试。")).toBeInTheDocument();
    expect(within(page).queryByText("无匹配批次。")).not.toBeInTheDocument();
  });

  test("shows reconciliation task load errors without rendering a real empty task state", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockRejectedValue(new Error("批次流程服务繁忙，请稍后重试。"));

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const workflowRegion = await within(page).findByRole("region", { name: "ETC批次流程" });
    expect(await within(workflowRegion).findByText("批次流程服务繁忙，请稍后重试。")).toBeInTheDocument();
    expect(within(workflowRegion).queryByText("暂无批次流程。")).not.toBeInTheDocument();
  });

  test("shows business batch detail load errors without rendering detail as truly empty", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockRejectedValue(new Error("批次明细读取失败，请刷新后重试。"));

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const detailRegion = await within(page).findByRole("region", { name: "ETC批次详情" });
    expect(await within(detailRegion).findByText("批次明细读取失败，请刷新后重试。")).toBeInTheDocument();
    expect(within(detailRegion).queryByText("暂无明细。")).not.toBeInTheDocument();
  });

  test("surfaces new business batch errors and keeps the current batch list", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const createBatch = vi.spyOn(etcApi, "createEtcBusinessBatch").mockRejectedValue(new Error("新建 ETC 批次失败，请稍后重试。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "新建批次" }));

    await waitFor(() => expect(createBatch).toHaveBeenCalledWith({}));
    expect(await within(page).findByText("新建 ETC 批次失败，请稍后重试。")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();
  });

  test("deletes an unsubmitted ETC batch through confirmation and refreshes the list", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-01");
    await user.click(within(row).getByRole("button", { name: "删除批次 3月批次" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("3月批次");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches/etc-batch-unsubmitted-01",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(await within(page).findByRole("radio", { name: "未提交 1" })).toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc-batch-unsubmitted-01")).not.toBeInTheDocument();
  });

  test("keeps the delete dialog and batch row when business batch deletion fails", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/business-batches/etc-batch-unsubmitted-01") && init?.method === "DELETE") {
        return new Response(
          JSON.stringify({ error: "version_conflict", message: "批次已被他人更新，请刷新后重试。" }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-01");
    await user.click(within(row).getByRole("button", { name: "删除批次 3月批次" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    expect(await within(page).findByText("批次已被他人更新，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "删除批次" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();
  });

  test("can retry business batch deletion after a transient failure", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    let deleteFailuresRemaining = 1;
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (
        String(url).endsWith("/api/etc/business-batches/etc-batch-unsubmitted-01")
        && init?.method === "DELETE"
        && deleteFailuresRemaining > 0
      ) {
        deleteFailuresRemaining -= 1;
        return new Response(
          JSON.stringify({
            error: "etc_business_batch_delete_temporarily_unavailable",
            message: "ETC业务批次删除暂时失败，请重试。",
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-01");
    await user.click(within(row).getByRole("button", { name: "删除批次 3月批次" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    expect(await within(page).findByText("ETC业务批次删除暂时失败，请重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "删除批次" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      const deleteCalls = fetchMock.mock.calls.filter(([url, init]) =>
        String(url).endsWith("/api/etc/business-batches/etc-batch-unsubmitted-01")
        && (init as RequestInit | undefined)?.method === "DELETE",
      );
      expect(deleteCalls).toHaveLength(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "删除批次" })).not.toBeInTheDocument();
    });
    expect(within(page).queryByText("ETC业务批次删除暂时失败，请重试。")).not.toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc-batch-unsubmitted-01")).not.toBeInTheDocument();
  });

  test("allows business batch deletion when the latest batch only has an unsubmitted OA draft link", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const listedBusinessBatch = {
      businessBatchId: "etc-business-batch-stale-delete-001",
      taskId: "etc-recon-task-001",
      status: "imported",
      version: 7,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-batch-stale-delete-001"],
      submissionBatchId: "",
      externalEtcBatchId: "ETC-2026-DRAFT-LINK",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "in_progress",
      invoiceSummary: { count: 2, amount: "32.26" },
      scopeMonth: "2026-05",
      amountBreakdown: { scope_month: "2026-05" },
      invoiceIds: ["etc-inv-001", "etc-inv-002"],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
    };
    const latestBusinessBatch = {
      ...listedBusinessBatch,
      version: 8,
      submissionBatchId: "etc-submission-batch-active-001",
      oaDraftId: "oa-draft-active-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-active-001",
      status: "oa_confirmation_pending",
      invoiceItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [listedBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(latestBusinessBatch as never);
    const deleteBusinessBatch = vi.spyOn(etcApi, "deleteEtcBusinessBatch").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-business-batch-stale-delete-001");
    await user.click(within(row).getByRole("button", { name: "删除批次 5月批次" }));
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteBusinessBatch).toHaveBeenCalledWith("etc-business-batch-stale-delete-001", {
        expectedVersion: 8,
        reason: "用户在 ETC 页面删除未提交业务批次。",
      });
    });
  });

  test("deletes a legacy submission batch row through the linked business batch", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      etcInvoiceStoreBatches: [{
        id: "etc-submission-legacy-001",
        business_batch_id: "etc-business-legacy-001",
        business_status: "imported",
        etc_batch_id: "ETC-2026-LEGACY",
        external_batch_id: "ETC-2026-LEGACY",
        external_etc_batch_id: "ETC-2026-LEGACY",
        status: "unsubmitted",
        source_type: "normal_oa_draft",
        invoice_ids: ["etc-inv-001", "etc-inv-002"],
        invoice_summary: { count: 37, amount: "1673.30" },
        import_batch_ids: ["etc-import-legacy-001"],
        submission_batch_id: "etc-submission-legacy-001",
        confirmed_at: "2026-06-09T01:21:07+08:00",
        linked_oa_row_id: null,
        linked_oa_case_id: null,
        linked_oa_applicant: null,
        linked_oa_apply_date: null,
        linked_oa_amount: null,
        amount_delta: null,
        note: "",
        version: 14,
      }],
    });
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-business-legacy-001");
    await user.click(within(row).getByRole("button", { name: "删除批次 2月批次" }));
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url, init]) =>
        url === "/api/etc/business-batches/etc-business-legacy-001"
        && (init as RequestInit | undefined)?.method === "DELETE",
      )).toBe(true);
    });
    expect(fetchMock.mock.calls.some(([url, init]) =>
      url === "/api/etc/batches/etc-submission-legacy-001"
      && (init as RequestInit | undefined)?.method === "DELETE",
    )).toBe(false);
  });

  test("treats an already-deleted business batch as a successful delete and refreshes stale rows", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const staleListedBusinessBatch = {
      businessBatchId: "etc_business_batch_0001",
      taskId: "etc-recon-deleted-link-001",
      status: "not_submitted",
      version: 12,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-deleted-link-001"],
      submissionBatchId: "",
      externalEtcBatchId: "",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 36, amount: "1673.30" },
      invoiceIds: ["etc-inv-001"],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:10:00+08:00",
    };
    const fetchBusinessBatches = vi.spyOn(etcApi, "fetchEtcBusinessBatches")
      .mockResolvedValueOnce({
        counts: { active: 1, submitted: 0 },
        items: [staleListedBusinessBatch],
        pagination: { page: 1, pageSize: 100, total: 1 },
      } as never)
      .mockResolvedValue({
        counts: { active: 0, submitted: 0 },
        items: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail")
      .mockResolvedValueOnce({
        ...staleListedBusinessBatch,
        invoiceItems: [],
      } as never)
      .mockRejectedValueOnce(new Error("ETC business batch not found: etc_business_batch_0001"));
    const deleteBusinessBatch = vi.spyOn(etcApi, "deleteEtcBusinessBatch").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc_business_batch_0001");
    await user.click(within(row).getByRole("button", { name: "删除批次 未记录月份批次" }));
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteBusinessBatch).toHaveBeenCalledWith("etc_business_batch_0001", {
        reason: "用户在 ETC 页面删除未提交业务批次。",
      });
    });
    await waitFor(() => {
      expect(fetchBusinessBatches).toHaveBeenCalledTimes(2);
    });
    expect(within(page).queryByText("ETC business batch not found: etc_business_batch_0001")).not.toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc_business_batch_0001")).not.toBeInTheDocument();
  });

  test("treats coded business-batch not-found responses as idempotent stale-row cleanup", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const staleListedBusinessBatch = {
      businessBatchId: "etc_business_batch_0002",
      taskId: "etc-recon-deleted-link-002",
      status: "not_submitted",
      version: 12,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-deleted-link-002"],
      submissionBatchId: "",
      externalEtcBatchId: "",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 36, amount: "1673.30" },
      invoiceIds: ["etc-inv-001"],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:10:00+08:00",
    };
    const notFound = Object.assign(new Error("ETC业务批次不存在。"), {
      status: 404,
      code: "business_batch_not_found",
    });
    vi.spyOn(etcApi, "fetchEtcBusinessBatches")
      .mockResolvedValueOnce({
        counts: { active: 1, submitted: 0 },
        items: [staleListedBusinessBatch],
        pagination: { page: 1, pageSize: 100, total: 1 },
      } as never)
      .mockResolvedValue({
        counts: { active: 0, submitted: 0 },
        items: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail")
      .mockResolvedValueOnce({
        ...staleListedBusinessBatch,
        invoiceItems: [],
      } as never)
      .mockRejectedValueOnce(notFound);
    const deleteBusinessBatch = vi.spyOn(etcApi, "deleteEtcBusinessBatch").mockRejectedValueOnce(notFound as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc_business_batch_0002");
    await user.click(within(row).getByRole("button", { name: "删除批次 未记录月份批次" }));
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteBusinessBatch).toHaveBeenCalledWith("etc_business_batch_0002", {
        reason: "用户在 ETC 页面删除未提交业务批次。",
      });
    });
    expect(within(page).queryByText("ETC业务批次不存在。")).not.toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc_business_batch_0002")).not.toBeInTheDocument();
  });

  test("removes a selected stale business-batch row when detail loading reports not found", async () => {
    installMockApiFetch();
    const staleListedBusinessBatch = {
      businessBatchId: "etc_business_batch_0003",
      taskId: "etc-recon-deleted-link-003",
      status: "not_submitted",
      version: 12,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-deleted-link-003"],
      submissionBatchId: "",
      externalEtcBatchId: "",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 36, amount: "1673.30" },
      invoiceIds: ["etc-inv-001"],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:10:00+08:00",
    };
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [staleListedBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockRejectedValue(Object.assign(new Error("ETC业务批次不存在。"), {
      status: 404,
      code: "business_batch_not_found",
    }) as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => {
      expect(within(page).queryByTestId("etc-batch-row-etc_business_batch_0003")).not.toBeInTheDocument();
    });
    expect(within(page).queryByText("ETC业务批次不存在。")).not.toBeInTheDocument();
  });

  test("deletes the selected mutable reconciliation task with expected version from the workflow", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const task = {
      taskId: "etc_task_ready_001",
      status: "ready_for_import",
      version: 7,
      title: "2026-03 ETC 对账",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      oaTotalAmount: "108.40",
      etcInvoiceAmount: "96.40",
      supplementAmount: "12.00",
      etcInvoiceCount: 8,
      supplementCount: 1,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:mock",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [task] } as never)
      .mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(task as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "删除批次 2026-03 ETC批次" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("2026-03 ETC批次");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc_task_ready_001",
        expect.objectContaining({
          method: "DELETE",
          body: JSON.stringify({ expectedVersion: 7 }),
        }),
      );
    });
    expect(within(page).queryByText("2026-03 ETC批次 / v7")).not.toBeInTheDocument();
  });

  test("keeps the task delete dialog and row when reconciliation task deletion fails", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const task = {
      taskId: "etc-recon-delete-fail-001",
      status: "reviewing",
      version: 4,
      title: "2026-04 ETC 删除失败",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [task] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(task as never);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockRejectedValue(new Error("删除批次失败，请刷新后重试。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "删除批次 2026-04 ETC 删除失败" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleteTask).toHaveBeenCalledWith("etc-recon-delete-fail-001", 4));
    expect(await within(page).findByText("删除批次失败，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "删除批次" })).toBeInTheDocument();
    expect(within(page).getByText("2026-04 ETC 删除失败 / v4")).toBeInTheDocument();
  });

  test("closes the task delete dialog after delete succeeds even when the follow-up task refresh hangs", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const task = {
      taskId: "etc-recon-delete-refresh-hangs-001",
      status: "reviewing",
      version: 3,
      title: "2026-02 ETC 对账",
      periodStart: "2026-02-27",
      periodEnd: "2026-02-28",
      statementPeriodStart: "2026-02-01",
      statementPeriodEnd: "2026-02-29",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "120.00",
      etcInvoiceAmount: "90.00",
      supplementAmount: "30.00",
      etcInvoiceCount: 2,
      supplementCount: 1,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    } as never;
    let taskLoadCount = 0;
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockImplementation(() => {
      taskLoadCount += 1;
      if (taskLoadCount === 1) {
        return Promise.resolve({ items: [task] });
      }
      return new Promise(() => undefined);
    });
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(task);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "删除批次 2026-02 ETC批次" }));
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-delete-refresh-hangs-001", 3);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "删除批次" })).not.toBeInTheDocument();
    });
    expect(within(page).queryByText("2026-02 ETC批次 / v3")).not.toBeInTheDocument();
    expect(screen.queryByText("正在删除...")).not.toBeInTheDocument();
  });

  test("deletes an imported reconciliation task with the latest task version and removes it from the list", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-delete-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-delete-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [importedTask] } as never)
      .mockResolvedValueOnce({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...importedTask,
      version: 9,
    } as never);
    mockFetchEtcInvoices([
      {
        id: "etc-inv-imported-delete-001",
        invoiceNumber: "ETC-IMPORTED-DELETE-001",
        issueDate: "2026-03-03",
        passageStartDate: "2026-03-03",
        passageEndDate: "2026-03-03",
        plateNumber: "云ADA0381",
        sellerName: "云南高速通行费",
        buyerName: "云南溯源科技",
        amountWithoutTax: "28.20",
        taxAmount: "1.80",
        totalAmount: "30.00",
        status: "unsubmitted",
        hasPdf: true,
        hasXml: true,
      },
    ]);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "删除批次 2026-03 ETC 已导入" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("将删除本地批次、上传文件、核对结果和已导入发票");
    expect(dialog).toHaveTextContent("审批系统中的草稿和已提交记录不会删除");
    expect(dialog.textContent).toContain("重新确认并导入 ZIP");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-imported-delete-001", 9);
    });
    await waitFor(() => {
      expect(within(page).queryByText("2026-03 ETC 已导入 / v8")).not.toBeInTheDocument();
    });
    expect(within(page).getByText("选择左侧批次，或新建批次。")).toBeInTheDocument();
    expect(within(page).queryByRole("region", { name: "已导入ETC发票" })).not.toBeInTheDocument();
  });

  test("allows physical task deletion after an unsubmitted OA draft link exists", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const taskWithDraft = {
      taskId: "etc-recon-imported-draft-linked-001",
      status: "imported",
      version: 12,
      title: "2026-03 ETC 已建草稿",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-draft-linked-001",
      etcBatchId: "ETC-2026-DRAFT-LINKED",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "etc_batch_submission_draft_linked_001",
      oaDraftStatus: "draft_created",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [taskWithDraft] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(taskWithDraft as never);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const deleteButton = await within(page).findByRole("button", { name: "删除批次 2026-03 ETC 已建草稿" });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-imported-draft-linked-001", 12);
    });
  });

  test("allows physical task deletion when only the external ETC OA batch link exists", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const taskWithExternalOaBatch = {
      taskId: "etc-recon-imported-external-link-001",
      status: "imported",
      version: 12,
      title: "2026-03 ETC 外部批次链路",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-external-link-001",
      etcBatchId: "ETC-2026-EXTERNAL-LINK",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [taskWithExternalOaBatch] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(taskWithExternalOaBatch as never);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const deleteButton = await within(page).findByRole("button", { name: "删除批次 2026-03 ETC 外部批次链路" });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-imported-external-link-001", 12);
    });
  });

  test("allows reconciliation task deletion when its linked business batch only has an unsubmitted OA draft", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-business-linked-001",
      status: "imported",
      version: 13,
      title: "新建ETC对账批次",
      periodStart: "2026-03-28",
      periodEnd: "2026-04-27",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-04-30",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "1673.30",
      etcInvoiceAmount: "1673.30",
      supplementAmount: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云A361HX", "云A516HJ", "云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "etc-import-business-linked-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 37,
      importedInvoiceAmount: "1673.30",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    const linkedBusinessBatch = {
      businessBatchId: "etc-business-linked-001",
      taskId: "etc-recon-imported-business-linked-001",
      status: "oa_confirmation_pending",
      version: 8,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-business-linked-001"],
      submissionBatchId: "etc-submission-linked-001",
      externalEtcBatchId: "ETC-2026-LINKED",
      oaDraftId: "oa-draft-linked-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-linked-001",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 37, amount: "1673.30" },
      scopeMonth: "2026-05",
      amountBreakdown: { scope_month: "2026-05" },
      invoiceIds: [],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
    };
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      items: [],
      counts: { unsubmitted: 0, submitted: 0 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [importedTask] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(importedTask as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [linkedBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue({
      ...linkedBusinessBatch,
      invoiceItems: [],
    } as never);
    const deleteBusinessBatch = vi.spyOn(etcApi, "deleteEtcBusinessBatch").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const deleteButton = await within(page).findByRole("button", { name: "删除批次 5月批次" });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteBusinessBatch).toHaveBeenCalledWith("etc-business-linked-001", {
        expectedVersion: 8,
        reason: "用户在 ETC 页面删除未提交业务批次。",
      });
    });
  });

  test("manually confirms a draft-created business batch as submitted without refresh entry", async () => {
    const user = userEvent.setup();
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-business-linked-001",
      status: "imported",
      version: 13,
      title: "新建ETC对账批次",
      periodStart: "2026-03-28",
      periodEnd: "2026-04-27",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-04-30",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "1673.30",
      etcInvoiceAmount: "1673.30",
      supplementAmount: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云A361HX", "云A516HJ", "云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "etc-import-business-linked-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 37,
      importedInvoiceAmount: "1673.30",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    const linkedBusinessBatch = {
      businessBatchId: "etc-business-linked-001",
      taskId: "etc-recon-imported-business-linked-001",
      status: "oa_confirmation_pending",
      version: 8,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc-import-business-linked-001"],
      submissionBatchId: "etc-submission-linked-001",
      externalEtcBatchId: "ETC-2026-LINKED",
      oaDraftId: "oa-draft-linked-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-linked-001",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 37, amount: "1673.30" },
      invoiceIds: [],
      importAttempts: [],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
    };
    const submittedBatch = {
      ...linkedBusinessBatch,
      status: "manually_marked_submitted",
      version: 9,
      oaProcessStatus: "manual_without_oa_row",
      invoiceItems: [],
    };
    const fetchReconciliationTasks = vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [importedTask] } as never)
      .mockResolvedValue({ items: [] } as never);
    const fetchBusinessBatches = vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockImplementation((query = {}) => Promise.resolve({
      counts: { active: query.status === "submitted" ? 0 : 1, submitted: query.status === "submitted" ? 1 : 0 },
      items: query.status === "submitted" ? [submittedBatch] : [linkedBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never));
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue({
      ...linkedBusinessBatch,
      invoiceItems: [],
    } as never);
    const manualOaStatus = vi.spyOn(etcApi, "manualEtcBusinessBatchOaStatus").mockResolvedValue(submittedBatch as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const oaStatusPanel = await within(page).findByRole("region", { name: "审批提交确认" });
    const openDraftButton = within(oaStatusPanel).getByRole("button", { name: "打开草稿" });
    expect(openDraftButton).toBeEnabled();
    await user.click(openDraftButton);
    expect(openMock).toHaveBeenCalledWith(
      "https://oa.example.test/draft/oa-draft-linked-001#/normal/forms/form/2?formId=2",
      "_blank",
      "noopener,noreferrer",
    );
    expect(within(oaStatusPanel).queryByRole("button", { name: "刷新检测" })).not.toBeInTheDocument();
    expect(within(oaStatusPanel).queryByRole("button", { name: "撤销草稿" })).not.toBeInTheDocument();
    expect(within(oaStatusPanel).queryByRole("button", { name: "异常处理" })).not.toBeInTheDocument();
    expect(within(oaStatusPanel).queryByLabelText("人工处理原因")).not.toBeInTheDocument();
    await user.click(within(oaStatusPanel).getByRole("button", { name: "已提交" }));

    await waitFor(() => {
      expect(manualOaStatus).toHaveBeenCalledWith("etc-business-linked-001", {
        decision: "submitted",
        expectedVersion: 8,
        reason: "用户确认审批草稿已提交。",
      });
    });
    await waitFor(() => expect(fetchReconciliationTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(fetchBusinessBatches).toHaveBeenCalledWith(expect.objectContaining({ status: "submitted" }));
    });
    await waitFor(() => expect(within(page).getByRole("radio", { name: "未提交 0" })).toBeInTheDocument());
    expect(within(page).getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    expect(within(page).getByTestId("etc-batch-row-etc-business-linked-001")).toHaveTextContent("人工确认已提交");
    expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-imported-business-linked-001")).not.toBeInTheDocument();
  });

  test("keeps a task-scoped business batch visible after manual OA submission and submitted-tab reload", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-business-linked-001",
      status: "imported",
      version: 6,
      title: "3.28-4.27",
      periodStart: "2026-03-28",
      periodEnd: "2026-04-27",
      statementPeriodStart: "2026-03-28",
      statementPeriodEnd: "2026-04-27",
      oaTotalAmount: "1673.30",
      etcInvoiceAmount: "1673.30",
      supplementAmount: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云A361HX", "云A516HJ", "云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "etc-import-business-linked-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 37,
      importedInvoiceAmount: "1673.30",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    const linkedBusinessBatch = businessBatchFixture({
      businessBatchId: "etc-business-linked-001",
      taskId: "etc-recon-imported-business-linked-001",
      status: "oa_confirmation_pending",
      version: 8,
      importBatchIds: ["etc-import-business-linked-001"],
      submissionBatchId: "etc-submission-linked-001",
      externalEtcBatchId: "ETC-2026-LINKED",
      oaDraftId: "oa-draft-linked-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-linked-001",
      invoiceSummary: { count: 37, amount: "1673.30" },
      invoiceIds: [],
    });
    const submittedBatch = {
      ...linkedBusinessBatch,
      status: "manually_marked_submitted",
      version: 9,
      oaProcessStatus: "manual_without_oa_row",
      invoiceItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [importedTask] } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockImplementation((query = {}) => Promise.resolve({
      counts: { active: query.status === "submitted" ? 0 : 1, submitted: query.status === "submitted" ? 1 : 0 },
      items: query.status === "submitted" ? [submittedBatch] : [linkedBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never));
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockImplementation((businessBatchId: string) => Promise.resolve({
      ...(businessBatchId === "etc-business-linked-001" ? linkedBusinessBatch : submittedBatch),
      invoiceItems: [],
    } as never));
    vi.spyOn(etcApi, "manualEtcBusinessBatchOaStatus").mockResolvedValue(submittedBatch as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const oaStatusPanel = await within(page).findByRole("region", { name: "审批提交确认" });
    await user.click(within(oaStatusPanel).getByRole("button", { name: "已提交" }));
    await waitFor(() => expect(within(page).getByRole("radio", { name: "已提交 1" })).toBeInTheDocument());

    await user.click(within(page).getByRole("radio", { name: "已提交 1" }));

    expect(await within(page).findByTestId("etc-batch-row-etc-business-linked-001")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-business-linked-001")).toHaveTextContent("人工确认已提交");
  });

  test("manually confirms a draft-created business batch as not submitted", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const detectingBatch = businessBatchFixture({
      businessBatchId: "etc-business-manual-not-submitted-001",
      status: "oa_confirmation_pending",
      version: 8,
    });
    const notSubmittedBatch = {
      ...detectingBatch,
      status: "manually_marked_not_submitted",
      version: 9,
      submissionBatchId: "",
      externalEtcBatchId: "",
      oaDraftId: "",
      oaDraftUrl: "",
      invoiceItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [detectingBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue({
      ...detectingBatch,
      invoiceItems: [],
    } as never);
    const manualOaStatus = vi.spyOn(etcApi, "manualEtcBusinessBatchOaStatus").mockResolvedValue(notSubmittedBatch as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const oaStatusPanel = await within(page).findByRole("region", { name: "审批提交确认" });
    expect(within(oaStatusPanel).queryByRole("button", { name: "刷新检测" })).not.toBeInTheDocument();
    await user.click(within(oaStatusPanel).getByRole("button", { name: "未提交" }));
    await waitFor(() => {
      expect(manualOaStatus).toHaveBeenCalledWith("etc-business-manual-not-submitted-001", {
        decision: "not_submitted",
        expectedVersion: 8,
        reason: "用户确认审批草稿未提交。",
      });
    });
    expect(within(oaStatusPanel).queryByLabelText("人工处理原因")).not.toBeInTheDocument();
    expect(within(page).getByRole("radio", { name: "未提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("radio", { name: "已提交 0" })).toBeInTheDocument();
  });

  test("surfaces manual OA status errors and keeps the confirmation actions available", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const detectingBatch = businessBatchFixture({
      businessBatchId: "etc-business-manual-fail-001",
      status: "oa_confirmation_pending",
      version: 8,
    });
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [detectingBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue({
      ...detectingBatch,
      invoiceItems: [],
    } as never);
    const manualOaStatus = vi
      .spyOn(etcApi, "manualEtcBusinessBatchOaStatus")
      .mockRejectedValue(new Error("人工处理失败，请重新确认 OA 状态。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const oaStatusPanel = await within(page).findByRole("region", { name: "审批提交确认" });
    await user.click(within(oaStatusPanel).getByRole("button", { name: "已提交" }));

    await waitFor(() => {
      expect(manualOaStatus).toHaveBeenCalledWith("etc-business-manual-fail-001", {
        decision: "submitted",
        reason: "用户确认审批草稿已提交。",
        expectedVersion: 8,
      });
    });
    expect(await within(page).findByText("人工处理失败，请重新确认 OA 状态。")).toBeInTheDocument();
    expect(within(oaStatusPanel).getByRole("button", { name: "已提交" })).toBeEnabled();
    expect(within(oaStatusPanel).getByRole("button", { name: "未提交" })).toBeEnabled();
    expect(within(page).getByTestId("etc-batch-row-etc-business-manual-fail-001")).toBeInTheDocument();
  });

  test("can retry manual OA status confirmation after a transient failure", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const detectingBatch = businessBatchFixture({
      businessBatchId: "etc-business-manual-retry-001",
      status: "oa_confirmation_pending",
      version: 8,
    });
    const submittedBatch = {
      ...detectingBatch,
      status: "manually_marked_submitted",
      version: 9,
      oaProcessStatus: "manual_without_oa_row",
      invoiceItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockImplementation((query = {}) => Promise.resolve({
      counts: { active: query.status === "submitted" ? 0 : 1, submitted: query.status === "submitted" ? 1 : 0 },
      items: query.status === "submitted" ? [submittedBatch] : [detectingBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never));
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockImplementation(() => Promise.resolve({
      ...detectingBatch,
      invoiceItems: [],
    } as never));
    const manualOaStatus = vi
      .spyOn(etcApi, "manualEtcBusinessBatchOaStatus")
      .mockRejectedValueOnce(new Error("人工确认暂时失败，请重试。") as never)
      .mockResolvedValueOnce(submittedBatch as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const oaStatusPanel = await within(page).findByRole("region", { name: "审批提交确认" });
    await user.click(within(oaStatusPanel).getByRole("button", { name: "已提交" }));

    await waitFor(() => expect(manualOaStatus).toHaveBeenCalledTimes(1));
    expect(manualOaStatus).toHaveBeenLastCalledWith("etc-business-manual-retry-001", {
      decision: "submitted",
      reason: "用户确认审批草稿已提交。",
      expectedVersion: 8,
    });
    expect(await within(page).findByText("人工确认暂时失败，请重试。")).toBeInTheDocument();
    expect(within(page).getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    expect(within(page).getByRole("radio", { name: "已提交 0" })).toBeInTheDocument();
    expect(within(oaStatusPanel).getByRole("button", { name: "已提交" })).toBeEnabled();

    await user.click(within(oaStatusPanel).getByRole("button", { name: "已提交" }));

    await waitFor(() => expect(manualOaStatus).toHaveBeenCalledTimes(2));
    expect(manualOaStatus).toHaveBeenLastCalledWith("etc-business-manual-retry-001", {
      decision: "submitted",
      reason: "用户确认审批草稿已提交。",
      expectedVersion: 8,
    });
    await waitFor(() => expect(within(page).queryByText("人工确认暂时失败，请重试。")).not.toBeInTheDocument());
    await waitFor(() => expect(within(page).getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true"));
    expect(within(page).getByTestId("etc-batch-row-etc-business-manual-retry-001")).toHaveTextContent("人工确认已提交");
  });

  test("shows the reconciliation workspace with upload blocks, statuses, supplements, and parse issues", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("button", { name: "新建批次" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("3月批次");
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("发票 2 + 补充凭证 1");
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("金额 120.00 元");

    expect(within(page).queryByRole("group", { name: "票根网导入方式" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).getByLabelText("上传信用卡账单")).toBeInTheDocument();
    expect(within(page).queryByLabelText("上传补充凭证")).not.toBeInTheDocument();
    expect(within(page).getByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(page).getByRole("region", { name: "ETC批次流程" })).toBeInTheDocument();
    expect(within(page).getByLabelText("ETC对账文件上传")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "补ETC发票" })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeDisabled();

    expect(within(page).getByText("信用卡侧")).toBeInTheDocument();
    expect(within(page).getByText("票根/补充凭证侧")).toBeInTheDocument();
    expect(within(page).getByRole("table", { name: "ETC双侧核对明细" })).toBeInTheDocument();
    await openEtcDisclosure(page, user, /人工处理/);
    expect(within(page).getByRole("region", { name: "人工核对处理" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "接受推荐票根" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "关联所选记录" })).toBeDisabled();
    expect(within(page).getByText("ETC补充凭证")).toBeInTheDocument();
    await openEtcDisclosure(page, user, /解析异常/);
    expect(within(page).getByText(/票根网缺少车牌号/)).toBeInTheDocument();

    expect(within(page).getByRole("region", { name: "ETC批次详情" })).toBeInTheDocument();
  });

  test("renders the batch-level file drop upload boxes in the ticket-root import area", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByLabelText("上传信用卡账单");
    const uploadRegion = page.querySelector('[aria-label="ETC对账文件上传"]');
    if (!(uploadRegion instanceof HTMLElement)) {
      throw new Error("Expected upload region to render.");
    }
    const dropGrid = uploadRegion.querySelector(".etc-upload-drop-grid");

    expect(dropGrid).toBeInstanceOf(HTMLElement);
    expect(within(dropGrid as HTMLElement).getByLabelText("上传信用卡账单")).toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByLabelText("上传补充凭证")).not.toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).getByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByRole("button", { name: "补ETC发票" })).not.toBeInTheDocument();
  });

  test("uploads a credit-card statement through the selected task and refreshes the workspace", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
    const uploadBox = await within(page).findByLabelText("上传信用卡账单");
    const input = uploadBox.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) {
      throw new Error("Expected credit-card statement upload input to render.");
    }
    expect(input).toHaveAttribute("accept", ".pdf,application/pdf");

    const statement = new File(["%PDF-1.4\n"], "ccb-statement.pdf", { type: "application/pdf" });
    await user.upload(input, statement);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/credit-card-statement",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/credit-card-statement")?.[1] as RequestInit;
    const formData = request.body as FormData;
    expect(formData.get("expectedVersion")).toBe("3");
    expect((formData.getAll("files") as File[])[0]).toMatchObject({ name: "ccb-statement.pdf", type: "application/pdf" });
    expect(await within(page).findByText("2026-02 ETC批次 / v4")).toBeInTheDocument();
  });

  test("surfaces credit-card statement upload errors and keeps the existing task version", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/credit-card-statement")) {
        return new Response(
          JSON.stringify({ error: "parse_failed", message: "信用卡账单解析失败，请检查 PDF 文件。" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
    const uploadBox = await within(page).findByLabelText("上传信用卡账单");
    const input = uploadBox.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) {
      throw new Error("Expected credit-card statement upload input to render.");
    }

    await user.upload(input, new File(["bad pdf"], "bad-statement.pdf", { type: "application/pdf" }));

    expect(await within(page).findByText("信用卡账单解析失败，请检查 PDF 文件。")).toBeInTheDocument();
    expect(within(page).getByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
  });

  test("uploads a supplement from an unmatched card row with a delta note", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const initialTask = {
      taskId: "etc-recon-row-supplement-001",
      status: "reviewing",
      version: 5,
      title: "2026-03 ETC 对账",
      periodStart: "2026-03-03",
      periodEnd: "2026-03-03",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [
        {
          itemId: "card-unmatched-001",
          transactionDate: "2026-03-03",
          postingDate: "2026-03-04",
          cardLast4: "3632",
          description: "高速停车费",
          amount: "25.00",
          settlementAmount: "25.00",
          isEtcCandidate: true,
          candidateReason: "ETC关键词",
          recommendationStatus: "missing_ticket",
          manualResolution: "unresolved",
          manualResolutionReason: "",
          reviewNote: "",
        },
      ],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    const updatedTask = {
      ...initialTask,
      version: 6,
      supplementAmount: "25.00",
      supplementCount: 1,
      canConfirm: true,
      creditCardItems: [
        {
          ...initialTask.creditCardItems[0],
          manualResolution: "covered_by_supplement",
          reviewNote: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      ],
      supplementEvidences: [
        {
          evidenceId: "supplement-row-001",
          sourceName: "parking.pdf",
          evidenceKind: "non_etc_invoice",
          amount: "23.00",
          paidAt: "2026-03-03",
          merchantName: "停车场",
          tags: ["ETC补充凭证"],
          includeInEtcZipCheck: false,
          includeInOaSubmission: true,
          includeInWorkbench: true,
        },
      ],
      reconciledItems: [
        {
          itemId: "RECONCILED-card-unmatched-001",
          creditCardItemId: "card-unmatched-001",
          ticketRootItemIds: [],
          supplementEvidenceIds: ["supplement-row-001"],
          resolution: "covered_by_supplement",
          note: "凭证少开 2 元，按信用卡实际支出提交。",
          claimAmount: "25.00",
          evidenceAmount: "23.00",
          amountDelta: "2.00",
          amountDeltaNote: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      ],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [initialTask] } as never);
    const uploadSupplement = vi.spyOn(etcApi, "uploadEtcSupplementEvidenceForCard").mockResolvedValue(updatedTask as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "上传补充凭证覆盖 高速停车费" }));
    const dialog = await screen.findByRole("dialog", { name: "上传补充凭证" });
    await user.upload(within(dialog).getByLabelText("选择补充凭证文件"), new File(["金额 23.00"], "parking.pdf", { type: "application/pdf" }));
    await user.type(within(dialog).getByLabelText("差异说明"), "凭证少开 2 元，按信用卡实际支出提交。");
    await user.click(within(dialog).getByRole("button", { name: "上传并覆盖" }));

    await waitFor(() => {
      expect(uploadSupplement).toHaveBeenCalledWith(
        "etc-recon-row-supplement-001",
        "card-unmatched-001",
        [expect.objectContaining({ name: "parking.pdf" })],
        5,
        {
          evidenceKind: "non_etc_invoice",
          note: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      );
    });
    expect(await within(page).findByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-reconciliation-row-card-unmatched-001")).toHaveTextContent("23.00");
  });

  test("keeps the supplement upload dialog open when supplement upload fails", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const initialTask = {
      taskId: "etc-recon-supplement-fail-001",
      status: "reviewing",
      version: 5,
      title: "2026-03 ETC 对账",
      periodStart: "2026-03-03",
      periodEnd: "2026-03-03",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [
        {
          itemId: "card-supplement-fail-001",
          transactionDate: "2026-03-03",
          postingDate: "2026-03-04",
          cardLast4: "3632",
          description: "高速停车费",
          amount: "25.00",
          settlementAmount: "25.00",
          isEtcCandidate: true,
          candidateReason: "ETC关键词",
          recommendationStatus: "missing_ticket",
          manualResolution: "unresolved",
          manualResolutionReason: "",
          reviewNote: "",
        },
      ],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [initialTask] } as never);
    const uploadSupplement = vi
      .spyOn(etcApi, "uploadEtcSupplementEvidenceForCard")
      .mockRejectedValue(new Error("补充凭证金额无法识别，请补充差异说明。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "上传补充凭证覆盖 高速停车费" }));
    const dialog = await screen.findByRole("dialog", { name: "上传补充凭证" });
    await user.upload(within(dialog).getByLabelText("选择补充凭证文件"), new File(["bad"], "parking.pdf", { type: "application/pdf" }));
    await user.click(within(dialog).getByRole("button", { name: "上传并覆盖" }));

    expect(await within(page).findByText("补充凭证金额无法识别，请补充差异说明。")).toBeInTheDocument();
    expect(uploadSupplement).toHaveBeenCalledWith(
      "etc-recon-supplement-fail-001",
      "card-supplement-fail-001",
      expect.any(Array),
      5,
      { evidenceKind: "non_etc_invoice", note: "" },
    );
    expect(uploadSupplement.mock.calls[0]?.[2][0]).toMatchObject({ name: "parking.pdf" });
    expect(screen.getByRole("dialog", { name: "上传补充凭证" })).toBeInTheDocument();
    expect(within(page).getByText("2026-03 ETC批次 / v5")).toBeInTheDocument();
  });

  test("uploads ticket-root TXT files through the ticket-root files endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    expect(txtUploadBox).toBeEnabled();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();

    const txtInput = txtUploadBox.querySelector('input[type="file"]');
    if (!(txtInput instanceof HTMLInputElement)) {
      throw new Error("Expected ticket-root TXT upload input to render.");
    }
    expect(txtInput).toHaveAttribute("accept", ".txt,text/plain");

    const txtFile = new File(["车牌号：云A516HJ\n交易时间：2026-04-02 13:30:29交易金额：￥57.95"], "云A516HJ", { type: "text/plain" });
    await user.upload(txtInput, txtFile);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")?.[1] as RequestInit;
    const formData = request.body as FormData;
    expect(formData.get("expectedVersion")).toBe("3");
    expect((formData.getAll("files") as File[])[0]).toMatchObject({ name: "云A516HJ", type: "text/plain" });
  });

  test("uploads ticket-root TXT files by dropping them on the upload box", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    const txtFile = new File(["车牌号：云A516HJ\n交易时间：2026-04-02 13:30:29交易金额：￥57.95"], "云A516HJ.txt", { type: "text/plain" });

    fireEvent.dragEnter(txtUploadBox, { dataTransfer: { files: [txtFile] } });
    fireEvent.dragOver(txtUploadBox, { dataTransfer: { files: [txtFile] } });
    fireEvent.drop(txtUploadBox, { dataTransfer: { files: [txtFile] } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")?.[1] as RequestInit;
    const formData = request.body as FormData;
    expect((formData.getAll("files") as File[])[0]).toMatchObject({ name: "云A516HJ.txt", type: "text/plain" });
  });

  test("surfaces ticket-root upload wrong-slot errors from the backend", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")) {
        return new Response(
          JSON.stringify({
            error: "wrong_reconciliation_source_kind",
            message: "检测到信用卡账单内容，请上传到信用卡账单入口。",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    const txtInput = txtUploadBox.querySelector('input[type="file"]');
    if (!(txtInput instanceof HTMLInputElement)) {
      throw new Error("Expected ticket-root TXT upload input to render.");
    }
    await user.upload(txtInput, new File(["交易日期,入账金额"], "ccb-statement.txt", { type: "text/plain" }));

    expect(await within(page).findByText("检测到信用卡账单内容，请上传到信用卡账单入口。")).toBeInTheDocument();
    expect(within(page).getByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
  });

  test("can retry ticket-root TXT upload after a transient failure", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    let uploadFailuresRemaining = 1;
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (
        String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")
        && init?.method === "POST"
        && uploadFailuresRemaining > 0
      ) {
        uploadFailuresRemaining -= 1;
        return new Response(
          JSON.stringify({
            error: "etc_source_file_upload_temporarily_unavailable",
            message: "ETC票根网文件上传暂时失败，请重试。",
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    const txtInput = txtUploadBox.querySelector('input[type="file"]');
    if (!(txtInput instanceof HTMLInputElement)) {
      throw new Error("Expected ticket-root TXT upload input to render.");
    }

    await user.upload(txtInput, new File(["车牌号：云A516HJ\n交易金额：57.95"], "云A516HJ.txt", { type: "text/plain" }));

    expect(await within(page).findByText("ETC票根网文件上传暂时失败，请重试。")).toBeInTheDocument();
    expect(within(page).getByText("2026-02 ETC批次 / v3")).toBeInTheDocument();

    await user.upload(txtInput, new File(["车牌号：云A516HJ\n交易金额：57.95"], "云A516HJ.txt", { type: "text/plain" }));

    await waitFor(() => {
      const uploadCalls = fetchMock.mock.calls.filter(([url, init]) =>
        String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")
        && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(uploadCalls).toHaveLength(2);
    });
    expect(within(page).queryByText("ETC票根网文件上传暂时失败，请重试。")).not.toBeInTheDocument();
    expect(await within(page).findByText("2026-02 ETC批次 / v4")).toBeInTheDocument();
  });

  test("shows source file context, deletes a mutable source file, and fresh tasks do not inherit old issues", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

    const taskWithSourceFiles = {
      taskId: "etc-recon-task-source-001",
      status: "reviewing",
      version: 3,
      title: "2026-04 ETC 对账",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "80.00",
      etcInvoiceAmount: "50.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [
        {
          fileId: "file-ticket-ok",
          sourceKind: "ticket_root",
          originalName: "票根网-成功.pdf",
          hasBlockingIssue: false,
        },
        {
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          hasBlockingIssue: true,
        },
      ],
      parseIssues: [
        {
          issueId: "parse-issue-ticket-bad",
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          severity: "blocking",
          message: "票根网通行项缺少车牌号，不能进入核对。",
          sourcePage: 2,
          sourceLine: null,
          extractionMethod: "ocr",
          fieldName: "vehicle_plate",
        },
      ],
    };
    const taskAfterFileDelete = {
      ...taskWithSourceFiles,
      version: 4,
      sourceFiles: [taskWithSourceFiles.sourceFiles[0]],
      parseIssues: [],
    };
    const freshTask = {
      ...taskWithSourceFiles,
      taskId: "etc-recon-task-fresh-001",
      status: "draft",
      version: 1,
      title: "新建ETC对账批次",
      sourceFiles: [],
      parseIssues: [],
      vehiclePlates: [],
      etcInvoiceCount: 0,
      supplementCount: 0,
    };
    const sourceBusinessBatch = businessBatchFixture({
      businessBatchId: "etc-business-source-files-001",
      taskId: "etc-recon-task-source-001",
      status: "draft",
      version: 3,
      externalEtcBatchId: "2026-04 ETC批次",
      scopeMonth: "2026-04",
      amountBreakdown: { scope_month: "2026-04" },
      importBatchIds: [],
      submissionBatchId: "",
      invoiceSummary: { count: 1, amount: "80.00" },
      invoiceIds: [],
      importAttempts: [],
    });
    const freshBusinessBatch = businessBatchFixture({
      businessBatchId: "etc-business-fresh-001",
      taskId: "etc-recon-task-fresh-001",
      status: "draft",
      version: 1,
      externalEtcBatchId: "新建ETC批次",
      importBatchIds: [],
      submissionBatchId: "",
      invoiceSummary: { count: 0, amount: "0.00" },
      invoiceIds: [],
      importAttempts: [],
    });

    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [sourceBusinessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockImplementation((businessBatchId: string) => Promise.resolve({
      ...(businessBatchId === "etc-business-fresh-001" ? freshBusinessBatch : sourceBusinessBatch),
      invoiceItems: [],
    } as never));
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [taskWithSourceFiles] } as never)
      .mockResolvedValue({ items: [freshTask, taskWithSourceFiles] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(taskWithSourceFiles as never);
    vi.spyOn(etcApi as Record<string, unknown>, "deleteEtcReconciliationSourceFile").mockResolvedValue(taskAfterFileDelete as never);
    const createBatch = vi.spyOn(etcApi, "createEtcBusinessBatch").mockResolvedValue(freshBusinessBatch as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已上传文件/);
    await openEtcDisclosure(page, user, /解析异常/);
    expect(await within(page).findByText("上传文件")).toBeInTheDocument();
    expect(within(page).getByText("票根网-成功.pdf")).toBeInTheDocument();
    expect(within(page).getAllByText("票根网-失败.pdf").length).toBeGreaterThanOrEqual(1);
    expect(within(page).getAllByText("票根网").length).toBeGreaterThanOrEqual(2);
    expect(within(page).getByText("blocking")).toBeInTheDocument();
    expect(within(page).getAllByText(/票根网-失败\.pdf/).length).toBeGreaterThanOrEqual(1);
    expect(within(page).getByText(/第 2 页/)).toBeInTheDocument();
    expect(within(page).getByText(/ocr/)).toBeInTheDocument();
    expect(within(page).getByText(/票根网通行项缺少车牌号/)).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "新建批次" }));
    await waitFor(() => expect(createBatch).toHaveBeenCalledWith({}));
    await waitFor(() => expect(within(page).getByText("新建ETC批次 / v1")).toBeInTheDocument());
    expect(within(page).queryByText("票根网-成功.pdf")).not.toBeInTheDocument();
    expect(within(page).queryByText(/票根网通行项缺少车牌号/)).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "查看批次 4月批次" }));
    await waitFor(() => expect(within(page).getAllByText("票根网-失败.pdf").length).toBeGreaterThanOrEqual(1));
    await user.click(within(page).getByRole("button", { name: "删除源文件 票根网-失败.pdf" }));
    const dialog = await screen.findByRole("dialog", { name: "删除源文件" });
    expect(dialog).toHaveTextContent("票根网-失败.pdf");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect((etcApi as Record<string, unknown>).deleteEtcReconciliationSourceFile).toHaveBeenCalledWith(
        "etc-recon-task-source-001",
        "file-ticket-bad",
        3,
      );
    });
    await waitFor(() => expect(within(page).queryByText("票根网-失败.pdf")).not.toBeInTheDocument());
    expect(within(page).queryByText(/票根网通行项缺少车牌号/)).not.toBeInTheDocument();
  });

  test("blocks source file deletion when the latest task no longer contains that file", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const taskWithSourceFile = {
      taskId: "etc-recon-task-source-stale-001",
      status: "reviewing",
      version: 3,
      title: "2026-04 ETC 对账",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "80.00",
      etcInvoiceAmount: "50.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [
        {
          fileId: "file-ticket-stale",
          sourceKind: "ticket_root",
          originalName: "票根网-已变化.txt",
          hasBlockingIssue: false,
        },
      ],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [taskWithSourceFile] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...taskWithSourceFile,
      version: 4,
      sourceFiles: [],
    } as never);
    const deleteSourceFile = vi.spyOn(etcApi as Record<string, unknown>, "deleteEtcReconciliationSourceFile");

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已上传文件/);
    await within(page).findByText("票根网-已变化.txt");
    await user.click(within(page).getByRole("button", { name: "删除源文件 票根网-已变化.txt" }));
    const dialog = await screen.findByRole("dialog", { name: "删除源文件" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    expect(await within(page).findByText("源文件已变化，请刷新后重试。")).toBeInTheDocument();
    expect(deleteSourceFile).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "删除源文件" })).toBeInTheDocument();
  });

  test("can retry source file deletion after a transient failure", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const taskWithSourceFile = {
      taskId: "etc-recon-task-source-retry-001",
      status: "reviewing",
      version: 3,
      title: "2026-04 ETC 对账",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "80.00",
      etcInvoiceAmount: "50.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [
        {
          fileId: "file-ticket-retry",
          sourceKind: "ticket_root",
          originalName: "票根网-重试.txt",
          hasBlockingIssue: false,
        },
      ],
      parseIssues: [],
    };
    const taskAfterFileDelete = {
      ...taskWithSourceFile,
      version: 4,
      sourceFiles: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [taskWithSourceFile] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(taskWithSourceFile as never);
    const deleteSourceFile = vi.spyOn(etcApi as Record<string, unknown>, "deleteEtcReconciliationSourceFile")
      .mockRejectedValueOnce(new Error("ETC源文件删除暂时失败，请重试。") as never)
      .mockResolvedValueOnce(taskAfterFileDelete as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已上传文件/);
    await within(page).findByText("票根网-重试.txt");
    await user.click(within(page).getByRole("button", { name: "删除源文件 票根网-重试.txt" }));
    const dialog = await screen.findByRole("dialog", { name: "删除源文件" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    expect(await within(page).findByText("ETC源文件删除暂时失败，请重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "删除源文件" })).toBeInTheDocument();
    expect(within(page).getByText("票根网-重试.txt")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteSourceFile).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "删除源文件" })).not.toBeInTheDocument();
    });
    expect(within(page).queryByText("ETC源文件删除暂时失败，请重试。")).not.toBeInTheDocument();
    expect(within(page).queryByText("票根网-重试.txt")).not.toBeInTheDocument();
  });

  test("removes legacy ticket-root mode controls and keeps only TXT ticket-root upload", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(page).queryByRole("group", { name: "票根网导入方式" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "TXT文件" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "点击粘贴票根网文本" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("disables ticket-root TXT upload when a legacy non-TXT ticket-root source exists", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-manual-existing",
          status: "reviewing",
          version: 3,
          title: "已有手工粘贴",
          periodStart: null,
          periodEnd: null,
          statementPeriodStart: null,
          statementPeriodEnd: null,
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "paste-source-1",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云ADA0381-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toHaveAttribute("aria-disabled", "true");
    expect(within(page).getByText("已有非 TXT 来源，删除后可导入。")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("auto-selects TXT mode for text ticket-root files and shows each source summary", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-txt-existing",
          status: "reviewing",
          version: 3,
          title: "已有TXT",
          periodStart: "2026-04-01",
          periodEnd: "2026-04-30",
          statementPeriodStart: "2026-04-01",
          statementPeriodEnd: "2026-04-30",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 3,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A516HJ", "云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [
            {
              itemId: "ticket-txt-1",
              sourceFileId: "ticket-txt-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-02 13:30:29",
              amount: "57.95",
              entryStation: "云南沙桥站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-txt-2",
              sourceFileId: "ticket-txt-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-02 11:25:48",
              amount: "88.86",
              entryStation: "云南昆明西站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-txt-3",
              sourceFileId: "ticket-txt-source-2",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-04-08 18:57:17",
              amount: "71.25",
              entryStation: "云南弥勒南站",
              exitStation: "云南小喜村站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
          ],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "ticket-txt-source-1",
              sourceKind: "ticket_root",
              originalName: "云A516HJ",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
            {
              fileId: "ticket-txt-source-2",
              sourceKind: "ticket_root",
              originalName: "云ADA0381.txt",
              contentType: "text/plain",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toBeEnabled();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByText("已有 TXT 源文件，删除后可切换。")).not.toBeInTheDocument();

    await openEtcDisclosure(page, user, /已上传文件/);
    const sourceList = within(page).getByRole("list", { name: "已上传文件列表" });
    const firstSource = within(sourceList).getByText("云A516HJ").closest("li");
    const secondSource = within(sourceList).getByText("云ADA0381.txt").closest("li");
    if (!firstSource || !secondSource) {
      throw new Error("Expected both ticket-root TXT source rows to render.");
    }
    expect(firstSource).toHaveTextContent("票根网");
    expect(firstSource).toHaveTextContent("云A516HJ / 已解析 2 条");
    expect(firstSource).toHaveTextContent("金额合计 146.81");
    expect(firstSource).toHaveTextContent("日期 2026-04-02");

    expect(secondSource).toHaveTextContent("票根网");
    expect(secondSource).toHaveTextContent("云ADA0381 / 已解析 1 条");
    expect(secondSource).toHaveTextContent("金额合计 71.25");
    expect(secondSource).toHaveTextContent("日期 2026-04-08");
    expect(within(page).queryByRole("button", { name: /编辑票根网文本/ })).not.toBeInTheDocument();
  });

  test("shows legacy manual ticket-root source summaries only in the uploaded source list", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-manual-existing",
          status: "reviewing",
          version: 3,
          title: "已有手工粘贴",
          periodStart: "2026-04-01",
          periodEnd: "2026-04-30",
          statementPeriodStart: "2026-04-01",
          statementPeriodEnd: "2026-04-30",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 4,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A516HJ", "云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [
            {
              itemId: "ticket-paste-1",
              sourceFileId: "paste-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-15 12:24:08",
              amount: "146.98",
              entryStation: "云南昆明西站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-paste-2",
              sourceFileId: "paste-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-02 13:30:29",
              amount: "57.95",
              entryStation: "云南沙桥站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-paste-3",
              sourceFileId: "paste-source-2",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-04-08 18:57:17",
              amount: "71.25",
              entryStation: "云南弥勒南站",
              exitStation: "云南小喜村站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
          ],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "paste-source-1",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云A516HJ-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
            {
              fileId: "paste-source-2",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云ADA0381-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已上传文件/);
    const sourceList = await within(page).findByRole("list", { name: "已上传文件列表" });
    const firstSource = within(sourceList).getByText("票根网手工粘贴-云A516HJ-202604-1.txt").closest("li");
    const secondSource = within(sourceList).getByText("票根网手工粘贴-云ADA0381-202604-1.txt").closest("li");
    if (!firstSource || !secondSource) {
      throw new Error("Expected both legacy ticket-root source rows to be rendered.");
    }
    expect(firstSource).toHaveTextContent("云A516HJ");
    expect(firstSource).toHaveTextContent("已解析 2 条");
    expect(firstSource).toHaveTextContent("金额合计 204.93");
    expect(firstSource).toHaveTextContent("日期 2026-04-02 至 2026-04-15");

    expect(secondSource).toHaveTextContent("云ADA0381");
    expect(secondSource).toHaveTextContent("已解析 1 条");
    expect(secondSource).toHaveTextContent("金额合计 71.25");
    expect(secondSource).toHaveTextContent("日期 2026-04-08");
    expect(within(page).queryByRole("button", { name: /编辑票根网文本/ })).not.toBeInTheDocument();
    expect(within(page).queryByText("已解析 3 条")).not.toBeInTheDocument();
  });

  test("disables ticket-root TXT upload when a legacy PDF ticket-root source exists", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-pdf-existing",
          status: "reviewing",
          version: 3,
          title: "已有PDF",
          periodStart: null,
          periodEnd: null,
          statementPeriodStart: null,
          statementPeriodEnd: null,
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "ticket-pdf-1",
              sourceKind: "ticket_root",
              originalName: "票根网.pdf",
              contentType: "application/pdf",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toHaveAttribute("aria-disabled", "true");
    expect(within(page).getByText("已有非 TXT 来源，删除后可导入。")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("renders paired reconciliation table without row status chips or station wording", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(page).getByRole("button", { name: "全选" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "全选配对项" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "清空" })).toBeInTheDocument();

    expect(within(table).getByRole("columnheader", { name: "交易日" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "交易日/银行记账日" })).not.toBeInTheDocument();
    expect(within(table).queryByText("银行记账日")).not.toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "交易描述" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "交易时间" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "金额 / 车牌" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "站点/类型" })).not.toBeInTheDocument();

    const suggestedPairRow = within(table).getByTestId("etc-reconciliation-row-card-item-suggested");
    expect(suggestedPairRow).toHaveAttribute("data-highlight", "matched");
    expect(suggestedPairRow).toHaveTextContent("财付通-微信支付-贵州黔通智联");
    expect(suggestedPairRow).toHaveTextContent("2026-02-27");
    expect(suggestedPairRow).toHaveTextContent("10:00:00");
    expect(suggestedPairRow).toHaveTextContent("云ADA0381");
    expect(suggestedPairRow).toHaveTextContent("30.00");

    const missingRow = within(table).getByTestId("etc-reconciliation-row-card-item-missing");
    expect(missingRow).toHaveAttribute("data-highlight", "missing");
    expect(within(missingRow).getByTestId("etc-reconciliation-card-cell-card-item-missing")).toHaveAttribute("data-highlight", "missing");

    const extraRow = within(table).getByTestId("etc-reconciliation-row-right-ticket-item-extra");
    expect(extraRow).toHaveAttribute("data-highlight", "extra");
    expect(within(extraRow).getByTestId("etc-reconciliation-evidence-cell-ticket-item-extra")).toHaveAttribute("data-highlight", "extra");

    expect(within(suggestedPairRow).getByTestId("etc-card-date-transaction-card-item-suggested")).toHaveTextContent("2026-02-27");
    expect(within(suggestedPairRow).queryByTestId("etc-card-date-posting-card-item-suggested")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("2026-02-28")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("2026-02")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("交易")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("记账")).not.toBeInTheDocument();
    expect(within(table).queryByText("02-27")).not.toBeInTheDocument();
    expect(within(table).queryByText("02-28")).not.toBeInTheDocument();
    expect(within(table).getByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(table).queryByText("suggested")).not.toBeInTheDocument();
    expect(within(table).queryByText("系统建议")).not.toBeInTheDocument();
    expect(within(table).queryByText("manual")).not.toBeInTheDocument();
    expect(within(table).queryByText("covered")).not.toBeInTheDocument();
    expect(within(table).queryByText("人工已处理")).not.toBeInTheDocument();
    expect(within(table).queryByText(/昆明东/)).not.toBeInTheDocument();
    expect(within(table).queryByText(/玉溪北/)).not.toBeInTheDocument();

    const compactBlock = page.querySelector(".etc-reconciliation-table-block");
    if (!(compactBlock instanceof HTMLElement)) {
      throw new Error("Expected reconciliation table block to render.");
    }
    expect(getComputedStyle(compactBlock).getPropertyValue("--etc-reconciliation-row-height").trim()).toBe("32px");
    const bodyRowCount = table.querySelectorAll("tbody .etc-reconciliation-table-row").length;
    expect(table.querySelectorAll(".etc-reconciliation-divider")).toHaveLength(2 + bodyRowCount);
    expect(getComputedStyle(within(missingRow).getByTestId("etc-reconciliation-card-cell-card-item-missing")).boxShadow).not.toContain("inset");
    expect(getComputedStyle(within(extraRow).getByTestId("etc-reconciliation-evidence-cell-ticket-item-extra")).boxShadow).not.toContain("inset");
  });

  test("keeps long reconciliation descriptions to one line until expanded", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    const row = within(table).getByTestId("etc-reconciliation-row-card-item-suggested");
    const description = within(row).getByTestId("etc-reconciliation-description-card-item-suggested");

    expect(description).toHaveClass("etc-reconciliation-description--collapsed");
    expect(within(row).getByRole("button", { name: "展开交易描述 card-item-suggested" })).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "展开交易描述 card-item-suggested" }));

    expect(description).toHaveClass("etc-reconciliation-description--expanded");
    expect(within(row).getByRole("button", { name: "收起交易描述 card-item-suggested" })).toBeInTheDocument();
  });

  test("selects reconciliation rows locally with all, paired-only, and clear actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    const rowCheckboxes = [
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-suggested" }),
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-missing" }),
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-covered" }),
      within(table).getByRole("checkbox", { name: "选择核对行 right-ticket-item-extra" }),
    ];

    rowCheckboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());

    await user.click(rowCheckboxes[1]);
    expect(rowCheckboxes[1]).toBeChecked();
    expect(rowCheckboxes[0]).not.toBeChecked();

    await user.click(within(page).getByRole("button", { name: "全选" }));
    rowCheckboxes.forEach((checkbox) => expect(checkbox).toBeChecked());

    await user.click(within(page).getByRole("button", { name: "清空" }));
    rowCheckboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));
    expect(rowCheckboxes[0]).toBeChecked();
    expect(rowCheckboxes[2]).toBeChecked();
    expect(rowCheckboxes[1]).not.toBeChecked();
    expect(rowCheckboxes[3]).not.toBeChecked();
  });

  test("updates confirmation metrics from the checked paired rows", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const metrics = await within(page).findByLabelText("本次确认预览");

    expect(metrics).toHaveTextContent("金额");
    expect(metrics).toHaveTextContent("0.00");
    expect(metrics).toHaveTextContent("范围");
    expect(metrics).toHaveTextContent("-");
    expect(metrics).toHaveTextContent("数量");
    expect(metrics).toHaveTextContent("发票 0 + 补充凭证 0");

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));

    expect(metrics).toHaveTextContent("60.00");
    expect(metrics).toHaveTextContent("2026-02-27");
    expect(metrics).toHaveTextContent("2026-02-28");
    expect(metrics).toHaveTextContent("发票 1 + 补充凭证 1");

    await user.click(within(page).getByRole("button", { name: "清空" }));

    expect(metrics).toHaveTextContent("0.00");
    expect(metrics).toHaveTextContent("-");
    expect(metrics).toHaveTextContent("发票 0 + 补充凭证 0");
  });

  test("submits the checked card item ids when confirming reconciliation and blocks empty selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-001",
          status: "reviewing",
          version: 3,
          title: "2026-02 ETC 对账",
          periodStart: "2026-02-27",
          periodEnd: "2026-02-28",
          statementPeriodStart: "2026-02-01",
          statementPeriodEnd: "2026-02-29",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "7788",
          oaTotalAmount: "120.00",
          etcInvoiceAmount: "90.00",
          supplementAmount: "30.00",
          etcInvoiceCount: 2,
          supplementCount: 1,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          sourceFiles: [],
          parseIssues: [],
          creditCardItems: [
            {
              itemId: "card-item-suggested",
              transactionDate: "2026-02-27",
              postingDate: "2026-02-28",
              cardLast4: "7788",
              description: "财付通-微信支付-贵州黔通智联",
              amount: "30.00",
              settlementAmount: "30.00",
              isEtcCandidate: true,
              candidateReason: "ETC关键词",
              recommendationStatus: "suggested_match",
              manualResolution: "unresolved",
              manualResolutionReason: "",
              reviewNote: "",
            },
            {
              itemId: "card-item-covered",
              transactionDate: "2026-02-28",
              postingDate: "2026-02-29",
              cardLast4: "7788",
              description: "停车费补充凭证",
              amount: "30.00",
              settlementAmount: "30.00",
              isEtcCandidate: false,
              candidateReason: "",
              recommendationStatus: "not_candidate",
              manualResolution: "covered_by_supplement",
              manualResolutionReason: "",
              reviewNote: "",
            },
          ],
          ticketRootItems: [
            {
              itemId: "ticket-item-001",
              sourceFileId: "ticket-file-001",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-02-27T10:00:00",
              amount: "30.00",
              entryStation: "昆明东",
              exitStation: "玉溪北",
              invoiceCount: 1,
              recommendationStatus: "suggested_match",
              linkedCreditCardItemIds: ["card-item-suggested"],
            },
          ],
          supplementEvidences: [
            {
              evidenceId: "supplement-001",
              sourceName: "parking.pdf",
              evidenceKind: "non_etc_invoice",
              amount: "30.00",
              paidAt: "2026-02-28",
              merchantName: "停车场",
              tags: ["ETC补充凭证"],
              includeInEtcZipCheck: false,
              includeInOaSubmission: true,
              includeInWorkbench: true,
            },
          ],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeDisabled();

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeEnabled();
    await user.click(within(page).getByRole("button", { name: "确认对账" }));

    await waitFor(() => {
      const confirmRequest = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/confirm"))?.[1] as RequestInit | undefined;
      expect(confirmRequest).toBeDefined();
      expect(JSON.parse(String(confirmRequest?.body))).toMatchObject({
        expectedVersion: 3,
        confirmedCreditCardItemIds: ["card-item-suggested"],
      });
    });
  });

  test("surfaces reconciliation confirmation errors and keeps the current task state", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/confirm")) {
        return new Response(
          JSON.stringify({ error: "stale_task", message: "对账任务版本已变化，请刷新后重试。" }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "全选配对项" }));
    await user.click(within(page).getByRole("button", { name: "确认对账" }));

    expect(await within(page).findByText("批次版本已变化，请刷新后重试。")).toBeInTheDocument();
    expect(within(page).getByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeEnabled();
  });

  test("surfaces reopen errors and keeps a ready task ready for retry", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const readyTask = {
      taskId: "etc-recon-ready-reopen-001",
      status: "ready_for_import",
      version: 7,
      title: "2026-04 ETC 待导入",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [readyTask] } as never);
    const reopenTask = vi.spyOn(etcApi, "reopenEtcReconciliationTask").mockRejectedValue(new Error("重新打开失败，任务已进入导入流程。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("2026-04 ETC 待导入 / v7")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "重新打开" }));

    await waitFor(() => expect(reopenTask).toHaveBeenCalledWith("etc-recon-ready-reopen-001", 7));
    expect(await within(page).findByText("重新打开失败，任务已进入导入流程。")).toBeInTheDocument();
    expect(within(page).getByText("2026-04 ETC 待导入 / v7")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "重新打开" })).toBeEnabled();
  });

  test("reopens a ready reconciliation task and returns it to reviewing", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const readyTask = {
      taskId: "etc-recon-ready-reopen-success-001",
      status: "ready_for_import",
      version: 7,
      title: "2026-04 ETC 待导入",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [readyTask] } as never);
    const reopenTask = vi.spyOn(etcApi, "reopenEtcReconciliationTask").mockResolvedValue({
      ...readyTask,
      status: "reviewing",
      version: 8,
      confirmedItemSetHash: "",
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByText("2026-04 ETC 待导入 / v7");
    await user.click(within(page).getByRole("button", { name: "重新打开" }));

    await waitFor(() => expect(reopenTask).toHaveBeenCalledWith("etc-recon-ready-reopen-success-001", 7));
    expect(await within(page).findByText("2026-04 ETC 待导入 / v8")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "重新打开" })).not.toBeInTheDocument();
  });

  test("shows imported task invoices under the reconciliation task and collapses both task blocks", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-001",
      etcBatchId: "etc-batch-imported-001",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [importedTask],
    } as never);
    mockFetchEtcInvoices([
      {
        id: "etc-inv-imported-001",
        invoiceNumber: "ETC-IMPORTED-001",
        issueDate: "2026-03-03",
        passageStartDate: "2026-03-03",
        passageEndDate: "2026-03-03",
        plateNumber: "云ADA0381",
        sellerName: "云南高速通行费",
        buyerName: "云南溯源科技",
        amountWithoutTax: "28.20",
        taxAmount: "1.80",
        totalAmount: "30.00",
        status: "unsubmitted",
        hasPdf: true,
        hasXml: true,
      },
    ]);
    vi.spyOn(etcApi, "deleteEtcReconciliationTaskImportedInvoices").mockResolvedValue({
      ...importedTask,
      status: "ready_for_import",
      version: 9,
      importBatchId: "",
      etcBatchId: "",
    } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...importedTask,
      version: 9,
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已导入发票/);
    const importedInvoiceSection = within(page).getByRole("region", { name: "已导入ETC发票" });
    expect(within(page).getByRole("button", { name: /已导入发票.*1 张/ })).toBeInTheDocument();
    const removeButton = await within(importedInvoiceSection).findByRole("button", { name: "移除发票" });
    expect(removeButton).toBeEnabled();
    expect(within(importedInvoiceSection).getByRole("table", { name: "已导入ETC发票明细" })).toBeInTheDocument();
    expect(within(importedInvoiceSection).getByText("ETC-IMPORTED-001")).toBeInTheDocument();
    expect(etcApi.fetchEtcInvoices).toHaveBeenCalledWith({
      importBatchId: "import-session-001",
      page: 1,
      pageSize: 500,
      signal: expect.any(AbortSignal),
    });

    await user.click(removeButton);
    const dialog = await screen.findByRole("dialog", { name: "移除发票" });
    expect(dialog).toHaveTextContent("2026-03 ETC 已导入");
    expect(dialog).toHaveTextContent("1 张");
    await user.click(within(dialog).getByRole("button", { name: "确认移除" }));

    await waitFor(() => {
      expect(etcApi.deleteEtcReconciliationTaskImportedInvoices).toHaveBeenCalledWith("etc-recon-imported-001", 9);
    });
    await waitFor(() => {
      expect(within(page).queryByRole("region", { name: "已导入ETC发票" })).not.toBeInTheDocument();
    });
    expect(within(page).getByText("2026-03 ETC 已导入 / v9")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "移除发票" })).not.toBeInTheDocument());

    const workflowRegion = within(page).getByRole("region", { name: "ETC批次流程" });
    await user.click(within(workflowRegion).getByRole("button", { name: "全部折叠" }));
    expect(within(workflowRegion).queryByRole("table", { name: "ETC双侧核对明细" })).not.toBeInTheDocument();
    await user.click(within(workflowRegion).getByRole("button", { name: "展开流程" }));
    expect(await within(workflowRegion).findByRole("table", { name: "ETC双侧核对明细" })).toBeInTheDocument();

    const detailRegion = within(page).getByRole("region", { name: "ETC批次详情" });
    await user.click(within(detailRegion).getByRole("button", { name: "全部折叠" }));
    expect(within(detailRegion).queryByRole("table", { name: "ETC发票明细" })).not.toBeInTheDocument();
    await user.click(within(detailRegion).getByRole("button", { name: "展开详情" }));
    expect(await within(detailRegion).findByRole("table", { name: "ETC发票明细" })).toBeInTheDocument();
  });

  test("keeps imported invoice removal dialog open when removal fails", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-remove-fail-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-remove-fail-001",
      etcBatchId: "etc-batch-remove-fail-001",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [importedTask] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...importedTask,
      version: 9,
    } as never);
    mockFetchEtcInvoices([
      {
        id: "etc-inv-remove-fail-001",
        invoiceNumber: "ETC-REMOVE-FAIL-001",
        issueDate: "2026-03-03",
        passageStartDate: "2026-03-03",
        passageEndDate: "2026-03-03",
        plateNumber: "云ADA0381",
        sellerName: "云南高速通行费",
        buyerName: "云南溯源科技",
        amountWithoutTax: "28.20",
        taxAmount: "1.80",
        totalAmount: "30.00",
        status: "unsubmitted",
        hasPdf: true,
        hasXml: true,
      },
    ]);
    const removeInvoices = vi
      .spyOn(etcApi, "deleteEtcReconciliationTaskImportedInvoices")
      .mockRejectedValue(new Error("移除发票失败，请刷新后重试。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /已导入发票/);
    const importedInvoiceSection = await within(page).findByRole("region", { name: "已导入ETC发票" });
    await user.click(await within(importedInvoiceSection).findByRole("button", { name: "移除发票" }));

    const dialog = await screen.findByRole("dialog", { name: "移除发票" });
    await user.click(within(dialog).getByRole("button", { name: "确认移除" }));

    await waitFor(() => expect(removeInvoices).toHaveBeenCalledWith("etc-recon-imported-remove-fail-001", 9));
    expect(await within(page).findByText("移除发票失败，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "移除发票" })).toBeInTheDocument();
    expect(page.querySelector(".etc-task-imported-invoices")).toBeInTheDocument();
    expect(within(page).getByText("2026-03 ETC 已导入 / v9")).toBeInTheDocument();
  });

  test("creates OA draft from the selected imported reconciliation task batch", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-imported-submit-001",
          status: "imported",
          version: 11,
          title: "2026-04 ETC 已导入",
          periodStart: "2026-03-28",
          periodEnd: "2026-04-27",
          statementPeriodStart: "2026-03-28",
          statementPeriodEnd: "2026-04-27",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "8514",
          oaTotalAmount: "1673.30",
          etcInvoiceAmount: "1673.30",
          supplementAmount: "0.00",
          etcInvoiceCount: 37,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "sha256:selected",
          importBatchId: "etc_import_batch_0004",
          etcBatchId: "",
          hasImportedInvoices: true,
          importedInvoiceCount: 36,
          importedInvoiceAmount: "1673.30",
          oaDraftBatchId: "",
          oaDraftStatus: "",
          submittedConfirmedAt: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [],
          parseIssues: [],
        },
      ],
    } as never);
    mockFetchEtcInvoices([
      {
        id: "etc-inv-imported-submit-001",
        invoiceNumber: "ETC-IMPORTED-SUBMIT-001",
        issueDate: "2026-04-27",
        passageStartDate: "2026-04-27",
        passageEndDate: "2026-04-27",
        plateNumber: "云ADA0381",
        sellerName: "云南高速通行费",
        buyerName: "云南溯源科技",
        amountWithoutTax: "1624.56",
        taxAmount: "48.74",
        totalAmount: "1673.30",
        status: "unsubmitted",
        hasPdf: true,
        hasXml: true,
      },
    ]);
    const businessBatch = {
      businessBatchId: "etc_business_batch_imported_submit_001",
      taskId: "etc-recon-imported-submit-001",
      status: "imported",
      version: 11,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc_import_batch_0004"],
      submissionBatchId: "",
      externalEtcBatchId: "ETC-2026-OA-001",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 36, amount: "1673.30" },
      invoiceIds: ["etc-inv-imported-submit-001"],
      importAttempts: [
        {
          attemptId: "attempt-imported-submit-001",
          importBatchId: "etc_import_batch_0004",
          status: "imported",
          imported: 36,
          duplicatesSkipped: 0,
          attachmentsCompleted: 0,
          failed: 0,
          createdAt: "2026-05-19T09:00:00+08:00",
        },
      ],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
      invoiceItems: [
        {
          id: "etc-inv-imported-submit-001",
          invoiceNumber: "ETC-IMPORTED-SUBMIT-001",
          issueDate: "2026-04-27",
          passageStartDate: "2026-04-27",
          passageEndDate: "2026-04-27",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "1624.56",
          taxAmount: "48.74",
          totalAmount: "1673.30",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi.spyOn(etcApi, "createEtcBusinessBatchOaDraft").mockResolvedValue({
      ...businessBatch,
      status: "oa_confirmation_pending",
      version: 12,
      submissionBatchId: "etc_batch_submission_001",
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa-draft-001",
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const submitButton = within(page).getByRole("button", { name: "提交审批" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);

    const dialog = await screen.findByRole("dialog", { name: "创建审批草稿" });
    expect(dialog).toHaveTextContent("为当前任务的 36 张发票创建审批草稿，合计 1673.30。");
    expect(dialog).toHaveTextContent("批次：4.27批次");
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc_business_batch_imported_submit_001", { expectedVersion: 11 }));
    expect(openMock).not.toHaveBeenCalled();
  });

  test("deletes an imported reconciliation task through confirmation", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-delete-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-delete-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [importedTask] } as never)
      .mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(importedTask as never);
    mockFetchEtcInvoices([]);
    vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const deleteButton = await within(page).findByRole("button", { name: /删除批次 2026-03 ETC 已导入/ });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("将一并删除已导入发票");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(etcApi.deleteEtcReconciliationTask).toHaveBeenCalledWith("etc-recon-imported-delete-001", 8);
    });
    await waitFor(() => {
      expect(within(page).queryByText("2026-03 ETC 已导入 / v8")).not.toBeInTheDocument();
    });
  });

  test("renders the business batch instead of a duplicate task row when an imported task shares its batch id", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-imported-batch",
          status: "imported",
          version: 5,
          title: "2026-03 ETC 对账",
          periodStart: "2026-03-01",
          periodEnd: "2026-03-31",
          statementPeriodStart: "2026-03-01",
          statementPeriodEnd: "2026-03-31",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "21.35",
          etcInvoiceAmount: "21.35",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A8H66Q"],
          confirmedItemSetHash: "sha256:selected",
          importBatchId: "",
          etcBatchId: "etc-batch-unsubmitted-02",
          oaDraftBatchId: "",
          oaDraftStatus: "",
          submittedConfirmedAt: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-02")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();
    expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-task-imported-batch")).not.toBeInTheDocument();
  });

  test("does not pair same-amount suggested rows without an explicit ticket link", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-unlinked-suggested",
          status: "reviewing",
          version: 1,
          title: "未明确 link 的同金额 suggested",
          periodStart: "2026-04-08",
          periodEnd: "2026-04-10",
          statementPeriodStart: "2026-04-01",
          statementPeriodEnd: "2026-04-30",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "8514",
          oaTotalAmount: "71.25",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          sourceFiles: [],
          parseIssues: [],
          supplementEvidences: [],
          creditCardItems: [
            {
              itemId: "card-unlinked-suggested",
              transactionDate: "2026-04-08",
              postingDate: "2026-04-09",
              cardLast4: "8514",
              description: "高速通行费-同金额未link",
              amount: "71.25",
              settlementAmount: "71.25",
              isEtcCandidate: true,
              candidateReason: "ETC关键词",
              recommendationStatus: "suggested_match",
              manualResolution: "unresolved",
              manualResolutionReason: "",
              reviewNote: "",
            },
          ],
          ticketRootItems: [
            {
              itemId: "ticket-unlinked-suggested",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-04-08T18:57:17",
              amount: "71.25",
              entryStation: "昆明南",
              exitStation: "九龙池",
              invoiceCount: 1,
              recommendationStatus: "suggested_match",
              linkedCreditCardItemIds: [],
            },
          ],
        },
      ],
    } as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });

    const cardOnlyRow = within(table).getByTestId("etc-reconciliation-row-card-unlinked-suggested");
    expect(cardOnlyRow).toHaveAttribute("data-highlight", "missing");
    expect(cardOnlyRow).toHaveTextContent("高速通行费-同金额未link");
    expect(cardOnlyRow).not.toHaveTextContent("云ADA0381");

    const ticketOnlyRow = within(table).getByTestId("etc-reconciliation-row-right-ticket-unlinked-suggested");
    expect(ticketOnlyRow).toHaveAttribute("data-highlight", "extra");
    expect(ticketOnlyRow).toHaveTextContent("云ADA0381");
    expect(ticketOnlyRow).not.toHaveTextContent("高速通行费-同金额未link");
  });

  test("refreshes reconciliation matches from the task API and rerenders explicit links", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    const initialTask = {
      taskId: "etc-recon-refresh-001",
      status: "reviewing",
      version: 4,
      title: "刷新匹配",
      periodStart: "2026-04-08",
      periodEnd: "2026-04-08",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "8514",
      oaTotalAmount: "71.25",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      sourceFiles: [],
      parseIssues: [],
      supplementEvidences: [],
      creditCardItems: [
        {
          itemId: "card-refresh-001",
          transactionDate: "2026-04-08",
          postingDate: "2026-04-09",
          cardLast4: "8514",
          description: "高速通行费-刷新后配对",
          amount: "71.25",
          settlementAmount: "71.25",
          isEtcCandidate: true,
          candidateReason: "ETC关键词",
          recommendationStatus: "suggested_match",
          manualResolution: "unresolved",
          manualResolutionReason: "",
          reviewNote: "",
        },
      ],
      ticketRootItems: [
        {
          itemId: "ticket-refresh-001",
          vehiclePlate: "云ADA0381",
          transactionAt: "2026-04-08T18:57:17",
          amount: "71.25",
          entryStation: "昆明南",
          exitStation: "九龙池",
          invoiceCount: 1,
          recommendationStatus: "suggested_match",
          linkedCreditCardItemIds: [],
        },
      ],
    };
    const refreshedTask = {
      ...initialTask,
      version: 5,
      ticketRootItems: [
        {
          ...initialTask.ticketRootItems[0],
          linkedCreditCardItemIds: ["card-refresh-001"],
        },
      ],
    };

    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [initialTask] } as never);
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-refresh-001/refresh-matches")) {
        return new Response(JSON.stringify(refreshedTask), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(table).getByTestId("etc-reconciliation-row-card-refresh-001")).toHaveAttribute("data-highlight", "missing");
    expect(within(table).getByTestId("etc-reconciliation-row-right-ticket-refresh-001")).toHaveAttribute("data-highlight", "extra");

    await user.click(within(page).getByRole("button", { name: "刷新匹配" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-refresh-001/refresh-matches",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(within(table).getByTestId("etc-reconciliation-row-card-refresh-001")).toHaveAttribute("data-highlight", "matched");
    });
    expect(within(table).queryByTestId("etc-reconciliation-row-right-ticket-refresh-001")).not.toBeInTheDocument();
  });

  test("surfaces refresh-match errors without replacing the current reconciliation rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/refresh-matches")) {
        return new Response(
          JSON.stringify({ error: "matcher_unavailable", message: "匹配服务暂不可用，请稍后重试。" }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(table).getByTestId("etc-reconciliation-row-card-item-missing")).toHaveTextContent("高速通行费");

    await user.click(within(page).getByRole("button", { name: "刷新匹配" }));

    expect(await within(page).findByText("匹配服务暂不可用，请稍后重试。")).toBeInTheDocument();
    expect(within(table).getByTestId("etc-reconciliation-row-card-item-missing")).toHaveTextContent("高速通行费");
    expect(within(page).getByText("2026-02 ETC批次 / v3")).toBeInTheDocument();
  });

  test("manual reconciliation accepts a suggested ticket instead of directly marking an item included", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await openEtcDisclosure(page, user, /人工处理/);
    await user.click(await within(page).findByText("财付通-微信支付-贵州黔通智联"));
    const acceptButton = within(page).getByRole("button", { name: "接受推荐票根" });
    await waitFor(() => expect(acceptButton).toBeEnabled());
    await user.click(acceptButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/items/card-item-suggested",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expectedVersion: 3,
            action: "link_ticket",
            ticketItemId: "ticket-item-001",
          }),
        }),
      );
    });
  });

  test("keeps manual reconciliation actions disabled until required selections exist and validates notes", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const patchItem = vi.spyOn(etcApi, "patchEtcReconciliationItem");

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    await openEtcDisclosure(page, user, /人工处理/);
    expect(within(page).getByRole("button", { name: "接受推荐票根" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "关联所选记录" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "排除非ETC" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "手工确认" })).toBeDisabled();

    await user.selectOptions(within(page).getByLabelText("选择票根/凭证"), "ticket-item-extra");
    expect(within(page).getByRole("button", { name: "关联所选记录" })).toBeDisabled();

    await user.click(within(page).getByText("财付通-微信支付-贵州黔通智联"));
    expect(within(page).getByRole("button", { name: "排除非ETC" })).toBeEnabled();
    await user.click(within(page).getByRole("button", { name: "排除非ETC" }));
    expect(await within(page).findByText("排除信用卡明细前需要填写处理说明。")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "手工确认" })).toBeEnabled();
    await user.click(within(page).getByRole("button", { name: "手工确认" }));

    expect(await within(page).findByText("手工确认前需要填写处理说明。")).toBeInTheDocument();
    expect(patchItem).not.toHaveBeenCalled();
  });

  test("submitted business batches use local reset deletion instead of the legacy internal revoke action", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const deleteBusinessBatch = vi.spyOn(etcApi, "deleteEtcBusinessBatch");
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("radio", { name: "已提交 1" }));

    await waitFor(() => expect(within(page).getAllByText("1月批次").length).toBeGreaterThanOrEqual(1));
    expect(within(page).queryByRole("button", { name: "提交审批" })).not.toBeInTheDocument();
    expect(within(page).getAllByText("已提交审批").length).toBeGreaterThanOrEqual(1);
    expect(within(page).queryByRole("button", { name: "撤销提交状态" })).not.toBeInTheDocument();

    const row = within(page).getByTestId("etc-batch-row-etc-batch-submitted-01");
    const deleteButton = within(row).getByRole("button", { name: "删除批次 1月批次" });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);
    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("取消发票合并");
    expect(dialog).toHaveTextContent("审批系统中的草稿和已提交记录不会删除");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteBusinessBatch).toHaveBeenCalledWith("etc-batch-submitted-01", {
        expectedVersion: 7,
        reason: "用户在 ETC 页面删除已提交业务批次并释放发票。",
      });
    });
    await waitFor(() => {
      expect(within(page).queryByTestId("etc-batch-row-etc-batch-submitted-01")).not.toBeInTheDocument();
    });
  });

  test("renders batch invoice details with a native table instead of DataGrid", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const invoiceTable = await within(page).findByRole("table", { name: "ETC发票明细" });
    expect(invoiceTable).toBeInTheDocument();
    expect(await within(invoiceTable).findByRole("columnheader", { name: "金额 32.26" })).toBeInTheDocument();
    expect(await within(invoiceTable).findByRole("columnheader", { name: "税额 1.82" })).toBeInTheDocument();
    expect(within(page).queryByRole("grid", { name: "ETC发票明细" })).not.toBeInTheDocument();
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();
    expect(within(page).queryByText("ETC-2026-003")).not.toBeInTheDocument();

    await user.click(within(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-02")).getByRole("button", { name: "查看批次 3月批次" }));

    await waitFor(() => expect(within(page).getAllByText("3月批次").length).toBeGreaterThanOrEqual(1));
    await waitFor(() => {
      expect(within(page).getByText("ETC-2026-003")).toBeInTheDocument();
      expect(within(page).queryByText("ETC-2026-001")).not.toBeInTheDocument();
    });
  });

  test("removes basket wording and old partial-selection actions", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("list", { name: "ETC批次列表" });
    await within(page).findByRole("table", { name: "ETC双侧核对明细" });

    expect(within(page).queryByText("提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("加入提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("移回未提交")).not.toBeInTheDocument();
    expect(within(page).getAllByRole("checkbox", { name: /选择核对行/ })).toHaveLength(4);
  });

  test("creates OA draft through the selected business batch and waits for manual confirmation", async () => {
    const user = userEvent.setup();
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);
    installMockApiFetch();
    const businessBatch = {
      businessBatchId: "etc_business_batch_0001",
      taskId: "etc-recon-task-001",
      status: "imported",
      version: 7,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc_import_batch_0004"],
      submissionBatchId: "",
      externalEtcBatchId: "ETC-2026-03-A",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      invoiceSummary: { count: 2, amount: "32.26" },
      invoiceIds: ["etc-inv-001", "etc-inv-002"],
      importAttempts: [
        {
          attemptId: "attempt-001",
          importBatchId: "etc_import_batch_0004",
          status: "imported",
          imported: 2,
          duplicatesSkipped: 0,
          attachmentsCompleted: 0,
          failed: 0,
          createdAt: "2026-05-19T09:00:00+08:00",
        },
      ],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
      invoiceItems: [
        {
          id: "etc-inv-001",
          invoiceNumber: "ETC-2026-001",
          issueDate: "2026-02-27",
          passageStartDate: "2026-02-27",
          passageEndDate: "2026-02-27",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "12.34",
          taxAmount: "0.73",
          totalAmount: "13.07",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi.spyOn(etcApi, "createEtcBusinessBatchOaDraft").mockResolvedValue({
      ...businessBatch,
      status: "oa_confirmation_pending",
      version: 8,
      submissionBatchId: "etc_batch_0027",
      oaDraftId: "oa_draft_001",
      oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
    } as never);
    const manualOaStatus = vi.spyOn(etcApi, "manualEtcBusinessBatchOaStatus").mockResolvedValue({
      ...businessBatch,
      status: "manually_marked_submitted",
      version: 9,
      submissionBatchId: "etc_batch_0027",
      oaDraftId: "oa_draft_001",
      oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
      oaProcessStatus: "manual_without_oa_row",
      invoiceItems: [],
    } as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getAllByText("3月批次").length).toBeGreaterThanOrEqual(1));
    const submitButton = within(page).getByRole("button", { name: "提交审批" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);

    const dialog = await screen.findByRole("dialog", { name: "创建审批草稿" });
    expect(dialog).toHaveTextContent("为当前任务的 2 张发票创建审批草稿");
    expect(dialog).toHaveTextContent("批次：3月批次");
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc_business_batch_0001", { expectedVersion: 7 }));
    expect(openMock).not.toHaveBeenCalled();

    const resultDialog = await screen.findByRole("dialog", { name: "审批提交确认" });
    expect(resultDialog).toHaveTextContent("审批草稿已创建，等待提交确认。");
    expect(within(resultDialog).getByRole("button", { name: "打开草稿" })).toBeEnabled();
    expect(within(resultDialog).queryByRole("button", { name: "刷新检测" })).not.toBeInTheDocument();
    expect(within(resultDialog).queryByRole("button", { name: "撤销草稿" })).not.toBeInTheDocument();
    await user.click(within(resultDialog).getByRole("button", { name: "已提交" }));
    await waitFor(() => {
      expect(manualOaStatus).toHaveBeenCalledWith("etc_business_batch_0001", {
        decision: "submitted",
        expectedVersion: 8,
        reason: "用户确认审批草稿已提交。",
      });
    });
  });

  test("keeps the create OA draft dialog open when draft creation fails", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const businessBatch = {
      ...businessBatchFixture({
        businessBatchId: "etc-business-draft-fail-001",
        taskId: "etc-recon-draft-fail-001",
        status: "imported",
        version: 7,
        submissionBatchId: "",
        oaDraftId: "",
        oaDraftUrl: "",
        invoiceItems: [],
      }),
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi
      .spyOn(etcApi, "createEtcBusinessBatchOaDraft")
      .mockRejectedValue(new Error("审批草稿创建失败，请检查附件完整性。") as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getByRole("button", { name: "提交审批" })).toBeEnabled());
    await user.click(within(page).getByRole("button", { name: "提交审批" }));

    const dialog = await screen.findByRole("dialog", { name: "创建审批草稿" });
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc-business-draft-fail-001", { expectedVersion: 7 }));
    expect(await within(page).findByText("审批草稿创建失败，请检查附件完整性。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "创建审批草稿" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-business-draft-fail-001")).toBeInTheDocument();
  });

  test("can retry OA draft creation after a transient failure", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const businessBatch = {
      ...businessBatchFixture({
        businessBatchId: "etc-business-draft-retry-001",
        taskId: "etc-recon-draft-retry-001",
        status: "imported",
        version: 7,
        submissionBatchId: "",
        oaDraftId: "",
        oaDraftUrl: "",
        invoiceItems: [],
      }),
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi
      .spyOn(etcApi, "createEtcBusinessBatchOaDraft")
      .mockRejectedValueOnce(new Error("审批草稿创建暂时失败，请重试。") as never)
      .mockResolvedValueOnce({
        ...businessBatch,
        status: "oa_confirmation_pending",
        version: 8,
        submissionBatchId: "etc_batch_retry_001",
        oaDraftId: "oa_draft_retry_001",
        oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_retry_001",
        invoiceItems: [],
      } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getByRole("button", { name: "提交审批" })).toBeEnabled());
    await user.click(within(page).getByRole("button", { name: "提交审批" }));

    const dialog = await screen.findByRole("dialog", { name: "创建审批草稿" });
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledTimes(1));
    expect(createDraft).toHaveBeenLastCalledWith("etc-business-draft-retry-001", { expectedVersion: 7 });
    expect(await within(page).findByText("审批草稿创建暂时失败，请重试。")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "创建审批草稿" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "审批提交确认" })).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledTimes(2));
    expect(createDraft).toHaveBeenLastCalledWith("etc-business-draft-retry-001", { expectedVersion: 7 });
    const resultDialog = await screen.findByRole("dialog", { name: "审批提交确认" });
    expect(resultDialog).toHaveTextContent("审批草稿已创建，等待提交确认。");
    expect(within(page).queryByText("审批草稿创建暂时失败，请重试。")).not.toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-business-draft-retry-001")).toHaveTextContent("待确认提交");
  });

  test("hides the OA draft open action when draft creation returns no URL", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const businessBatch = {
      ...businessBatchFixture({
        status: "imported",
        version: 7,
        submissionBatchId: "",
        oaDraftId: "",
        oaDraftUrl: "",
        invoiceItems: [],
      }),
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi.spyOn(etcApi, "createEtcBusinessBatchOaDraft").mockResolvedValue({
      ...businessBatch,
      status: "oa_confirmation_pending",
      version: 8,
      submissionBatchId: "etc_batch_0027",
      oaDraftId: "oa_draft_without_url_001",
      oaDraftUrl: "",
      invoiceItems: [],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const submitButton = within(page).getByRole("button", { name: "提交审批" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);
    const dialog = await screen.findByRole("dialog", { name: "创建审批草稿" });
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc-business-oa-action-001", { expectedVersion: 7 }));
    const resultDialog = await screen.findByRole("dialog", { name: "审批提交确认" });
    expect(resultDialog).toHaveTextContent("审批草稿已创建，等待提交确认。");
    expect(within(resultDialog).queryByRole("button", { name: "打开草稿" })).not.toBeInTheDocument();
    expect(within(resultDialog).queryByRole("button", { name: "刷新检测" })).not.toBeInTheDocument();
    expect(within(resultDialog).getByRole("button", { name: "已提交" })).toBeEnabled();
    expect(within(resultDialog).getByRole("button", { name: "未提交" })).toBeEnabled();
  });
});
