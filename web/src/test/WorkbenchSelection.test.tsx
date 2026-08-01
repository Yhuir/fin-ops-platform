import { act, screen, within } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt, renderAuthenticatedAppAt } from "./renderHelpers";
import { renderWorkbenchPage } from "./workbenchRenderHelpers";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

const ROUTE_RENDER_TIMEOUT = 5_000;

async function openWorkbenchSettingsPage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("link", { name: "设置" }));
  const settingsPage = await screen.findByTestId("settings-page", undefined, {
    timeout: ROUTE_RENDER_TIMEOUT,
  });
  await within(settingsPage).findByRole("tree", { name: "设置分类" });
  return settingsPage;
}

function expectRelationPreviewSummary(section: HTMLElement) {
  const summary = within(section).getByTestId("relation-preview-summary");
  expect(within(summary).getByText("金额核对")).toBeInTheDocument();
  expect(within(summary).getByTestId("relation-preview-summary-metric-oa")).toBeInTheDocument();
  expect(within(summary).getByTestId("relation-preview-summary-metric-bank")).toBeInTheDocument();
  expect(within(summary).getByTestId("relation-preview-summary-metric-invoice")).toBeInTheDocument();
  expect(within(summary).queryByText(/\d+\s*[项条]/)).not.toBeInTheDocument();
  return summary;
}

function expectRelationPreviewTriPane(section: HTMLElement) {
  expect(within(section).getByTestId("tri-pane")).toBeInTheDocument();
  const oaPane = within(section).getByTestId("pane-oa");
  const bankPane = within(section).getByTestId("pane-bank");
  const invoicePane = within(section).getByTestId("pane-invoice");
  expect(within(oaPane).getByText("OA")).toBeInTheDocument();
  expect(within(oaPane).getByText(/\d+ [项条]/)).toBeInTheDocument();
  expect(within(bankPane).getByText("流水")).toBeInTheDocument();
  expect(within(bankPane).getByText(/\d+ [项条]/)).toBeInTheDocument();
  expect(within(invoicePane).getByText("发票")).toBeInTheDocument();
  expect(within(invoicePane).getByText(/\d+ [项条]/)).toBeInTheDocument();
}

