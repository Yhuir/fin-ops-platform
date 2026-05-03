import { screen, within } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt, renderWorkbenchPage } from "./renderHelpers";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function openWorkbenchImportMenu(user: ReturnType<typeof userEvent.setup>) {
  const trigger = await screen.findByRole("button", { name: "导入中心" });
  await user.hover(trigger);
  return trigger;
}

async function openWorkbenchSettingsPage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "设置" }));
  return await screen.findByTestId("settings-page");
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

describe("Workbench row selection and detail modal", () => {
  test("clicking an open row toggles multi-selection without opening the detail modal", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const row = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });

    await user.click(row);

    expect(row).toHaveAttribute("data-row-state", "selected");
    expect(screen.queryByRole("dialog", { name: "详情弹窗" })).not.toBeInTheDocument();

    await user.click(row);

    expect(row).toHaveAttribute("data-row-state", "idle");
  });

  test("bank pane time filter supports month selection and clears on second click", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const openBankPane = within(openZone).getByTestId("pane-bank");

    expect(within(openZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
    expect(within(openZone).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);

    await user.click(within(openBankPane).getByRole("button", { name: "银行流水时间筛选" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水时间筛选面板" });

    await user.click(within(dialog).getByRole("button", { name: "按月" }));
    await user.click(within(dialog).getByRole("button", { name: "4月" }));

    expect(within(openZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
    expect(within(openZone).queryByText("智能工厂设备商")).not.toBeInTheDocument();

    await user.click(within(openBankPane).getByRole("button", { name: "清除银行流水时间筛选 2026年4月" }));

    expect(within(openZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
    expect(within(openZone).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);
  });

  test("clicking detail opens the modal and highlights rows with the same case id", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const oaRow = await screen.findByRole("row", {
      name: /赵华.*华东设备供应商/,
    });
    const bankRow = screen.getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const detailButton = within(bankRow).getByRole("button", { name: "详情" });

    await user.click(detailButton);

    const dialog = await screen.findByRole("dialog", { name: "详情弹窗" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("银行流水详情")).toBeInTheDocument();
    expect(screen.getByText("账号")).toBeInTheDocument();
    expect(within(dialog).getByText("招商银行")).toBeInTheDocument();
    expect(within(dialog).getByText("9123")).toBeInTheDocument();
    expect(within(dialog).queryByText("招商银行 9123")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("资金方向")).not.toBeInTheDocument();
    expect(within(dialog).getByText("支出")).toHaveClass("direction-tag");
    expect(oaRow).toHaveAttribute("data-row-state", "related");
    expect(bankRow).toHaveAttribute("data-row-state", "selected");
    expect(fetchMock).toHaveBeenCalledWith("/api/workbench/rows/bk-p-202603-001", expect.any(Object));
  });

  test("modal can be closed after opening from row action", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const invoiceRow = await screen.findByRole("row", {
      name: /91310110MA1F99088Q.*华东设备供应商/,
    });
    await user.click(within(invoiceRow).getByRole("button", { name: "详情" }));

    expect(await screen.findByRole("dialog", { name: "详情弹窗" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭详情" }));

    expect(screen.queryByRole("dialog", { name: "详情弹窗" })).not.toBeInTheDocument();
  });

  test("modal supports closing with escape", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const invoiceRow = await screen.findByRole("row", {
      name: /91310110MA1F99088Q.*华东设备供应商/,
    });
    await user.click(within(invoiceRow).getByRole("button", { name: "详情" }));

    expect(await screen.findByRole("dialog", { name: "详情弹窗" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "详情弹窗" })).not.toBeInTheDocument();
  });

  test("open zone header confirm link opens preview before submit", async () => {
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

    const dialog = await screen.findByRole("dialog", { name: "关联预览" });
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
    expect(beforeGroups).toHaveLength(1);
    expect(within(beforeGroups[0]).getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toHaveClass(
      "record-card-sheet-row",
    );
    expect(within(beforeGroups[0]).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toHaveClass(
      "record-card-sheet-row",
    );
    expect(within(beforeGroups[0]).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveClass(
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
          case_id: "CASE-202603-101",
        }),
      }),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.anything(),
    );

    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByText("已确认 3 条记录关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
          case_id: "CASE-202603-101",
        }),
      }),
    );
  });

  test("amount mismatch preview requires note before confirm submit", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    await user.click(await screen.findByRole("row", { name: /林晨.*尾差设备商/ }));
    await user.click(await screen.findByRole("row", { name: /2026-03-29.*尾差设备商/ }));
    await user.click(await screen.findByRole("row", { name: /91330108MA27B4011E.*杭州溯源科技有限公司/ }));
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    const dialog = await screen.findByRole("dialog", { name: "关联预览" });
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

    await user.type(within(dialog).getByRole("textbox", { name: "备注" }), "发票税额尾差，财务已复核");
    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByText("已确认 3 条记录关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"note\":\"发票税额尾差，财务已复核\""),
      }),
    );
  });

  test("open zone header confirm link explains invalid selection when no bank row is selected", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openInvoiceRow = await screen.findByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(openOaRow);
    await user.click(openInvoiceRow);
    await user.click(screen.getByRole("button", { name: "确认关联" }));

    expect(
      await screen.findByText("确认关联至少需要选择 1 条银行流水，并同时选择 OA 或发票。"),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.anything(),
    );
  });

  test("open zone header confirm link supports bank plus invoice selection without OA", async () => {
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

    const dialog = await screen.findByRole("dialog", { name: "关联预览" });
    const after = within(dialog).getByTestId("relation-preview-after");
    const afterSummary = expectRelationPreviewSummary(after);
    const emptyOaMetric = within(afterSummary).getByTestId("relation-preview-summary-metric-oa");
    expect(within(emptyOaMetric).getByText("-")).toBeInTheDocument();
    expect(emptyOaMetric).not.toHaveClass("mismatch");
    expect(within(after).getByTestId("pane-oa")).not.toHaveClass("mismatch");
    await user.click(within(dialog).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByText("已确认 2 条记录关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["bk-o-202603-001", "iv-o-202603-001"],
          case_id: "CASE-202603-101",
        }),
      }),
    );
  });

  test("workbench action shows a blocking loading modal and requires acknowledgement after completion", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ actionDelayMs: 80 });
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
    const preview = await screen.findByRole("dialog", { name: "关联预览" });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(screen.getByText("正在确认关联...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确定" })).not.toBeInTheDocument();

    expect(await screen.findByText("已确认 2 条记录关联。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确定" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确定" }));

    expect(screen.queryByRole("dialog", { name: "操作状态弹窗" })).not.toBeInTheDocument();
  });

  test("confirm link finishes the blocking modal before the background workbench refresh completes", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ actionDelayMs: 80, workbenchLoadDelayMs: 160 });
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
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
    const preview = await screen.findByRole("dialog", { name: "关联预览" });
    await user.click(within(preview).getByRole("button", { name: "确认关联" }));

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(await screen.findByText("已确认 2 条记录关联。")).toBeInTheDocument();

    expect(
      within(openZone).queryByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(pairedZone).getByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
  });

  test("initial workbench rows render before slow ignored and settings requests finish", async () => {
    installMockApiFetch({
      workbenchPrimaryDelayMs: 20,
      workbenchIgnoredDelayMs: 180,
      workbenchSettingsDelayMs: 180,
    });
    renderWorkbenchPage();

    expect(
      await screen.findByRole("row", {
        name: /陈涛.*智能工厂设备商/,
      }, { timeout: 500 }),
    ).toBeInTheDocument();
  });

  test("cancel link finishes the blocking modal after local state moves the group back to open", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ actionDelayMs: 20, workbenchLoadDelayMs: 160 });
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const openZone = await screen.findByTestId("zone-open");

    const pairedBankRow = await screen.findByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const pairedInvoiceRow = await screen.findByRole("row", {
      name: /91310000MA1K8A001X.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await user.click(pairedInvoiceRow);
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    const preview = await screen.findByRole("dialog", { name: "关联预览" });
    expect(within(preview).getByText("撤回关联预览")).toBeInTheDocument();
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
    expect(afterGroups).toHaveLength(2);
    const restoredGroup = afterGroups.find((group) => within(group).queryByRole("row", { name: /赵华.*华东设备供应商/ }));
    expect(restoredGroup).toBeDefined();
    expect(within(restoredGroup!).getByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).toBeInTheDocument();
    expect(within(restoredGroup!).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ })).not.toBeInTheDocument();
    const bankOnlyGroup = afterGroups.find((group) => within(group).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ }));
    expect(bankOnlyGroup).toBeDefined();
    expect(within(bankOnlyGroup!).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "确认撤回" }));

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(await screen.findByText("已撤回 1 组关联。")).toBeInTheDocument();
    expect(
      within(pairedZone).queryByRole("row", {
        name: /2026-03-25 14:22.*华东设备供应商/,
      }),
    ).not.toBeInTheDocument();
    const openGroupsAfterWithdraw = within(openZone).getAllByTestId(/^candidate-group-/);
    const restoredOpenGroup = openGroupsAfterWithdraw.find((group) => within(group).queryByRole("row", { name: /赵华.*华东设备供应商/ }));
    expect(restoredOpenGroup).toBeDefined();
    expect(within(restoredOpenGroup!).getByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).toBeInTheDocument();
    expect(within(restoredOpenGroup!).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ })).not.toBeInTheDocument();
    const bankOnlyOpenGroup = openGroupsAfterWithdraw.find((group) =>
      within(group).queryByRole("row", { name: /2026-03-25 14:22.*华东设备供应商/ }),
    );
    expect(bankOnlyOpenGroup).toBeDefined();
    expect(within(bankOnlyOpenGroup!).queryByRole("row", { name: /赵华.*华东设备供应商/ })).not.toBeInTheDocument();
    expect(within(bankOnlyOpenGroup!).queryByRole("row", { name: /91310000MA1K8A001X.*华东设备供应商/ })).not.toBeInTheDocument();
  });

  test("open zone enables withdraw link only for groups with history", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const withdrawButton = within(openZone).getByRole("button", { name: "撤回关联" });
    expect(withdrawButton).toBeDisabled();

    await user.click(await within(openZone).findByRole("row", { name: /孙敏.*华东设备供应商/ }));

    expect(withdrawButton).toBeEnabled();

    await user.click(withdrawButton);
    const preview = await screen.findByRole("dialog", { name: "关联预览" });
    expect(within(preview).getByText("撤回关联预览")).toBeInTheDocument();
    const before = within(preview).getByTestId("relation-preview-before");
    const after = within(preview).getByTestId("relation-preview-after");
    expectRelationPreviewSummary(before);
    expectRelationPreviewSummary(after);
    expectRelationPreviewTriPane(before);
    expectRelationPreviewTriPane(after);
  });

  test("unified pane search filters candidate groups across all panes and highlights matches", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const openOaPane = within(openZone).getByTestId("pane-oa");

    await user.click(within(openOaPane).getByRole("button", { name: "搜索 OA" }));
    await user.type(within(openOaPane).getByLabelText("搜索 OA"), "智能工厂");

    expect(within(openZone).getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toBeInTheDocument();
    expect(within(openZone).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeInTheDocument();
    expect(within(openZone).getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeInTheDocument();
    expect(within(openZone).queryByText("杭州张三广告有限公司")).not.toBeInTheDocument();
    expect(within(openZone).getAllByText("智能工厂").length).toBeGreaterThan(0);
    expect(within(openZone).getAllByText("智能工厂").some((node) => node.classList.contains("search-hit"))).toBe(true);

    await user.click(within(openOaPane).getByRole("button", { name: "清空搜索 OA" }));

    expect(within(openZone).getAllByText("杭州张三广告有限公司").length).toBeGreaterThan(0);
  });

  test("open zone header actions stay disabled until enough rows are selected", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");

    const clearButton = within(openZone).getByRole("button", { name: "清空选择" });
    const confirmButton = within(openZone).getByRole("button", { name: "确认关联" });
    const exceptionButton = within(openZone).getByRole("button", { name: "异常处理" });

    expect(clearButton).toBeEnabled();
    expect(confirmButton).toBeDisabled();
    expect(exceptionButton).toBeDisabled();

    const openOaRow = within(openZone).getByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });

    await user.click(openOaRow);

    expect(confirmButton).toBeDisabled();
    expect(exceptionButton).toBeEnabled();

    const openBankRow = within(openZone).getByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openBankRow);

    expect(confirmButton).toBeEnabled();
    expect(exceptionButton).toBeEnabled();
  });

  test("workbench settings can manage allowed app accounts", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "杨南山",
    });
    renderAppAt("/");

    const settingsPage = await openWorkbenchSettingsPage(user);
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(settingsPage).getByRole("heading", { name: "设置分类" })).toBeInTheDocument();
    expect(screen.queryByText("设置项")).not.toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /项目状态/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /银行账户/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /OA导入设置/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ })).toBeInTheDocument();
    expect(within(settingsTree).getByRole("treeitem", { name: /访问账户/ })).toBeInTheDocument();
    expect(within(settingsPage).getByRole("heading", { name: "项目状态管理" })).toBeInTheDocument();

    await user.click(within(settingsTree).getByRole("treeitem", { name: /银行账户/ }));
    expect(within(settingsPage).getByRole("heading", { name: "银行账户映射" })).toBeInTheDocument();
    await user.click(within(settingsTree).getByRole("treeitem", { name: /OA导入设置/ }));
    expect(within(settingsPage).getByRole("heading", { name: "OA导入设置" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "支付申请" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "日常报销" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "已完成" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "进行中" })).not.toBeChecked();
    expect(within(settingsPage).queryByText("票据类型")).not.toBeInTheDocument();
    expect(within(settingsPage).queryByText(/^0$/)).not.toBeInTheDocument();
    expect(within(settingsPage).queryByText(/^4$/)).not.toBeInTheDocument();
    expect(within(settingsPage).queryByText("REJECTED")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("OA导入起始日期"));
    await user.type(screen.getByLabelText("OA导入起始日期"), "2026-02-01");
    await user.click(screen.getByRole("checkbox", { name: "进行中" }));
    await user.click(within(settingsTree).getByRole("treeitem", { name: /冲账规则/ }));
    expect(within(settingsPage).getByRole("heading", { name: "冲账规则" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("冲账申请人"));
    await user.type(screen.getByLabelText("冲账申请人"), "周洁莹、李四");
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
        body: expect.stringContaining("\"oa_import\":{\"form_types\":[\"payment_request\",\"expense_claim\"],\"statuses\":[\"completed\",\"in_progress\"]}"),
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
  });

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
    const settingsTree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(settingsTree).getByRole("treeitem", { name: /银行账户/ }));

    expect(within(settingsPage).getByRole("heading", { name: "银行账户映射" })).toBeInTheDocument();
    const bankNameInputs = within(settingsPage).getAllByLabelText("银行名称");
    const shortNameInputs = within(settingsPage).getAllByLabelText("简称");
    const last4Inputs = within(settingsPage).getAllByLabelText(/后四位|银行卡后四位/);

    await user.clear(bankNameInputs[1]);
    await user.type(bankNameInputs[1], "中国建设银行股份有限公司");
    await user.clear(shortNameInputs[1]);
    await user.type(shortNameInputs[1], "建行");
    await user.clear(last4Inputs[1]);
    await user.type(last4Inputs[1], "8826");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(within(settingsPage).getByDisplayValue("中国建设银行股份有限公司")).toBeInTheDocument();
    expect(within(settingsPage).getByDisplayValue("建行")).toBeInTheDocument();
    expect(within(settingsPage).getByDisplayValue("8826")).toBeInTheDocument();
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
  });

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
    await screen.findByTestId("zone-open");
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

  test("bank import opens a dialog and sends per-file bank mapping overrides", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "银行流水导入" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水导入" });
    const input = within(dialog).getByLabelText("上传银行流水文件") as HTMLInputElement;
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });
    const secondBankFile = new File(["bank-demo-2"], "2026-01-01至2026-01-31交易明细.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [bankFile, secondBankFile]);
    const previewButton = within(dialog).getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(within(dialog).getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(within(dialog).getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    expect(previewButton).toBeEnabled();
    await user.click(previewButton);

    expect(await within(dialog).findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
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

  test("invoice import combines input and output entry points and sends per-file directions", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    expect(await screen.findByRole("button", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "发票导入" }));
    const dialog = await screen.findByRole("dialog", { name: "发票导入" });
    const input = within(dialog).getByLabelText("上传发票文件") as HTMLInputElement;
    const outputFile = new File(["invoice-output"], "一月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });
    const inputFile = new File(["invoice-input"], "二月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [outputFile, inputFile]);
    const previewButton = within(dialog).getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(within(dialog).getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(within(dialog).getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(previewButton);

    expect(await within(dialog).findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
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

  test("ETC invoice import opens a dialog and uses zip preview before confirm", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "ETC发票导入" }));
    const dialog = await screen.findByRole("dialog", { name: "ETC发票导入" });
    const input = within(dialog).getByLabelText("上传ETC zip") as HTMLInputElement;
    const etcZip = new File(["etc-zip"], "ETC一月发票.zip", {
      type: "application/zip",
      lastModified: 1,
    });

    await user.upload(input, [etcZip]);
    await user.click(within(dialog).getByRole("button", { name: "开始预览" }));

    expect(await within(dialog).findByText("已完成 1 个 ETC zip 文件预览。")).toBeInTheDocument();
    expect(within(dialog).getByText("ETC-2026-005")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认导入" }));

    await waitFor(() => {
      expect(within(dialog).getAllByText("已导入 ETC票据管理").length).toBeGreaterThan(0);
    });
    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual(["ETC一月发票.zip"]);
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/confirm");
    expect(confirmCall).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
  });

  test("import completion marks the global status icon pending and returns to synced", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ workbenchLoadDelayMs: 160 });
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "发票导入" }));
    const dialog = await screen.findByRole("dialog", { name: "发票导入" });
    const input = within(dialog).getByLabelText("上传发票文件") as HTMLInputElement;
    const inputFile = new File(["invoice-input"], "二月发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });

    await user.upload(input, [inputFile]);
    await user.selectOptions(within(dialog).getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(within(dialog).getByRole("button", { name: "开始预览" }));
    expect(await within(dialog).findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认导入" }));

    await waitFor(() => {
      const statusIndicator = screen.getByRole("status", { name: "已导入 1 个文件，正在刷新关联台。" });
      expect(statusIndicator).toHaveClass("pending");
      expect(statusIndicator.textContent).toBe("");
    });
    expect(document.querySelector(".global-status-text")).toBeNull();
    expect(screen.queryByText("已导入 1 个文件，正在后台刷新关联台。")).not.toBeInTheDocument();
    expect(document.querySelector(".action-feedback")).toBeNull();

    await waitFor(() => {
      const statusIndicator = screen.getByRole("status", { name: "OA 已同步" });
      expect(statusIndicator).toHaveClass("ok");
      expect(statusIndicator.textContent).toBe("");
    });
  });

  test("OA connection errors mark the global status icon red with the failure reason", async () => {
    installMockApiFetch({
      workbenchOaStatus: { code: "error", message: "OA连接失败，请检查会话或网络" },
    });
    renderAppAt("/");

    const statusIndicator = await screen.findByRole("status", { name: "OA连接失败，请检查会话或网络" });

    expect(statusIndicator).toHaveClass("error");
    expect(statusIndicator.textContent).toBe("");
    expect(document.querySelector(".global-status-text")).toBeNull();
  });

  test("OA sync polling marks refreshing status and coalesces synced refreshes", async () => {
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

    await screen.findByRole("status", { name: "OA 已同步" });
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/oa-sync/events"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/oa-sync/status"))).toBe(true);

    await waitFor(() => {
      const refreshingIndicator = screen.getByRole("status", { name: "OA 正在同步，关联台稍后更新" });
      expect(refreshingIndicator).toHaveClass("pending");
    }, { timeout: 5_000 });

    const initialWorkbenchFetchCount = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/workbench?")).length;

    await waitFor(() => {
      const workbenchFetchCount = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/workbench?")).length;
      expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/oa-sync/status")).length).toBeGreaterThan(2);
      expect(workbenchFetchCount).toBe(initialWorkbenchFetchCount + 1);
    }, { timeout: 8_000 });
  });

  test("read-only export users can search and view details but cannot see write actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "read_export_only",
      sessionUsername: "READONLY001",
    });
    renderAppAt("/");

    const openZone = await screen.findByTestId("zone-open");
    const pairedZone = await screen.findByTestId("zone-paired");

    expect(screen.queryByRole("button", { name: "银行流水导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ETC发票导入" })).not.toBeInTheDocument();
    expect(within(openZone).getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(within(openZone).getByRole("button", { name: "异常处理" })).toBeDisabled();
    expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeDisabled();

    const invoiceRow = within(openZone).getByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });
    expect(within(invoiceRow).queryByRole("button", { name: "忽略" })).not.toBeInTheDocument();
    await user.click(within(invoiceRow).getByRole("button", { name: "详情" }));
    expect(await screen.findByRole("dialog", { name: "详情弹窗" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情" }));

    await user.click(screen.getByRole("button", { name: "搜索" }));
    expect(await screen.findByRole("dialog", { name: "关联台搜索" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭搜索" }));

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

    const pairedBankRow = within(pairedZone).getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await waitFor(() => {
      expect(within(pairedZone).getByRole("button", { name: "撤回关联" })).toBeEnabled();
    });
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

    expect(await screen.findByRole("dialog", { name: "关联预览" })).toBeInTheDocument();
  });

  test("invoice rows can be ignored into the ignored modal and restored back to open", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 200 });
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const invoiceRow = within(openZone).getByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(within(invoiceRow).getByRole("button", { name: "忽略" }));

    expect(await screen.findByText("已忽略 1 条记录。")).toBeInTheDocument();
    expect(
      within(openZone).queryByRole("row", {
        name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
      }),
    ).not.toBeInTheDocument();

    await user.click(within(openZone).getByRole("button", { name: /已忽略\d+项/ }));

    const ignoredModal = await screen.findByRole("dialog", { name: "已忽略弹窗" });
    const ignoredInvoiceRow = within(ignoredModal).getByRole("row", {
      name: /智能工厂设备商.*杭州溯源科技有限公司/,
    });
    expect(ignoredInvoiceRow).toBeInTheDocument();

    await user.click(within(ignoredInvoiceRow).getByRole("button", { name: "撤回忽略" }));

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(await screen.findByText("正在撤回忽略...")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "已忽略弹窗" })).not.toBeInTheDocument();

    expect(await screen.findByText("已撤回忽略 1 条记录。")).toBeInTheDocument();
    expect(
      within(openZone).getByRole("row", {
        name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
      }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/ignore-row",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_id: "iv-o-202603-001",
          comment: "由关联台忽略发票：iv-o-202603-001",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/unignore-row",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_id: "iv-o-202603-001",
        }),
      }),
    );
  });

  test("unignore shows a friendly error when the api returns an empty body", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ emptyBodyPaths: ["/api/workbench/actions/unignore-row"] });
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const invoiceRow = within(openZone).getByRole("row", {
      name: /91330108MA27B4011D.*杭州溯源科技有限公司/,
    });

    await user.click(within(invoiceRow).getByRole("button", { name: "忽略" }));
    await screen.findByText("已忽略 1 条记录。");
    await user.click(within(openZone).getByRole("button", { name: /已忽略\d+项/ }));

    const ignoredModal = await screen.findByRole("dialog", { name: "已忽略弹窗" });
    await user.click(within(ignoredModal).getAllByRole("button", { name: "撤回忽略" })[0]);

    expect(await screen.findByText("操作失败，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByText(/Unexpected end of JSON input/)).not.toBeInTheDocument();
  });

  test("paired zone supports multi-select cancel and moves the selected group back to open", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const openZone = await screen.findByTestId("zone-open");

    const pairedBankRow = within(pairedZone).getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });
    const pairedInvoiceRow = within(pairedZone).getByRole("row", {
      name: /91310000MA1K8A001X.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    await user.click(pairedInvoiceRow);
    await user.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));
    const preview = await screen.findByRole("dialog", { name: "关联预览" });
    await user.click(within(preview).getByRole("button", { name: "确认撤回" }));

    expect(await screen.findByText("已撤回 1 组关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/withdraw-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-p-202603-001", "bk-p-202603-001", "iv-p-202603-001"],
        }),
      }),
    );

    expect(
      within(pairedZone).queryByRole("row", {
        name: /2026-03-25 14:22.*华东设备供应商/,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(openZone).getByRole("row", {
        name: /2026-03-25 14:22.*华东设备供应商/,
      }),
    ).toBeInTheDocument();
  });

  test("open zone header exception action opens the OA-bank modal and submits a structured exception", async () => {
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

    const exceptionModal = await screen.findByRole("dialog", { name: "OA流水异常处理弹窗" });
    expect(within(exceptionModal).getByText("OA合计")).toBeInTheDocument();
    expect(within(exceptionModal).getAllByText("58,000.00")).toHaveLength(2);
    expect(within(exceptionModal).getByText("流水合计")).toBeInTheDocument();
    expect(within(exceptionModal).getByText("差额")).toBeInTheDocument();

    await user.selectOptions(within(exceptionModal).getByLabelText("异常情况"), "oa_bank_amount_mismatch");
    await user.type(within(exceptionModal).getByLabelText("备注"), "金额核对后暂时继续异常");
    fetchMock.mockClear();
    await user.click(within(exceptionModal).getByRole("button", { name: "继续报异常" }));

    expect(await screen.findByText("已对 2 条记录执行 OA/流水异常处理。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/oa-bank-exception",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
          exception_code: "oa_bank_amount_mismatch",
          exception_label: "金额不一致，继续异常",
          comment: "金额核对后暂时继续异常",
        }),
      }),
    );
    const workbenchRefreshCalls = fetchMock.mock.calls.filter(([input]) => {
      const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return new URL(rawUrl, "http://localhost").pathname === "/api/workbench";
    });
    expect(workbenchRefreshCalls).toHaveLength(0);
  });

  test("processed exception rows move out of the open zone and appear in the processed exception modal", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    expect(within(openZone).getByRole("button", { name: /已处理异常\d+项/ })).toBeInTheDocument();
    const openOaRow = within(openZone).getByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = within(openZone).getByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(openZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "OA流水异常处理弹窗" });
    await user.selectOptions(within(exceptionModal).getByLabelText("异常情况"), "oa_bank_amount_mismatch");
    await user.click(within(exceptionModal).getByRole("button", { name: "继续报异常" }));

    expect(await screen.findByText("已对 2 条记录执行 OA/流水异常处理。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确定" }));

    expect(
      within(openZone).queryByRole("row", {
        name: /陈涛.*智能工厂设备商/,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(openZone).queryByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).not.toBeInTheDocument();

    await user.click(within(openZone).getByRole("button", { name: /已处理异常\d+项/ }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    expect(within(processedModal).getAllByText("金额不一致，继续异常").length).toBeGreaterThanOrEqual(2);
    expect(within(processedModal).getByText("OA")).toBeInTheDocument();
    expect(within(processedModal).getByText("银行流水")).toBeInTheDocument();
    expect(within(processedModal).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(processedModal).queryByRole("button", { name: "更多" })).not.toBeInTheDocument();
    expect(within(processedModal).getAllByRole("button", { name: "取消异常处理" }).length).toBeGreaterThan(0);
  });

  test("processed exception modal can cancel exception handling and move rows back to open", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 80 });
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const openOaRow = within(openZone).getByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = within(openZone).getByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(openZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "OA流水异常处理弹窗" });
    await user.selectOptions(within(exceptionModal).getByLabelText("异常情况"), "oa_bank_amount_mismatch");
    await user.click(within(exceptionModal).getByRole("button", { name: "继续报异常" }));
    await user.click(await screen.findByRole("button", { name: "确定" }));

    await user.click(within(openZone).getByRole("button", { name: /已处理异常\d+项/ }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    await user.click(within(processedModal).getAllByRole("button", { name: "取消异常处理" })[0]);

    const confirmModal = await screen.findByRole("dialog", { name: "取消异常处理确认弹窗" });
    expect(within(confirmModal).getByText("确认取消异常处理后，这组记录会回到未配对区域。")).toBeInTheDocument();

    await user.click(within(confirmModal).getByRole("button", { name: "确认取消异常处理" }));

    expect(screen.queryByRole("dialog", { name: "已处理异常弹窗" })).not.toBeInTheDocument();
    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(screen.getByText("正在取消异常处理...")).toBeInTheDocument();
    expect(await screen.findByText("已取消 2 条记录的异常处理。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/cancel-exception",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
          comment: "由已处理异常弹窗撤回异常处理",
        }),
      }),
    );

    await user.click(screen.getByRole("button", { name: "确定" }));
    expect(
      within(openZone).getByRole("row", {
        name: /陈涛.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
    expect(
      within(openZone).getByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
  });

  test("canceling processed exception restores rows locally without starting an all-scope refresh", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 80 });
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const openOaRow = await screen.findByRole("row", {
      name: /陈涛.*智能工厂设备商/,
    });
    const openBankRow = await screen.findByRole("row", {
      name: /2026-03-28.*智能工厂设备商/,
    });

    await user.click(openOaRow);
    await user.click(openBankRow);
    await user.click(within(openZone).getByRole("button", { name: "异常处理" }));

    const exceptionModal = await screen.findByRole("dialog", { name: "OA流水异常处理弹窗" });
    await user.selectOptions(within(exceptionModal).getByLabelText("异常情况"), "oa_bank_amount_mismatch");
    await user.click(within(exceptionModal).getByRole("button", { name: "继续报异常" }));
    await user.click(await screen.findByRole("button", { name: "确定" }));
    fetchMock.mockClear();

    await user.click(within(openZone).getByRole("button", { name: /已处理异常\d+项/ }));
    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    await user.click(within(processedModal).getAllByRole("button", { name: "取消异常处理" })[0]);

    const confirmModal = await screen.findByRole("dialog", { name: "取消异常处理确认弹窗" });
    await user.click(within(confirmModal).getByRole("button", { name: "确认取消异常处理" }));

    expect(await screen.findByText("已取消 2 条记录的异常处理。")).toBeInTheDocument();
    const workbenchRefreshCalls = fetchMock.mock.calls.filter(([input]) => {
      const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return new URL(rawUrl, "http://localhost").pathname === "/api/workbench";
    });
    expect(workbenchRefreshCalls).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "确定" }));

    expect(
      within(openZone).getByRole("row", {
        name: /陈涛.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
    expect(
      within(openZone).getByRole("row", {
        name: /2026-03-28.*智能工厂设备商/,
      }),
    ).toBeInTheDocument();
  });

  test("renders an error state when the workbench request fails", async () => {
    installMockApiFetch({ workbenchErrorMonths: ["all"] });
    renderWorkbenchPage();

    expect(await screen.findByText("工作台数据加载失败，请稍后重试。")).toBeInTheDocument();
  });

  test("expands one zone to the full workbench area and restores it", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByText("赵华")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /放大 未配对/ }));

    expect(screen.getByTestId("zone-open")).not.toHaveClass("zone-hidden");
    expect(screen.getByTestId("zone-paired")).toHaveClass("zone-hidden");
    expect(screen.getByRole("button", { name: /恢复 未配对/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /恢复 未配对/ }));

    expect(screen.getByTestId("zone-open")).not.toHaveClass("zone-hidden");
    expect(screen.getByTestId("zone-paired")).not.toHaveClass("zone-hidden");
  });
});