function expectRelationPreviewBlocking(_preview: HTMLElement, submitLabel: string) {
  const currentPreview = screen.getByRole("dialog", { name: /^(确认|撤回)关联$/ });
  expect(screen.queryByRole("dialog", { name: "全局操作进度" })).not.toBeInTheDocument();
  expect(currentPreview).toHaveAttribute("aria-busy", "true");
  expect(within(currentPreview).getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
  expect(within(currentPreview).getByRole("button", { name: "取消" })).toBeDisabled();
  expect(within(currentPreview).getByRole("button", { name: submitLabel })).toBeDisabled();
}

function fetchPath(input: RequestInfo | URL) {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, "http://localhost");
  return `${url.pathname}${url.search}`;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function isWorkbenchInitialRequest(input: RequestInfo | URL) {
  return fetchPath(input).startsWith("/api/workbench?");
}

describe("Workbench row selection and detail drawer", () => {
  test("shows the unified page Audit control to admins", async () => {
    installMockApiFetch();
    renderAuthenticatedAppAt("/", { session: { canAdminAccess: true } });

    expect(await screen.findByRole("heading", { name: "关联台" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Audit 关联台" })).toBeInTheDocument();
  });

  test("clicking an open row toggles multi-selection without opening the detail drawer", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const row = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });

    await user.click(row);

    expect(row).toHaveAttribute("data-row-state", "selected");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(row);

    expect(row).toHaveAttribute("data-row-state", "idle");
  });

  test("stops a relation write and reloads when the active generation changes after preview", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      workbenchReadModelVersions: ["generation-v1", "generation-v2"],
    });
    const defaultFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/confirm-link") {
        return Promise.resolve(jsonResponse({
          error: "workbench_read_model_version_conflict",
          message: "关联台数据版本已更新，请重新确认。",
          read_model_status: "fresh",
          read_model_version: "generation-v2",
        }, 409));
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(screen.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    await waitFor(() => {
      const initialRequests = fetchMock.mock.calls.filter(([input]) => isWorkbenchInitialRequest(input as RequestInfo | URL));
      expect(initialRequests).toHaveLength(2);
      expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
      expect(screen.getAllByText("已选 0")).toHaveLength(2);
    });
    expect(await screen.findByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeInTheDocument();
  });

  test("bank pane time filter supports month selection and clears on second click", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openBankPane = within(unpairedZone).getByTestId("pane-bank");

    expect((await within(unpairedZone).findAllByText("杭州张三广告有限公司")).length).toBeGreaterThan(0);
    expect(within(unpairedZone).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);

    await user.click(within(openBankPane).getByRole("button", { name: "银行流水时间筛选" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水时间筛选面板" });

    await user.click(within(dialog).getByRole("button", { name: "按月" }));
    await user.click(within(dialog).getByRole("button", { name: "4月" }));

    expect(within(unpairedZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
    expect(within(unpairedZone).queryByText("智能工厂设备商")).not.toBeInTheDocument();

    await user.click(within(openBankPane).getByRole("button", { name: "清除银行流水时间筛选 2026年4月" }));

    expect(within(unpairedZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
    expect(within(unpairedZone).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);
  });

  test("clicking detail opens the drawer and highlights rows with the same case id", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const oaRow = await screen.findByRole("row", {
      name: /赵华.*华东设备供应商/,
    });
    const bankRow = screen.getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const detailButton = within(bankRow).getByRole("button", { name: /查看银行流水 .* 详情/ });

    await user.click(detailButton);

    const dialog = await screen.findByRole("dialog", { name: "银行流水详情" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("账号")).toBeInTheDocument();
    expect(within(dialog).getByText("招商银行")).toBeInTheDocument();
    expect(within(dialog).getByText("9123")).toBeInTheDocument();
    expect(within(dialog).queryByText("招商银行 9123")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("资金方向")).not.toBeInTheDocument();
    expect(within(dialog).getByText("支出")).toHaveClass("direction-tag");
    expect(oaRow).toHaveAttribute("data-row-state", "related");
    expect(bankRow).toHaveAttribute("data-row-state", "related");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/rows/bk-p-202603-001?month=all&expected_read_model_version=mock-workbench-generation-1",
      expect.any(Object),
    );
  });

  test("detail reloads the active generation once and retries after a version conflict", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      workbenchReadModelVersions: ["generation-v1", "generation-v2"],
    });
    const defaultFetch = fetchMock.getMockImplementation();
    let detailRequestCount = 0;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input).startsWith("/api/workbench/rows/")) {
        detailRequestCount += 1;
        if (detailRequestCount === 1) {
          return Promise.resolve(jsonResponse({
            error: "workbench_read_model_version_conflict",
            message: "关联台数据版本已更新。",
            read_model_status: "fresh",
            read_model_version: "generation-v2",
          }, 409));
        }
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const bankRow = await screen.findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    await user.click(within(bankRow).getByRole("button", { name: /查看银行流水 .* 详情/ }));

    const dialog = await screen.findByRole("dialog", { name: "银行流水详情" });
    expect(await within(dialog).findByText("账号")).toBeInTheDocument();
    expect(within(dialog).getByText("招商银行")).toBeInTheDocument();
    expect(within(dialog).queryByText("详情加载失败，请稍后重试。")).not.toBeInTheDocument();
    expect(detailRequestCount).toBe(2);
    expect(
      fetchMock.mock.calls.filter(([input]) => isWorkbenchInitialRequest(input as RequestInfo | URL)),
    ).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/rows/bk-p-202603-001?month=all&expected_read_model_version=generation-v2",
      expect.any(Object),
    );
  });

  test("detail shows a real row miss without reloading or retrying", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const defaultFetch = fetchMock.getMockImplementation();
    let detailRequestCount = 0;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input).startsWith("/api/workbench/rows/")) {
        detailRequestCount += 1;
        return Promise.resolve(jsonResponse({ error: "workbench_row_not_found" }, 404));
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const bankRow = await screen.findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    await user.click(within(bankRow).getByRole("button", { name: /查看银行流水 .* 详情/ }));

    const dialog = await screen.findByRole("dialog", { name: "银行流水详情" });
    expect(await within(dialog).findByText("所选关联台记录已不可用，请刷新后重新选择。")).toBeInTheDocument();
    expect(detailRequestCount).toBe(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => isWorkbenchInitialRequest(input as RequestInfo | URL)),
    ).toHaveLength(1);
  });

  test("detail drawer opens before the row detail request resolves", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const defaultFetch = fetchMock.getMockImplementation();
    let detailSignal: AbortSignal | null = null;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input).startsWith("/api/workbench/rows/")) {
        detailSignal = init?.signal ?? null;
        return new Promise<Response>(() => undefined);
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const bankRow = await screen.findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });

    await user.click(within(bankRow).getByRole("button", { name: /查看银行流水 .* 详情/ }));

    const dialog = screen.getByRole("dialog", { name: "银行流水详情" });
    expect(within(dialog).getByText("正在加载详情...")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/rows/bk-p-202603-001?month=all&expected_read_model_version=mock-workbench-generation-1",
      expect.any(Object),
    );
    expect(detailSignal?.aborted).toBe(false);

    await user.click(within(dialog).getByRole("button", { name: "关闭详情抽屉" }));

    expect(detailSignal?.aborted).toBe(true);
  });

  test("OA applicant column keeps the detail icon on the first line and time chip on the second line", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const oaRow = await screen.findByRole("row", {
      name: /赵华.*2026-03-25 11:05/,
    });
    const detailButton = within(oaRow).getByRole("button", { name: "查看OA 赵华 详情" });
    const applicantCell = detailButton.closest("[role='cell']") as HTMLElement;

    expect(detailButton).toHaveClass("row-action-btn-icon");
    expect(within(oaRow).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(applicantCell).getByText("2026-03-25")).toHaveClass("inline-meta-tag-datetime-date");
    expect(within(applicantCell).getByText("11:05")).toHaveClass("inline-meta-tag-datetime-time");

    await user.click(detailButton);

    const dialog = await screen.findByRole("dialog", { name: "OA详情" });
    expect(within(dialog).getByText("OA详情")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/rows/oa-p-202603-001?month=all&expected_read_model_version=mock-workbench-generation-1",
      expect.any(Object),
    );
  });

  test("drawer can be closed after opening from row action", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const invoiceRow = await screen.findByRole("row", {
      name: /91310110MA1F99088Q.*华东设备供应商/,
    });
    await user.click(within(invoiceRow).getByRole("button", { name: /查看发票 .* 详情/ }));

    expect(await screen.findByRole("dialog", { name: "发票详情" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    expect(screen.queryByRole("dialog", { name: "发票详情" })).not.toBeInTheDocument();
  });

  test("drawer supports closing with escape", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const invoiceRow = await screen.findByRole("row", {
      name: /91310110MA1F99088Q.*华东设备供应商/,
    });
    await user.click(within(invoiceRow).getByRole("button", { name: /查看发票 .* 详情/ }));

    expect(await screen.findByRole("dialog", { name: "发票详情" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "发票详情" })).not.toBeInTheDocument();
  });

  test("OA attachment invoice detail shows source expense item and attachment fields", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const invoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });
    await user.click(within(invoiceRow).getByRole("button", { name: /查看发票 .* 详情/ }));

    const dialog = await screen.findByRole("dialog", { name: "发票详情" });

    expect(within(dialog).getByText("来源附件文件名")).toBeInTheDocument();
    expect(within(dialog).getByText("设备尾款附件发票.pdf")).toBeInTheDocument();
    expect(within(dialog).queryByText("来源OA单号")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("oa-o-202603-001")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("来源OA明细行号")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("来源付款项ID")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("oa-o-202603-001:item:1")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("来源附件Key")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("oa-o-202603-001/item-1/invoice.pdf")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("source_expense_item_id")).not.toBeInTheDocument();
  });

  test("unpaired zone header confirm link opens preview before submit", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    expect(within(dialog).getByRole("heading", { name: "确认关联" })).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "操作前" })).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "操作后" })).toBeInTheDocument();
    const before = within(dialog).getByTestId("relation-preview-before");
    const after = within(dialog).getByTestId("relation-preview-after");
    expect(before).toHaveClass("relation-preview-section-before");
    expect(after).toHaveClass("relation-preview-section-after");
    expectRelationPreviewSummary(before);
    expectRelationPreviewSummary(after);
    expectRelationPreviewTriPane(before);
    expectRelationPreviewTriPane(after);
    const beforeGroups = within(before).getAllByTestId(/^candidate-group-/);
    expect(beforeGroups).toHaveLength(3);
    expect(within(before).getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toHaveClass(
      "record-card-sheet-row",
    );
    expect(within(before).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toHaveClass(
      "record-card-sheet-row",
    );
    expect(within(before).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveClass(
      "record-card-sheet-row",
    );
    const afterGroups = within(after).getAllByTestId(/^candidate-group-/);
    expect(afterGroups).toHaveLength(1);
    expect(afterGroups[0]).toHaveClass("candidate-group-row-sheet");
    expect(within(afterGroups[0]).getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toHaveClass("record-card-sheet-row");
    expect(within(afterGroups[0]).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toHaveClass("record-card-sheet-row");
    expect(within(afterGroups[0]).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveClass("record-card-sheet-row");
    expect(within(dialog).queryByText("杭州张三广告有限公司")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("ETC过路费")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.anything(),
    );

    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/confirm-link",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
          }),
        }),
      );
    });
  });

  test("confirm preview is busy on the next render and duplicate clicks send one POST", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const defaultFetch = fetchMock.getMockImplementation();
    let releasePreview!: () => void;
    const previewGate = new Promise<void>((resolve) => {
      releasePreview = resolve;
    });
    let previewCalls = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/confirm-link/preview") {
        previewCalls += 1;
        await previewGate;
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    await user.click(within(unpairedZone).getByRole("row", { name: /陈涛.*智能工厂设备商/ }));
    await user.click(within(unpairedZone).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    const confirmButton = within(unpairedZone).getByRole("button", { name: "确认关联" });
    await user.click(confirmButton);

    const busyButton = within(unpairedZone).getByRole("button", { name: "正在准备确认预览" });
    expect(busyButton).toBeDisabled();
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    await user.click(busyButton);
    expect(previewCalls).toBe(1);

    releasePreview();
    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
  });

  test("withdraw preview is busy on the next render and duplicate clicks send one POST", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const defaultFetch = fetchMock.getMockImplementation();
    let releasePreview!: () => void;
    const previewGate = new Promise<void>((resolve) => {
      releasePreview = resolve;
    });
    let previewCalls = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/withdraw-link/preview") {
        previewCalls += 1;
        await previewGate;
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    await user.click(within(pairedZone).getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    }));
    const withdrawButton = within(pairedZone).getByRole("button", { name: "撤回关联" });
    await user.click(withdrawButton);

    const busyButton = within(pairedZone).getByRole("button", { name: "正在准备撤回预览" });
    expect(busyButton).toBeDisabled();
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    await user.click(busyButton);
    expect(previewCalls).toBe(1);

    releasePreview();
    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
  });

  test("drops a confirm preview response after the selected rows change", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const defaultFetch = fetchMock.getMockImplementation();
    let releasePreview!: () => void;
    const previewGate = new Promise<void>((resolve) => {
      releasePreview = resolve;
    });
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/confirm-link/preview") {
        await previewGate;
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    await user.click(within(unpairedZone).getByRole("row", { name: /陈涛.*智能工厂设备商/ }));
    await user.click(within(unpairedZone).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(within(unpairedZone).getByRole("button", { name: "确认关联" }));
    await user.click(within(unpairedZone).getByRole("button", { name: "清空选择" }));

    releasePreview();
    await waitFor(() => {
      expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeDisabled();
    });
    expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
  });

  test("preview failure restores the entry without exposing backend English", async () => {
    const user = userEvent.setup();
    const defaultFetch = installMockApiFetch();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/confirm-link/preview") {
        return jsonResponse({
          error: "internal_server_error",
          message: "INTERNAL ENGLISH SENTINEL: database details",
          requestId: "req-preview-safe",
        }, 500);
      }
      return defaultFetch(input, init);
    }));
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    await user.click(await within(unpairedZone).findByRole("row", { name: /陈涛.*智能工厂设备商/ }));
    await user.click(await within(unpairedZone).findByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(within(unpairedZone).getByRole("button", { name: "确认关联" }));

    const errorDialog = await screen.findByRole("dialog", { name: "操作状态弹窗" });
    expect(within(errorDialog).getByText("操作失败")).toBeInTheDocument();
    expect(
      within(errorDialog).getByText("关联台服务暂时不可用，请稍后重试。 · requestId req-preview-safe"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/INTERNAL ENGLISH SENTINEL/)).not.toBeInTheDocument();
    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeEnabled();
  });

  test("unknown JavaScript preview errors use the generic Chinese message", async () => {
    const user = userEvent.setup();
    const defaultFetch = installMockApiFetch();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchPath(input) === "/api/workbench/actions/confirm-link/preview") {
        throw new Error("PARSER EXCEPTION SENTINEL");
      }
      return defaultFetch(input, init);
    }));
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    await user.click(await within(unpairedZone).findByRole("row", { name: /陈涛.*智能工厂设备商/ }));
    await user.click(await within(unpairedZone).findByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(within(unpairedZone).getByRole("button", { name: "确认关联" }));

    const errorDialog = await screen.findByRole("dialog", { name: "操作状态弹窗" });
    expect(within(errorDialog).getByText("操作失败")).toBeInTheDocument();
    expect(within(errorDialog).getByText("操作失败，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByText(/PARSER EXCEPTION SENTINEL/)).not.toBeInTheDocument();
    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeEnabled();
  });

  test("amount mismatch preview requires note before confirm submit", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", { name: /林晨.*尾差设备商/ }));
    await user.click(await screen.findByRole("row", { name: /2026-03-29.*尾差设备商/ }));
    await user.click(await screen.findByRole("row", { name: /91330108MA27B4011E.*杭州溯源科技有限公司/ }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    expect(within(dialog).getByText("金额不一致，请填写备注。")).toBeInTheDocument();
    const after = within(dialog).getByTestId("relation-preview-after");
    const summary = expectRelationPreviewSummary(after);
    const invoiceMetric = within(summary).getByTestId("relation-preview-summary-metric-invoice");
    expect(
      invoiceMetric.classList.contains("mismatch")
        || invoiceMetric.classList.contains("relation-preview-summary-metric-mismatch"),
    ).toBe(true);
    const deltaBlocks = within(dialog).getAllByTestId("relation-preview-delta");
    expect(deltaBlocks.length).toBeGreaterThan(0);
    deltaBlocks.forEach((deltaBlock) => {
      expect(deltaBlock).toHaveTextContent("差额");
      expect(deltaBlock).not.toHaveTextContent(/OA\s*-|流水\s*-|发票\s*-/);
    });
    expect(within(dialog).getByRole("button", { name: "确认关联" })).toBeDisabled();

    await user.type(within(dialog).getByRole("textbox", { name: "差额说明" }), "发票税额尾差，财务已复核");
    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/confirm-link",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"note\":\"发票税额尾差，财务已复核\""),
        }),
      );
    });
  });

  test("confirm preview respects matched backend status for mixed bank directions", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      workbenchConfirmPreview: {
        operation: "confirm_link",
        operation_type: "confirm_link",
        can_submit: true,
        requires_note: false,
        message: "",
        before: {
          groups: [
            {
              group_id: "preview:mixed-bank-before",
              group_type: "selection",
              zone: "unpaired",
              status: "unpaired",
              match_confidence: "medium",
              reason: "manual_preview",
              oa_rows: [
                {
                  id: "oa-mixed-001",
                  type: "oa",
                  applicant: "刘际涛",
                  project_name: "云南溯源科技",
                  apply_type: "支付申请",
                  amount: "300000.00",
                  application_date: "2026-03-11 07:25:52",
                },
              ],
              bank_rows: [
                {
                  id: "bk-mixed-out-001",
                  type: "bank",
                  trade_time: "2026-03-04 15:24:58",
                  counterparty_name: "贾小花",
                  debit_amount: "300000.00",
                  credit_amount: null,
                },
                {
                  id: "bk-mixed-in-001",
                  type: "bank",
                  trade_time: "2026-02-04 17:07:45",
                  counterparty_name: "贾小花",
                  debit_amount: null,
                  credit_amount: "100000.00",
                },
                {
                  id: "bk-mixed-in-002",
                  type: "bank",
                  trade_time: "2026-02-04 13:20:48",
                  counterparty_name: "贾小花",
                  debit_amount: null,
                  credit_amount: "200000.00",
                },
              ],
              invoice_rows: [],
            },
          ],
        },
        after: {
          groups: [
            {
              group_id: "case:preview:mixed-bank-after",
              group_type: "relation",
              zone: "paired",
              status: "paired",
              match_confidence: "medium",
              reason: "manual_preview",
              oa_rows: [
                {
                  id: "oa-mixed-001",
                  type: "oa",
                  applicant: "刘际涛",
                  project_name: "云南溯源科技",
                  apply_type: "支付申请",
                  amount: "300000.00",
                  application_date: "2026-03-11 07:25:52",
                },
              ],
              bank_rows: [
                {
                  id: "bk-mixed-out-001",
                  type: "bank",
                  trade_time: "2026-03-04 15:24:58",
                  counterparty_name: "贾小花",
                  debit_amount: "300000.00",
                  credit_amount: null,
                },
                {
                  id: "bk-mixed-in-001",
                  type: "bank",
                  trade_time: "2026-02-04 17:07:45",
                  counterparty_name: "贾小花",
                  debit_amount: null,
                  credit_amount: "100000.00",
                },
                {
                  id: "bk-mixed-in-002",
                  type: "bank",
                  trade_time: "2026-02-04 13:20:48",
                  counterparty_name: "贾小花",
                  debit_amount: null,
                  credit_amount: "200000.00",
                },
              ],
              invoice_rows: [],
            },
          ],
        },
        amount_summary: {
          before: { oa_total: "300000.00", bank_total: "600000.00", invoice_total: null },
          after: { oa_total: "300000.00", bank_total: "600000.00", invoice_total: null },
          status: "matched",
          direction: "payment",
          mismatch_fields: [],
        },
      },
    });
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", { name: /陈涛.*智能工厂设备商/ }));
    await user.click(await screen.findByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    const after = within(dialog).getByTestId("relation-preview-after");
    expect(within(after).getByText("金额一致")).toBeInTheDocument();
    expect(within(after).queryByTestId("relation-preview-delta")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "确认关联" })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: "确认关联" }).closest(".relation-preview-actions")).toBeInTheDocument();
  });

  test("confirm preview for an already linked selection submits withdraw instead of confirm", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      workbenchConfirmPreview: {
        operation: "withdraw_link",
        operation_type: "withdraw_relation",
        preview_id: "withdraw_relation:CASE-202603-101",
        can_submit: true,
        requires_note: false,
        message: "所选记录已确认关联，可在此撤回这组配对关系。",
        active_relation: {
          case_id: "CASE-202603-101",
          row_ids: ["bk-o-202603-001", "iv-o-202603-001"],
        },
        submit_expected_versions: {
          "CASE-202603-101": 1,
        },
        before: {
          groups: [
            {
              group_id: "case:CASE-202603-101",
              group_type: "relation",
              zone: "paired",
              status: "paired",
              can_withdraw: true,
              oa_rows: [],
              bank_rows: [
                {
                  id: "bk-o-202603-001",
                  type: "bank",
                  trade_time: "2026-03-28 10:18",
                  debit_amount: "58,000.00",
                  counterparty_name: "智能工厂设备商",
                  invoice_relation: { code: "manual_confirmed", label: "完全关联", tone: "success" },
                },
              ],
              invoice_rows: [
                {
                  id: "iv-o-202603-001",
                  type: "invoice",
                  seller_name: "智能工厂设备商",
                  buyer_name: "杭州溯源科技有限公司",
                  issue_date: "2026-03-28",
                  total_with_tax: "65,540.00",
                  invoice_bank_relation: { code: "manual_confirmed", label: "完全关联", tone: "success" },
                },
              ],
            },
          ],
        },
        after: {
          groups: [],
        },
        amount_summary: {
          before: { oa_total: "-", bank_total: "58000.00", invoice_total: "65540.00" },
          after: { oa_total: "-", bank_total: "-", invoice_total: "-" },
          status: "matched",
          direction: "payment",
          mismatch_fields: [],
        },
      },
    });
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    await user.click(await screen.findByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    expect(within(dialog).getByRole("heading", { name: "撤回关联" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "确认关联" })).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认撤回" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/withdraw-link",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"preview_id\":\"withdraw_relation:CASE-202603-101\""),
        }),
      );
    });
    expect(
      fetchMock.mock.calls.filter(([input]) => fetchPath(input).startsWith("/api/workbench/actions/confirm-link")).length,
    ).toBe(1);
  });

  test("one unpaired singleton never pulls legacy case siblings into the selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });

    await user.click(openOaRow);

    expect(screen.getByText("已选 1")).toBeInTheDocument();
    expect(screen.queryByText(/带入/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link/preview",
      expect.anything(),
    );
  });

  test("unpaired confirmation uses only explicitly selected bank and invoice rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    const after = within(dialog).getByTestId("relation-preview-after");
    const afterSummary = expectRelationPreviewSummary(after);
    const sourceOaMetric = within(afterSummary).getByTestId("relation-preview-summary-metric-oa");
    expect(within(sourceOaMetric).getByText("-")).toBeInTheDocument();
    expect(within(after).getByTestId("pane-oa")).toHaveTextContent("0 项");
    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/confirm-link",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["bk-o-202603-001", "iv-o-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
          }),
        }),
      );
    });
  });

  test("unpaired selection summary and confirm preview keep explicitly selected rows hidden by pane time filters", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openBankPane = within(unpairedZone).getByTestId("pane-bank");
    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /王青.*维保续费项目/,
    });
    const openBankRow = within(unpairedZone).getByRole("row", {
      name: /2026-04-20.*杭州张三广告有限公司/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);

    expect(within(unpairedZone).getByText("OA 1 / 6,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).getByText("流水 1 / 6,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).queryByText(/发票 1/)).not.toBeInTheDocument();

    await user.click(within(openBankPane).getByRole("button", { name: "银行流水时间筛选" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水时间筛选面板" });
    await user.click(within(dialog).getByRole("button", { name: "按月" }));
    await user.click(within(dialog).getByRole("button", { name: "3月" }));

    expect(within(unpairedZone).queryByRole("row", { name: /王青.*维保续费项目/ })).not.toBeInTheDocument();
    expect(within(unpairedZone).queryByRole("row", { name: /2026-04-20.*杭州张三广告有限公司/ })).not.toBeInTheDocument();
    expect(within(unpairedZone).getByText("OA 1 / 6,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).getByText("流水 1 / 6,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).queryByText(/发票 1/)).not.toBeInTheDocument();

    await user.click(within(unpairedZone).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202604-001", "bk-o-202604-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );
  });

  test("unpaired selection summary never includes unselected attachment invoice context", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = within(unpairedZone).getByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);

    expect(within(unpairedZone).getByText("已选 2")).toBeInTheDocument();
    expect(within(unpairedZone).queryByText(/带入/)).not.toBeInTheDocument();
    expect(within(unpairedZone).getByText("OA 1 / 58,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).getByText("流水 1 / 58,000.00")).toBeInTheDocument();
    expect(within(unpairedZone).queryByText(/发票 1/)).not.toBeInTheDocument();

    await user.click(within(unpairedZone).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );
  });

  test("paired selection stays withdrawable after pane filters hide the explicitly selected row", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const pairedBankPane = within(pairedZone).getByTestId("pane-bank");
    const pairedBankRow = await within(pairedZone).findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeEnabled();
    expect(within(pairedZone).getByText("流水 1 / 128,000.00")).toBeInTheDocument();

    await user.click(within(pairedBankPane).getByRole("button", { name: "银行流水时间筛选" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水时间筛选面板" });
    await user.click(within(dialog).getByRole("button", { name: "按月" }));
    await user.click(within(dialog).getByRole("button", { name: "4月" }));

    expect(within(pairedZone).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(pairedZone).getByText("流水 1 / 128,000.00")).toBeInTheDocument();
    expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeEnabled();

    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/withdraw-link/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-p-202603-001", "bk-p-202603-001", "iv-p-202603-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );
  });

  test("unpaired zone exception action accepts invoice selections and uses the unified exception modal", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await within(unpairedZone).findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await within(unpairedZone).findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    const exceptionButton = within(unpairedZone)
      .getAllByRole("button", { name: "异常处理" })
      .find((button) => button.classList.contains("zone-selection-btn"));
    expect(exceptionButton).toBeDefined();
    await user.click(exceptionButton!);

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(screen.queryByText("OA与银行流水异常处理暂不支持发票，请先取消发票选择。")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "OA流水异常处理弹窗" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );

    await user.click(within(dialog).getByRole("radio", { name: /追进项发票/ }));
    await user.type(within(dialog).getByLabelText("备注"), "已联系供应商补票");
    await user.click(within(dialog).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/exception/apply",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
            scenario_code: "expense_oa_bank_invoice_equal",
            action_code: "wait_input_invoice",
            payload: {
              note: "已联系供应商补票",
            },
          }),
        }),
      );
    });

    const calledPaths = fetchMock.mock.calls.map(([input]) => fetchPath(input));
    const applyIndex = calledPaths.findIndex((path) => path === "/api/workbench/exception/apply");
    expect(applyIndex).toBeGreaterThanOrEqual(0);
    expect(calledPaths.slice(applyIndex + 1)).toContain("/api/workbench?month=all");
  });

  test("unpaired zone exception action accepts OA 2035 attachment payment receipt selections from the backend group", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ includeOaAttachmentPaymentReceipt: true });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const oa2035Summary = await within(unpairedZone).findByText("多个项目 · 2");
    const oa2035Row = oa2035Summary.closest('[role="row"]');
    expect(oa2035Row).not.toBeNull();
    const paymentReceiptRow = await within(unpairedZone).findByRole("row", {
      name: /微信支付.*胡瑢.*200(?:\.00)?/,
    });

    await user.click(oa2035Row!);
    await user.click(paymentReceiptRow);

    expect(oa2035Row!).toHaveAttribute("data-row-state", "selected");
    expect(paymentReceiptRow).toHaveAttribute("data-row-state", "selected");

    const exceptionButton = within(unpairedZone)
      .getAllByRole("button", { name: "异常处理" })
      .find((button) => button.classList.contains("zone-selection-btn"));
    expect(exceptionButton).toBeDefined();
    await user.click(exceptionButton!);

    expect(await screen.findByRole("dialog", { name: "统一异常处理" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-exp-2035", "pay-oa-2035-fuel-200"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );
  });

  test("workbench action applies backend projection and never calls the operation barrier", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 20, workbenchBackgroundLoadDelayMs: 180 });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const pairedZone = await screen.findByTestId("zone-paired");
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));
    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    expectRelationPreviewBlocking(preview, "确认关联");
    expect(within(preview).getByText("正在确认关联...")).toBeInTheDocument();
    expect(unpairedZone).toHaveTextContent("2026-03-28");
    expect(unpairedZone).toHaveTextContent("智能工厂设备商");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
    }, { timeout: 5_000 });
    expect(
      within(unpairedZone).queryByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(pairedZone).getByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => fetchPath(input).startsWith("/api/operation-barrier/status"))).toBe(false);
  });

  test("workbench action ignores legacy global freshness targets and does not call the barrier", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      actionDelayMs: 20,
      workbenchBackgroundLoadDelayMs: 180,
      transformWorkbenchConfirmActionResponse: (body) => ({
        ...body,
        affected_months: ["all"],
        affected_scope_keys: ["all"],
        freshness_targets: [
          { read_model_key: "workbench_relation", scope_key: "all" },
        ],
      }),
    });
    renderWorkbenchPage();

    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));
    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    expectRelationPreviewBlocking(preview, "确认关联");
    expect(within(preview).getByText("正在确认关联...")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
    }, { timeout: 2_000 });

    const barrierCalls = fetchMock.mock.calls.filter(([input]) => fetchPath(input).startsWith("/api/operation-barrier/status"));
    const globalRelationBarrierCalls = barrierCalls.filter(([, init]) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      return (body.targets ?? []).some((target: { read_model_key?: string; scope_key?: string }) => (
        target.read_model_key === "workbench_relation" && target.scope_key === "all"
      ));
    });
    expect(globalRelationBarrierCalls).toHaveLength(0);
    expect(screen.queryByText(/操作同步等待超时/)).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "操作失败" })).not.toBeInTheDocument();
  });

  test("confirm link does not expose row movement while the submit is still in progress", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ actionDelayMs: 20, workbenchBackgroundLoadDelayMs: 180 });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));
    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    expectRelationPreviewBlocking(preview, "确认关联");
    expect(unpairedZone).toHaveTextContent("2026-03-28");
    expect(unpairedZone).toHaveTextContent("智能工厂设备商");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
    });
  });

  test("refreshing response cannot overwrite the committed confirm projection", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 20 });
    const defaultFetch = fetchMock.getMockImplementation();
    let initialSnapshot: Record<string, unknown> | null = null;
    let confirmCommitted = false;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = fetchPath(input);
      if (confirmCommitted && isWorkbenchInitialRequest(input) && initialSnapshot) {
        const refreshingSnapshot = JSON.parse(JSON.stringify(initialSnapshot)) as {
          paired: Record<string, unknown>;
          unpaired: Record<string, unknown>;
          read_model_status: string;
        };
        refreshingSnapshot.read_model_status = "refreshing";
        refreshingSnapshot.paired.read_model_status = "refreshing";
        refreshingSnapshot.unpaired.read_model_status = "refreshing";
        return jsonResponse(refreshingSnapshot);
      }
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      const response = await defaultFetch(input, init);
      if (isWorkbenchInitialRequest(input) && !initialSnapshot) {
        initialSnapshot = await response.json() as Record<string, unknown>;
        return jsonResponse(initialSnapshot);
      }
      if (path === "/api/workbench/actions/confirm-link") {
        confirmCommitted = true;
      }
      return response;
    });
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    }));
    await user.click(screen.getByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));
    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    await waitFor(() => {
      const initialRequests = fetchMock.mock.calls.filter(([input]) => (
        isWorkbenchInitialRequest(input as RequestInfo | URL)
      ));
      expect(initialRequests).toHaveLength(2);
    });
    const pairedZone = screen.getByTestId("zone-paired");
    const unpairedZone = screen.getByTestId("zone-unpaired");
    expect(within(pairedZone).getByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    })).toBeInTheDocument();
    expect(within(unpairedZone).queryByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    })).not.toBeInTheDocument();
    expect(screen.getByText(
      "关联台正在刷新，当前显示上一版稳定数据；刷新完成前写操作已禁用。",
    )).toBeInTheDocument();
  });

  test("disables relation writes while the workbench generation is refreshing", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      actionDelayMs: 20,
      workbenchReadModelStatus: "refreshing",
    });
    renderWorkbenchPage();

    await screen.findByTestId("zone-unpaired");
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openBankRow);
    await user.click(openInvoiceRow);
    expect(screen.getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(screen.getByText("关联台正在刷新，当前显示上一版稳定数据；刷新完成前写操作已禁用。")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
  });

  test("initial workbench rows render before slow ignored and settings requests finish", async () => {
    installMockApiFetch({
      workbenchPrimaryDelayMs: 20,
      workbenchIgnoredDelayMs: 3000,
      workbenchSettingsDelayMs: 3000,
    });
    renderWorkbenchPage();

    expect(
      await screen.findByRole("row", {
        name: /陈涛.*智能工厂设备商/,
      }, { timeout: 2000 }),
    ).toBeInTheDocument();
  });

  test("withdraw link finishes only after the fresh refetch restores every row as an unpaired singleton", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 20, workbenchLoadDelayMs: 160 });
    const defaultFetch = fetchMock.getMockImplementation();
    let withdrawCommitted = false;
    let refreshStatusCallsAfterWrite = 0;
    let initialPageCallsAfterWrite = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!defaultFetch) {
        throw new Error("Mock API fetch is not installed.");
      }
      const path = fetchPath(input);
      if (path === "/api/workbench/actions/withdraw-link") {
        const response = await defaultFetch(input, init);
        withdrawCommitted = true;
        return response;
      }
      if (withdrawCommitted && path.startsWith("/api/workbench/refresh-status")) {
        refreshStatusCallsAfterWrite += 1;
        return jsonResponse({
          scope_key: "all",
          read_model_status: refreshStatusCallsAfterWrite >= 3 ? "fresh" : "refreshing",
          dirty_scopes: [],
          retryable: false,
        });
      }
      if (withdrawCommitted && isWorkbenchInitialRequest(input)) {
        initialPageCallsAfterWrite += 1;
        const response = await defaultFetch(input, init) as Response;
        const payload = await response.json() as Record<string, unknown>;
        const readModelStatus = refreshStatusCallsAfterWrite >= 3 ? "fresh" : "refreshing";
        return jsonResponse({
          ...payload,
          read_model_status: readModelStatus,
          paired: {
            ...(payload.paired as Record<string, unknown>),
            read_model_status: readModelStatus,
          },
          unpaired: {
            ...(payload.unpaired as Record<string, unknown>),
            read_model_status: readModelStatus,
          },
        });
      }
      return defaultFetch(input, init);
    });
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const unpairedZone = await screen.findByTestId("zone-unpaired");

    const pairedBankRow = await screen.findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const pairedInvoiceRow = await screen.findByRole("row", {
      name: /91310000MA1K8A001X.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await user.click(pairedInvoiceRow);
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    expect(within(preview).getByRole("heading", { name: "撤回关联" })).toBeInTheDocument();
    expect(within(preview).getByRole("heading", { name: "操作前" })).toBeInTheDocument();
    expect(within(preview).getByRole("heading", { name: "操作后" })).toBeInTheDocument();
    const before = within(preview).getByTestId("relation-preview-before");
    const after = within(preview).getByTestId("relation-preview-after");
    expectRelationPreviewSummary(before);
    expectRelationPreviewSummary(after);
    expectRelationPreviewTriPane(before);
    expectRelationPreviewTriPane(after);
    expect(within(before).getAllByTestId(/^candidate-group-/)).toHaveLength(1);
    const afterGroups = within(after).getAllByTestId(/^candidate-group-/);
    expect(afterGroups).toHaveLength(3);
    const oaOnlyGroup = afterGroups.find((group) => within(group).queryByRole("row", { name: /赵华.*华东设备供应商/ }));
    expect(oaOnlyGroup).toBeDefined();
    expect(within(oaOnlyGroup!).queryByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(oaOnlyGroup!).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ })).not.toBeInTheDocument();
    const bankOnlyGroup = afterGroups.find((group) => within(group).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ }));
    expect(bankOnlyGroup).toBeDefined();
    expect(within(bankOnlyGroup!).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    const invoiceOnlyGroup = afterGroups.find((group) => within(group).queryByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ }));
    expect(invoiceOnlyGroup).toBeDefined();
    expect(within(invoiceOnlyGroup!).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "确认撤回" }));

    expectRelationPreviewBlocking(preview, "确认撤回");
    expect(within(preview).getByText("正在撤回关联...")).toBeInTheDocument();
    expect(pairedZone).toHaveTextContent(/2026-03-25\s*14:22/);
    expect(pairedZone).toHaveTextContent("华东设备供应商");
    expect(unpairedZone).not.toHaveTextContent(/2026-03-25\s*14:22/);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /^(确认|撤回)关联$/ })).not.toBeInTheDocument();
    });
    expect(
      within(pairedZone).queryByRole("row", {
        name: /2026-03-25 14:22.*华东设备供应商/,
      }),
    ).not.toBeInTheDocument();
    const restoredOaGroup = await within(unpairedZone).findByTestId("candidate-group-unpaired-row:oa-p-202603-001");
    const bankOnlyUnpairedGroup = within(unpairedZone).getByTestId("candidate-group-unpaired-row:bk-p-202603-001");
    const invoiceOnlyUnpairedGroup = within(unpairedZone).getByTestId("candidate-group-unpaired-row:iv-p-202603-001");
    expect(within(restoredOaGroup).queryByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(restoredOaGroup).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(bankOnlyUnpairedGroup).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(bankOnlyUnpairedGroup).queryByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(invoiceOnlyUnpairedGroup).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(refreshStatusCallsAfterWrite).toBe(3);
    expect(initialPageCallsAfterWrite).toBe(2);
  });

  test("unpaired zone never exposes a withdraw action because it has no formal relation", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    expect(within(unpairedZone).queryByRole("button", { name: "撤回关联" })).not.toBeInTheDocument();

    await user.click(await within(unpairedZone).findByRole("row", { name: /孙敏.*华东设备供应商/ }));

    expect(within(unpairedZone).queryByRole("button", { name: "撤回关联" })).not.toBeInTheDocument();
  });

  test("zone search scans every pane while keeping singleton unpaired groups isolated", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const zoneSearch = within(unpairedZone).getByRole("searchbox", { name: "搜索未配对区域" });

    expect(within(unpairedZone).getAllByRole("searchbox")).toHaveLength(1);
    await user.type(zoneSearch, "智能工厂");

    expect(within(unpairedZone).getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toBeInTheDocument();
    expect(within(unpairedZone).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeInTheDocument();
    expect(within(unpairedZone).getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toBeInTheDocument();
    expect(within(unpairedZone).getByTestId("candidate-group-unpaired-row:bk-o-202603-001")).toBeInTheDocument();
    expect(within(unpairedZone).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeInTheDocument();
    expect(within(unpairedZone).getByTestId("candidate-group-unpaired-row:iv-o-202603-001")).toBeInTheDocument();
    expect(within(unpairedZone).queryByText("杭州张三广告有限公司")).not.toBeInTheDocument();

    await user.click(within(unpairedZone).getByRole("button", { name: "清空搜索" }));

    expect(within(unpairedZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);

    await user.type(zoneSearch, "91330108");

    expect(within(unpairedZone).queryByRole("row", { name: /陈涛.*智能工厂设备商/ })).not.toBeInTheDocument();
    expect(within(unpairedZone).queryByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).not.toBeInTheDocument();
    expect(within(unpairedZone).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeInTheDocument();
    expect(zoneSearch).toHaveValue("91330108");
    expect(within(unpairedZone).getByRole("button", { name: "清空搜索" })).toBeInTheDocument();
  });

  test("unpaired zone header actions use the selected group context", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");

    const clearButton = within(unpairedZone).getByRole("button", { name: "清空选择" });
    const confirmButton = within(unpairedZone).getByRole("button", { name: "确认关联" });
    const exceptionButton = within(unpairedZone).getByRole("button", { name: "异常处理" });
    expect(within(unpairedZone).queryByRole("button", { name: "撤回关联" })).not.toBeInTheDocument();

    expect(clearButton).toBeEnabled();
    expect(confirmButton).toBeDisabled();
    expect(exceptionButton).toBeDisabled();

    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });

    await user.click(openOaRow);

    expect(confirmButton).toBeDisabled();
    expect(exceptionButton).toBeEnabled();

    const openBankRow = await within(unpairedZone).findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openBankRow);

    expect(confirmButton).toBeEnabled();
    expect(exceptionButton).toBeEnabled();
  });

  test("workbench stale refresh does not globally disable selected group actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      appHealth: {
        status: "ok",
        generated_at: "2026-05-06T00:00:00+08:00",
        session: { status: "authenticated" },
        oa_sync: {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
        },
        workbench_matching: {
          status: "stale",
          dirty_scopes: ["2026-04"],
          stale_scopes: ["2026-04"],
          rebuilding_scopes: ["2026-04"],
        },
        background_jobs: {
          active: 0,
          queued: 0,
          running: 0,
          attention: 0,
        },
        dependencies: {},
      },
    });
    renderAppAt("/");

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    expect(await screen.findByRole("button", { name: /关联台待刷新/ })).toBeInTheDocument();
    await user.click(await within(unpairedZone).findByRole("row", { name: /陈涛.*智能工厂设备商/ }));

    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(within(unpairedZone).getByRole("button", { name: "异常处理" })).toBeEnabled();
    await user.click(within(unpairedZone).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }));
    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeEnabled();
    expect(within(unpairedZone).queryByRole("button", { name: "撤回关联" })).not.toBeInTheDocument();
  });

  test("OA dirty sync still disables selected group actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      workbenchOaSyncStatuses: [
        {
          status: "idle",
          message: "OA 有待处理变更",
          dirty_scopes: ["2026-04"],
          changed_scopes: [],
          last_synced_at: "2026-05-06T09:59:00+08:00",
          version: 1,
        },
      ],
      appHealth: {
        status: "ok",
        generated_at: "2026-05-06T00:00:00+08:00",
        session: { status: "authenticated" },
        oa_sync: {
          status: "synced",
          message: "OA 有待处理变更",
          dirty_scopes: ["2026-04"],
        },
        workbench_matching: {
          status: "ready",
          dirty_scopes: [],
          stale_scopes: [],
          rebuilding_scopes: [],
        },
        background_jobs: {
          active: 0,
          queued: 0,
          running: 0,
          attention: 0,
        },
        dependencies: {},
      },
    });
    renderAppAt("/");

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    expect(await screen.findByRole("button", { name: /关联台待刷新/ })).toBeInTheDocument();
    await user.click(await within(unpairedZone).findByRole("row", { name: /陈涛.*智能工厂设备商/ }));

    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(within(unpairedZone).getByRole("button", { name: "异常处理" })).toBeDisabled();
    expect(within(unpairedZone).getByRole("status", {
      name: "OA 正在同步，完成后将自动恢复关联操作。",
    })).toBeInTheDocument();
    expect(within(unpairedZone).queryByRole("button", { name: "撤回关联" })).not.toBeInTheDocument();
  });

  test("restores selected Workbench actions from the local OA status without waiting for stale App Health", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      appHealth: {
        status: "ok",
        generated_at: "2026-05-06T00:00:00+08:00",
        session: { status: "authenticated" },
        oa_sync: {
          status: "synced",
          message: "OA 有待处理变更",
          dirty_scopes: ["2026-03"],
        },
        workbench_matching: {
          status: "ready",
          dirty_scopes: [],
          stale_scopes: [],
          rebuilding_scopes: [],
        },
        background_jobs: {
          active: 0,
          queued: 0,
          running: 0,
          attention: 0,
        },
        dependencies: {},
      },
      workbenchOaSyncStatuses: [
        {
          status: "idle",
          message: "OA 有待处理变更",
          dirty_scopes: ["2026-03"],
          changed_scopes: [],
          last_synced_at: "2026-05-06T09:59:00+08:00",
          version: 1,
        },
        {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
          changed_scopes: ["all"],
          last_synced_at: "2026-05-06T10:00:00+08:00",
          version: 2,
        },
      ],
    });
    renderAppAt("/");

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const oaRow = await within(unpairedZone).findByRole("row", { name: /陈涛.*智能工厂设备商/ });
    const bankRow = await within(unpairedZone).findByRole("row", { name: /2026-03-28.*智能工厂设备商/ });
    await user.click(oaRow);
    await user.click(bankRow);

    const confirmButton = within(unpairedZone).getByRole("button", { name: "确认关联" });
    expect(confirmButton).toBeDisabled();
    expect(within(unpairedZone).getByRole("status", {
      name: "OA 正在同步，完成后将自动恢复关联操作。",
    })).toBeInTheDocument();

    await waitFor(() => {
      expect(confirmButton).toBeEnabled();
      expect(within(unpairedZone).queryByRole("status", {
        name: "OA 正在同步，完成后将自动恢复关联操作。",
      })).not.toBeInTheDocument();
    }, { timeout: 5_000 });

    expect(oaRow).toHaveAttribute("data-row-state", "selected");
    expect(bankRow).toHaveAttribute("data-row-state", "selected");
  });

  test("workbench settings can manage allowed app accounts", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
    });
    renderAuthenticatedAppAt("/", {
      session: {
        accessTier: "admin",
        canAdminAccess: true,
        canMutateData: true,
        user: {
          username: "YNSYLP005",
          nickname: "杨南山",
          displayName: "杨南山",
        },
      },
    });

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsPage).getByRole("heading", { name: "设置分类" })).toBeInTheDocument();
    expect(screen.queryByText("设置项")).not.toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /项目状态/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /银行账户/ })).toBeInTheDocument();
    expect(within(settingsTree).queryByRole("treeitem", { name: /银行明细标签管理/ })).not.toBeInTheDocument();
    expect(within(settingsTree).queryByRole("treeitem", { name: /银行流水标签/ })).not.toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /待找发票筛选/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /OA导入设置/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /访问账户/ })).toBeInTheDocument();
    expect(within(settingsPage).getByRole("heading", { name: "项目状态管理" })).toBeInTheDocument();

    await user.click(within(settingsTree).getByRole("treeitem", { name: /银行账户/ }));
    expect(within(settingsPage).getByRole("heading", { name: "银行账户映射" })).toBeInTheDocument();
    await user.click(within(settingsTree).getByRole("treeitem", { name: /OA导入设置/ }));
    expect(within(settingsPage).getByRole("heading", { name: "OA导入设置" })).toBeInTheDocument();
    expect(within(settingsPage).getByRole("heading", { name: "OA全量搜索导入" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "支付申请" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "日常报销" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "已完成" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "进行中" })).not.toBeChecked();
    const oaImportSection = within(settingsPage).getByRole("region", { name: "OA导入设置" });
    expect(within(oaImportSection).queryByText("票据类型")).not.toBeInTheDocument();
    expect(within(oaImportSection).queryByText(/^0$/)).not.toBeInTheDocument();
    expect(within(oaImportSection).queryByText(/^4$/)).not.toBeInTheDocument();
    expect(within(oaImportSection).queryByText("REJECTED")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("OA导入起始日期"));
    await user.type(screen.getByLabelText("OA导入起始日期"), "2026-02-01");
    await user.click(screen.getByRole("checkbox", { name: "进行中" }));
    await user.click(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ }));
    await waitFor(() => {
      expect(within(settingsPage).getByRole("region", { name: "冲账规则" })).toBeInTheDocument();
    });
    const oaInvoiceOffsetSection = within(settingsPage).getByRole("region", { name: "冲账规则" });
    const applicantInput = within(oaInvoiceOffsetSection).getByRole("textbox");
    await user.clear(applicantInput);
    await user.type(applicantInput, "周洁莹、李四");
    await user.click(within(settingsTree).getByRole("treeitem", { name: /访问账户/ }));
    expect(within(settingsPage).getByRole("heading", { name: "访问账户管理" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("新增访问账户"), "READONLY001");
    await user.selectOptions(screen.getByLabelText("新增账户权限"), "read_export_only");
    await user.click(screen.getByRole("button", { name: "新增账户" }));
    await user.click(screen.getByRole("button", { name: "保存设置" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"allowed_usernames\":[\"READONLY001\"]"),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"readonly_export_usernames\":[\"READONLY001\"]"),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"admin_usernames\":[\"YNSYLP005\"]"),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"oa_retention\":{\"cutoff_date\":\"2026-02-01\"}"),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"oa_import\":{\"form_types\":[\"payment_request\",\"expense_claim\"],\"statuses\":[\"completed\",\"in_progress\"],\"attachment_invoice_promotion_mode\":\"link_existing_only\"}"),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"oa_invoice_offset\":{\"applicant_names\":[\"周洁莹\",\"李四\"]}"),
      }),
    );
    expect(await screen.findByText("已保存关联台设置。")).toBeInTheDocument();
  }, 30_000);

  test("YNSYKJ001 can see OA invoice offset settings without access account management", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "full_access",
      sessionUsername: "YNSYKJ001",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ })).toBeInTheDocument();
    expect(within(settingsTree).queryByRole("treeitem", { name: /访问账户/ })).not.toBeInTheDocument();
    await user.click(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ }));
    expect(within(settingsPage).getByRole("heading", { name: "冲账规则" })).toBeInTheDocument();
  });

  test("bank account settings can edit names without blanking the settings page", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    await waitFor(() => {
      expect(within(settingsPage).getByRole("tree", { name: "设置分类" })).toBeInTheDocument();
    });
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /银行账户/ }));

    expect(within(settingsPage).getByRole("heading", { name: "银行账户映射" })).toBeInTheDocument();
    const bankMappingTable = within(settingsPage).getByRole("table", { name: "银行账户映射" });
    const bankMappingRow = within(bankMappingTable).getByRole("row", { name: "建设银行 8826 建行" });
    const [bankNameInput, last4Input, shortNameInput] = within(bankMappingRow).getAllByRole("textbox");
    await user.clear(bankNameInput);
    await user.type(bankNameInput, "中国建设银行股份有限公司");

    await user.clear(shortNameInput);
    await user.type(shortNameInput, "建行");

    await user.clear(last4Input);
    await user.type(last4Input, "8826");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(bankNameInput).toHaveValue("中国建设银行股份有限公司");
    expect(shortNameInput).toHaveValue("建行");
    expect(last4Input).toHaveValue("8826");
  });

  test("project status settings can sync, add, move, and delete local projects", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /项目状态/ }));

    expect(within(settingsPage).getByRole("heading", { name: "项目状态管理" })).toBeInTheDocument();
    expect(within(settingsPage).getByText("进行中项目")).toBeInTheDocument();
    expect(within(settingsPage).getByText("已完成项目")).toBeInTheDocument();
    expect(within(settingsPage).getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeInTheDocument();

    await user.click(within(settingsPage).getByRole("button", { name: "从 OA 拉取项目" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/projects/sync",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ actor_id: "YNSYLP005" }),
      }),
    );
    expect(await within(settingsPage).findByText("OA 同步新增项目")).toBeInTheDocument();

    await user.type(within(settingsPage).getByLabelText("项目编码"), "LOCAL-001");
    await user.type(within(settingsPage).getByLabelText("项目名称"), "本地测试项目");
    await user.click(within(settingsPage).getByRole("button", { name: "新增本地项目" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/projects",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          actor_id: "YNSYLP005",
          project_code: "LOCAL-001",
          project_name: "本地测试项目",
        }),
      }),
    );
    expect(await within(settingsPage).findByText("本地测试项目")).toBeInTheDocument();

    await user.click(within(settingsPage).getByRole("button", { name: /本地测试项目.*标记完成/ }));
    const completedColumn = within(settingsPage).getByText("已完成项目").closest(".settings-project-column");
    expect(completedColumn).not.toBeNull();
    expect(within(completedColumn as HTMLElement).getByText("本地测试项目")).toBeInTheDocument();

    await user.click(within(completedColumn as HTMLElement).getByRole("button", { name: /本地测试项目.*删除/ }));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("不会删除 OA 源项目和历史数据"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/projects/proj_manual_local_001",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(within(settingsPage).queryByText("本地测试项目")).not.toBeInTheDocument();
  }, 30_000);

  test("admin data reset requires impact confirmation and current OA password", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsTree).getByRole("treeitem", { name: /数据重置/ })).toBeInTheDocument();

    await user.click(within(settingsTree).getByRole("treeitem", { name: /数据重置/ }));
    expect(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" })).toBeInTheDocument();
    expect(within(settingsPage).getByRole("button", { name: "清除所有发票（进销）数据" })).toBeInTheDocument();
    expect(within(settingsPage).getByRole("button", { name: "清除所有 OA 数据并重新写入" })).toBeInTheDocument();
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "确认数据重置" });
    expect(within(confirmDialog).getByText(/不影响 OA 源库/)).toBeInTheDocument();

    await user.click(within(confirmDialog).getByRole("button", { name: "继续" }));
    const passwordDialog = await screen.findByRole("dialog", { name: "OA 密码复核" });
    expect(within(passwordDialog).getByText(/请输入当前 OA 用户密码/)).toBeInTheDocument();
    expect(within(passwordDialog).queryByLabelText(/用户名/)).not.toBeInTheDocument();

    await user.type(within(passwordDialog).getByLabelText("当前 OA 用户密码"), "correct-password");
    await user.click(within(passwordDialog).getByRole("button", { name: "确认清理" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/data-reset/jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          action: "reset_bank_transactions",
          oa_password: "correct-password",
        }),
      }),
    );
    expect(await screen.findByText(/正在清理 app 内部状态。 25%/)).toBeInTheDocument();
    expect(await screen.findAllByText("已完成数据重置。")).not.toHaveLength(0);
  });

  test("admin data reset progress survives leaving and re-entering settings", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
      dataResetJobPollsBeforeComplete: 20,
    });
    renderAppAt("/");

    let settingsPage = await openWorkbenchSettingsPage(user);
    let settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /数据重置/ }));
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认数据重置" })).getByRole("button", { name: "继续" }));
    const passwordDialog = await screen.findByRole("dialog", { name: "OA 密码复核" });
    await user.type(within(passwordDialog).getByLabelText("当前 OA 用户密码"), "correct-password");
    await user.click(within(passwordDialog).getByRole("button", { name: "确认清理" }));

    expect(await within(settingsPage).findByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();

    await user.click(screen.getByRole("link", { name: "关联台" }));
    await screen.findByTestId("zone-unpaired");
    settingsPage = await openWorkbenchSettingsPage(user);
    settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /数据重置/ }));

    expect(await within(settingsPage).findByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    expect(within(settingsPage).getByRole("button", { name: "清除所有发票（进销）数据" })).toBeDisabled();
    expect(within(settingsPage).getByRole("button", { name: "清除所有 OA 数据并重新写入" })).toBeDisabled();
  });

  test("data reset password failure does not show success feedback", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
      dataResetPasswordShouldFail: true,
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /数据重置/ }));
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有 OA 数据并重新写入" }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认数据重置" })).getByRole("button", { name: "继续" }));
    const passwordDialog = await screen.findByRole("dialog", { name: "OA 密码复核" });
    await user.type(within(passwordDialog).getByLabelText("当前 OA 用户密码"), "wrong-password");
    await user.click(within(passwordDialog).getByRole("button", { name: "确认清理" }));

    expect(await screen.findByText("当前 OA 用户密码复核失败，未执行数据重置。")).toBeInTheDocument();
    expect(screen.queryByText("已完成数据重置。")).not.toBeInTheDocument();
  });

  test("canceling data reset password input does not call reset API or show success", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /数据重置/ }));
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有发票（进销）数据" }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认数据重置" })).getByRole("button", { name: "继续" }));

    const passwordDialog = await screen.findByRole("dialog", { name: "OA 密码复核" });
    await user.type(within(passwordDialog).getByLabelText("当前 OA 用户密码"), "not-sent-password");
    await user.click(within(passwordDialog).getByRole("button", { name: "取消" }));

    expect(screen.queryByRole("dialog", { name: "OA 密码复核" })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => url === "/api/workbench/settings/data-reset/jobs"),
    ).toBe(false);
    expect(screen.queryByText("已完成数据重置。")).not.toBeInTheDocument();
  });

  test("non-admin users do not see access account management in settings", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "full_access",
      sessionUsername: "FULL001",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsTree).queryByRole("treeitem", { name: /访问账户/ })).not.toBeInTheDocument();
    expect(within(settingsTree).queryByRole("treeitem", { name: /冲账规则/ })).not.toBeInTheDocument();
    expect(within(settingsTree).queryByRole("treeitem", { name: /数据重置/ })).not.toBeInTheDocument();
    expect(screen.queryByText("访问账户管理")).not.toBeInTheDocument();
  });

  test("read-only export users do not see data reset tools in settings", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "read_only_export",
      sessionUsername: "EXPORT001",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsTree).queryByRole("treeitem", { name: /数据重置/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "清除所有 OA 数据并重新写入" })).not.toBeInTheDocument();
  });

  test("bank import standalone page sends per-file bank mapping overrides", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "银行流水导入" })).not.toBeInTheDocument();
    const input =
      (screen.queryByLabelText("上传银行流水文件") ?? screen.getByLabelText("上传文件")) as HTMLInputElement;
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });
    const secondBankFile = new File(["bank-demo-2"], "2026-01-01至2026-01-31交易明细.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [bankFile, secondBankFile]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(screen.getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    expect(previewButton).toBeEnabled();
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect(JSON.parse(String(formData.get("file_overrides")))).toEqual([
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

  test("invoice import standalone page combines input and output directions per file", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" }, { timeout: 10_000 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();
    const input =
      (screen.queryByLabelText("上传发票文件") ?? screen.getByLabelText("上传文件")) as HTMLInputElement;
    const outputFile = new File(["invoice-output"], "一月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });
    const inputFile = new File(["invoice-input"], "二月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [outputFile, inputFile]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect(JSON.parse(String(formData.get("file_overrides")))).toEqual([
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

  test("ETC invoice import standalone page starts a background job through the ETC API", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          job_id: "job_etc_001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "正在导入 ETC发票 3/31",
          status: "running",
          phase: "persist_items",
          current: 3,
          total: 31,
          percent: 10,
          message: "正在导入 ETC发票。",
          result_summary: {},
          error: null,
          created_at: "2026-05-03T10:00:00+00:00",
          updated_at: "2026-05-03T10:00:02+00:00",
          finished_at: null,
        },
      ],
    });
    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "ETC发票导入" })).not.toBeInTheDocument();
    expect(screen.getByTestId("background-progress-block")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "正在执行后台任务：正在导入 ETC发票 3/31" })).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("ETC对账任务"), "etc_task_ready_001");
    const input =
      (screen.queryByLabelText("上传ETC zip") ?? screen.getByLabelText("上传文件")) as HTMLInputElement;
    const etcZip = new File(["etc-zip"], "ETC一月发票.zip", {
      type: "application/zip",
      lastModified: 1,
    });

    await user.upload(input, [etcZip]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByText("已完成 1 个 ETC zip 文件预览。")).toBeInTheDocument();
    expect(screen.getByText("ETC-2026-005")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /确认导入/ }));

    await waitFor(() => {
      expect(screen.getAllByText("已开始后台导入").length).toBeGreaterThan(0);
    });
    expect(screen.getByTestId("background-progress-block")).toBeInTheDocument();
    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual(["ETC一月发票.zip"]);
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/confirm");
    expect(confirmCall).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
  });

  test("invoice import standalone page confirms selected preview files without a workbench dialog", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ workbenchLoadDelayMs: 160 });
    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "发票导入" })).not.toBeInTheDocument();
    const input =
      (screen.queryByLabelText("上传发票文件") ?? screen.getByLabelText("上传文件")) as HTMLInputElement;
    const inputFile = new File(["invoice-input"], "二月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [inputFile]);
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /确认导入/ }));

    await waitFor(() => {
      expect(screen.getByText("已确认导入")).toBeInTheDocument();
    });
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/confirm");
    expect(confirmCall).toBeTruthy();
    expect(JSON.parse(String((confirmCall?.[1] as RequestInit).body))).toEqual({
      session_id: "import_session_0001",
      selected_file_ids: ["import_file_0001"],
    });
  });

  test("OA connection errors keep the global status icon independent while warning in the page", async () => {
    installMockApiFetch({
      workbenchOaStatus: { code: "error", message: "OA连接失败，请检查会话或网络" },
    });
    renderAppAt("/");

    const statusIndicator = await screen.findByRole("button", { name: "系统状态正常" });

    expect(statusIndicator).toHaveClass("ok");
    expect(statusIndicator.textContent).toBe("");
    expect(document.querySelector(".global-status-text")).toBeNull();
    expect(await screen.findByText("OA连接失败，请检查会话或网络，本次结果未包含完整 OA 数据。")).toBeInTheDocument();
  });

  test("OA sync polling keeps the global status icon independent from local refresh messages", async () => {
    const fetchMock = installMockApiFetch({
      workbenchOaSyncStatuses: [
        {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
          last_seen_change_at: null,
          last_synced_at: "2026-04-01T11:59:00+08:00",
          lag_seconds: 0,
          failed_event_count: 0,
          version: 1,
        },
        {
          status: "refreshing",
          message: "OA 正在同步，关联台稍后更新",
          dirty_scopes: ["2026-03"],
          last_seen_change_at: "2026-04-01T12:00:00+08:00",
          last_synced_at: "2026-04-01T11:59:00+08:00",
          lag_seconds: 60,
          failed_event_count: 0,
          version: 2,
        },
        {
          status: "refreshing",
          message: "OA 正在同步，关联台稍后更新",
          dirty_scopes: ["2026-03"],
          last_seen_change_at: "2026-04-01T12:00:00+08:00",
          last_synced_at: "2026-04-01T11:59:00+08:00",
          lag_seconds: 61,
          failed_event_count: 0,
          version: 2,
        },
        {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
          changed_scopes: ["all"],
          last_seen_change_at: "2026-04-01T12:00:00+08:00",
          last_synced_at: "2026-04-01T12:00:00+08:00",
          lag_seconds: 0,
          failed_event_count: 0,
          version: 3,
        },
        {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
          changed_scopes: ["all"],
          last_seen_change_at: "2026-04-01T12:00:01+08:00",
          last_synced_at: "2026-04-01T12:00:01+08:00",
          lag_seconds: 0,
          failed_event_count: 0,
          version: 4,
        },
      ],
    });
    renderAppAt("/");

    await screen.findByRole("button", { name: "系统状态正常" });
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/oa-sync/events"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/oa-sync/status"))).toBe(true);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "系统状态正常" })).toHaveClass("ok");
      expect(screen.queryByRole("status", { name: "OA 正在同步，关联台稍后更新" })).not.toBeInTheDocument();
    }, { timeout: 5_000 });

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/oa-sync/status")).length).toBeGreaterThan(2);
      expect(screen.getByRole("button", { name: "系统状态正常" })).toHaveClass("ok");
      expect(screen.queryByRole("status", { name: "OA 正在同步，关联台稍后更新" })).not.toBeInTheDocument();
    }, { timeout: 8_000 });
  });

  test("read-only export users can search and view details but cannot see write actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "read_export_only",
      sessionUsername: "READONLY001",
    });
    renderAppAt("/");

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const pairedZone = await screen.findByTestId("zone-paired");

    expect(screen.queryByRole("button", { name: "银行流水导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ETC发票导入" })).not.toBeInTheDocument();
    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(within(unpairedZone).getByRole("button", { name: "异常处理" })).toBeDisabled();
    expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeDisabled();

    const invoiceRow = within(unpairedZone).getByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });
    expect(within(invoiceRow).queryByRole("button", { name: "忽略" })).not.toBeInTheDocument();
    await user.click(within(invoiceRow).getByRole("button", { name: /查看发票 .* 详情/ }));
    expect(await screen.findByRole("dialog", { name: "发票详情" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    const settingsPage = await openWorkbenchSettingsPage(user);
    expect(within(settingsPage).getByRole("button", { name: "保存设置" })).toBeDisabled();
  });

  test("paired zone withdraw action enables when one row in a relation is selected", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const cancelButton = within(pairedZone).getByRole("button", { name: "撤回关联" });

    expect(cancelButton).toBeDisabled();

    const pairedBankRow = await within(pairedZone).findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await waitFor(() => {
      expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeEnabled();
    });
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    expect(await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ })).toBeInTheDocument();
  });

  test("paired zone withdraw preview blocks immutable OA attachment invoice binding", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      workbenchWithdrawPreview: {
        operation: "withdraw_link",
        operation_type: "withdraw_relation",
        preview_id: "withdraw_relation:immutable-oa-attachment",
        can_submit: false,
        requires_note: false,
        message: "无法撤回：OA 附件发票必须和来源 OA 保持绑定。",
        active_relation: {
          case_id: "CASE-OA-ATT-oa-exp-2066-2",
          row_ids: ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
        },
        submit_expected_versions: {
          "relation:CASE-OA-ATT-oa-exp-2066-2": 1,
        },
        before: {
          groups: [
            {
              group_id: "case:CASE-OA-ATT-oa-exp-2066-2",
              group_type: "relation",
              zone: "paired",
              status: "paired",
              can_withdraw: false,
              oa_rows: [
                {
                  id: "oa-exp-2066-2",
                  type: "oa",
                  applicant: "陈佳玉",
                  project_name: "大理卷烟厂余热综合利用项目",
                  amount: "145.00",
                },
              ],
              bank_rows: [],
              invoice_rows: [
                {
                  id: "oa-att-inv-oa-exp-2066-2-01",
                  type: "invoice",
                  seller_name: "云南铁路发展有限公司",
                  buyer_name: "云南湖源科技有限公司",
                  total_with_tax: "145.00",
                },
              ],
            },
          ],
        },
        after: {
          groups: [
            {
              group_id: "case:CASE-OA-ATT-oa-exp-2066-2",
              group_type: "relation",
              zone: "paired",
              status: "paired",
              can_withdraw: false,
              oa_rows: [
                {
                  id: "oa-exp-2066-2",
                  type: "oa",
                  applicant: "陈佳玉",
                  project_name: "大理卷烟厂余热综合利用项目",
                  amount: "145.00",
                },
              ],
              bank_rows: [],
              invoice_rows: [
                {
                  id: "oa-att-inv-oa-exp-2066-2-01",
                  type: "invoice",
                  seller_name: "云南铁路发展有限公司",
                  buyer_name: "云南湖源科技有限公司",
                  total_with_tax: "145.00",
                },
              ],
            },
          ],
        },
        amount_summary: {
          before: { oa_total: "145.00", bank_total: "-", invoice_total: "145.00" },
          after: { oa_total: "145.00", bank_total: "-", invoice_total: "145.00" },
          status: "matched",
          direction: "payment",
          mismatch_fields: [],
        },
        restored_relations: [
          {
            case_id: "CASE-OA-ATT-oa-exp-2066-2",
            row_ids: ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
            row_types: ["oa", "invoice"],
          },
        ],
      },
    });
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    await user.click(
      await within(pairedZone).findByRole("row", {
        name: /2026-03-25 14:22.*华东设备供应商/,
      }),
    );
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    expect(within(preview).getByRole("heading", { name: "撤回关联" })).toBeInTheDocument();
    expect(within(preview).getByText("无法撤回：OA 附件发票必须和来源 OA 保持绑定。")).toBeInTheDocument();
    expect(within(preview).getByRole("button", { name: "确认撤回" })).toBeDisabled();
    expect(within(preview).getAllByText("陈佳玉").length).toBeGreaterThanOrEqual(2);
    expect(within(preview).getAllByText("云南铁路发展有限公司").length).toBeGreaterThanOrEqual(2);
  });

  test("paired zone supports multi-select cancel and moves the selected group back to open", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const unpairedZone = await screen.findByTestId("zone-unpaired");

    const pairedBankRow = within(pairedZone).getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const pairedInvoiceRow = within(pairedZone).getByRole("row", {
      name: /91310000MA1K8A001X.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await user.click(pairedInvoiceRow);
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));
    const preview = await screen.findByRole("dialog", { name: /^(确认|撤回)关联$/ });
    await user.click(within(preview).getByRole("button", { name: "确认撤回" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/withdraw-link",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-p-202603-001", "bk-p-202603-001", "iv-p-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
            operation_type: "withdraw_relation",
          }),
        }),
      );
    });

    await waitFor(() => {
      expect(
        within(pairedZone).queryByRole("row", {
          name: /2026-03-25 14:22.*华东设备供应商/,
        }),
      ).not.toBeInTheDocument();
      expect(
        within(unpairedZone).getByRole("row", {
          name: /2026-03-25 14:22.*华东设备供应商/,
        }),
      ).toBeInTheDocument();
    });
  });

  test("unpaired zone header exception action opens the unified modal instead of the OA-bank modal", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(screen.getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(screen.queryByRole("dialog", { name: "OA流水异常处理弹窗" })).not.toBeInTheDocument();
    expect(within(exceptionModal).getByText("金额摘要")).toBeInTheDocument();
    expect(within(exceptionModal).getByText("OA合计")).toBeInTheDocument();
    expect(within(exceptionModal).getAllByText("58,000.00").length).toBeGreaterThanOrEqual(2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
          expected_read_model_version: "mock-workbench-generation-1",
        }),
      }),
    );

    await user.click(await within(exceptionModal).findByRole("radio", { name: /追进项发票/ }));
    await user.type(within(exceptionModal).getByLabelText("备注"), "金额核对后暂时继续异常");
    fetchMock.mockClear();
    await user.click(within(exceptionModal).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/exception/apply",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
            scenario_code: "expense_oa_bank_invoice_equal",
            action_code: "wait_input_invoice",
            payload: {
              note: "金额核对后暂时继续异常",
            },
          }),
        }),
      );
    });
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/workbench/actions/oa-bank-exception",
      expect.objectContaining({
        method: "POST",
      }),
    );
    const workbenchRefreshCalls = fetchMock.mock.calls.filter(([input]) => {
      return isWorkbenchInitialRequest(input as RequestInfo | URL);
    });
    expect(workbenchRefreshCalls.length).toBeGreaterThan(0);
  });

  test("processed exception rows move out of the unpaired zone and appear in the processed exception modal", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    expect(within(unpairedZone).getByRole("button", { name: /已处理异常\d+项/ })).toBeInTheDocument();
    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await within(unpairedZone).findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(unpairedZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "统一异常处理" });
    await user.click(await within(exceptionModal).findByRole("radio", { name: /追进项发票/ }));
    await user.type(within(exceptionModal).getByLabelText("备注"), "金额核对后暂时继续异常");
    await user.click(within(exceptionModal).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(
        within(unpairedZone).queryByRole("row", {
          name: /陈涛.*智能工厂设备商/,
        }),
      ).not.toBeInTheDocument();
      expect(
        within(unpairedZone).queryByRole("row", {
          name: /2026-03-28.*智能工厂设备商/,
        }),
      ).not.toBeInTheDocument();
    });

    await user.click(await screen.findByRole("button", { name: /已处理异常\d+项/ }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    expect(within(processedModal).getAllByText("追进项发票").length).toBeGreaterThanOrEqual(2);
    expect(within(processedModal).getByText("OA")).toBeInTheDocument();
    expect(within(processedModal).getByText("银行流水")).toBeInTheDocument();
    expect(within(processedModal).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(processedModal).queryByRole("button", { name: "更多" })).not.toBeInTheDocument();
    expect(within(processedModal).getAllByRole("button", { name: "取消异常处理" }).length).toBeGreaterThan(0);
  });

  test("processed exception modal cancels only the explicitly chosen singleton exception row", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 80 });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openOaRow = await within(unpairedZone).findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await within(unpairedZone).findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(unpairedZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "统一异常处理" });
    await user.click(await within(exceptionModal).findByRole("radio", { name: /追进项发票/ }));
    await user.type(within(exceptionModal).getByLabelText("备注"), "金额核对后暂时继续异常");
    await user.click(within(exceptionModal).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(within(unpairedZone).queryByRole("row", { name: /陈涛.*智能工厂设备商/ })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "统一异常处理" })).not.toBeInTheDocument();
    });

    await user.click(await screen.findByRole("button", { name: /已处理异常\d+项/ }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    await user.click(within(processedModal).getAllByRole("button", { name: "取消异常处理" })[0]);

    const confirmModal = await screen.findByRole("dialog", { name: "取消异常处理确认弹窗" });
    expect(within(confirmModal).getByText("确认取消异常处理后，这组记录会回到未配对区域。")).toBeInTheDocument();

    await user.click(within(confirmModal).getByRole("button", { name: "确认取消异常处理" }));

    expect(screen.queryByRole("dialog", { name: "已处理异常弹窗" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/cancel-exception",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-o-202603-001"],
            expected_read_model_version: "mock-workbench-generation-1",
            comment: "由已处理异常弹窗撤回异常处理",
          }),
        }),
      );
    });
    await waitFor(() => {
      expect(
        within(unpairedZone).getByRole("row", {
          name: /陈涛.*智能工厂设备商/,
        }),
      ).toBeInTheDocument();
      expect(within(unpairedZone).queryByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).not.toBeInTheDocument();
    });
  });

  test("canceling a processed singleton exception restores that row after the fresh workbench refetch", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(unpairedZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "统一异常处理" });
    await user.click(await within(exceptionModal).findByRole("radio", { name: /追进项发票/ }));
    await user.type(within(exceptionModal).getByLabelText("备注"), "金额核对后暂时继续异常");
    await user.click(within(exceptionModal).getByRole("button", { name: "提交处理" }));
    await waitFor(() => {
      expect(within(unpairedZone).queryByRole("row", { name: /陈涛.*智能工厂设备商/ })).not.toBeInTheDocument();
    });
    fetchMock.mockClear();

    await user.click(within(unpairedZone).getByRole("button", { name: /已处理异常\d+项/ }));
    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    await user.click(within(processedModal).getAllByRole("button", { name: "取消异常处理" })[0]);

    const confirmModal = await screen.findByRole("dialog", { name: "取消异常处理确认弹窗" });
    await user.click(within(confirmModal).getByRole("button", { name: "确认取消异常处理" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/actions/cancel-exception",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      const workbenchRefreshCalls = fetchMock.mock.calls.filter(([input]) => {
        return isWorkbenchInitialRequest(input as RequestInfo | URL);
      });
      expect(workbenchRefreshCalls.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(
        within(unpairedZone).getByRole("row", {
          name: /陈涛.*智能工厂设备商/,
        }),
      ).toBeInTheDocument();
      expect(within(unpairedZone).queryByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).not.toBeInTheDocument();
    });
  }, 30_000);

  test("renders an error state when the workbench request fails", async () => {
    installMockApiFetch({ workbenchErrorMonths: ["all"] });
    renderWorkbenchPage();

    expect(await screen.findByText("关联台服务暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByText("workbench failed")).not.toBeInTheDocument();
  });

  test("does not render the global empty state for a stale empty workbench payload", async () => {
    installMockApiFetch({
      workbenchEmptyPayload: true,
      workbenchReadModelStatus: "stale",
      workbenchRefreshStatus: {
        scope_key: "all",
        read_model_status: "stale",
        dirty_scopes: [
          {
            scope_key: "2026-03",
            status: "failed",
            last_error: null,
          },
        ],
        last_error: null,
        retryable: true,
      },
    });
    renderWorkbenchPage();

    await screen.findByTestId("zone-unpaired");
    expect(await screen.findByText("关联台数据已过期，当前结果仅供查看；刷新完成前写操作已禁用。")).toBeInTheDocument();
    expect(screen.queryByText("当前没有可展示的 OA / 银行流水 / 发票记录。")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("zone-unpaired")).getByText("未配对 0 项")).toBeInTheDocument();
  });

  test("requeued workbench refresh failure does not show the stale failure banner", async () => {
    installMockApiFetch({
      workbenchRefreshStatus: {
        scope_key: "all",
        read_model_status: "refreshing",
        dirty_scopes: [
          {
            scope_key: "2026-03",
            status: "failed",
            last_error: "workbench_all_scope_parent_inconsistent: active_relation_open_membership count=4",
          },
          {
            scope_key: "2026-03",
            status: "processing",
          },
        ],
        last_error: null,
        retryable: false,
      },
    });
    renderWorkbenchPage();

    expect(await screen.findByRole("row", { name: /陈涛.*智能工厂设备商/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/关联台刷新失败/)).not.toBeInTheDocument();
      expect(screen.queryByText(/workbench_all_scope_parent_inconsistent/)).not.toBeInTheDocument();
    });
  });

  test("expands one zone to the full workbench area and restores it", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByText("赵华")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /放大 未配对/ }));

    expect(screen.getByTestId("zone-unpaired")).not.toHaveClass("zone-hidden");
    expect(screen.getByTestId("zone-paired")).toHaveClass("zone-hidden");
    expect(screen.getByRole("button", { name: /恢复 未配对/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /恢复 未配对/ }));

    expect(screen.getByTestId("zone-unpaired")).not.toHaveClass("zone-hidden");
    expect(screen.getByTestId("zone-paired")).not.toHaveClass("zone-hidden");
  });
});
