import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

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

  test("open zone header confirm link posts the currently selected rows", async () => {
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

    expect(await screen.findByText("已确认 3 条记录关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
          case_id: "CASE-202603-101",
        }),
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

    expect(await screen.findByText("已确认 2 条记录关联。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/confirm-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
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

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(screen.getByText("正在确认关联...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确定" })).not.toBeInTheDocument();

    expect(await screen.findByText("已确认 2 条记录关联。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确定" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确定" }));

    expect(screen.queryByRole("dialog", { name: "操作状态弹窗" })).not.toBeInTheDocument();
  });

  test("open zone header actions stay disabled until enough rows are selected", async () => {
    const user = userEvent.setup();
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
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    await user.click(await screen.findByRole("button", { name: "设置" }));

    expect(await screen.findByRole("dialog", { name: "关联台设置" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("允许访问账户"), "YNSYLP005");
    await user.click(screen.getByRole("button", { name: "新增账户" }));
    await user.click(screen.getByRole("button", { name: "保存设置" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"allowed_usernames\":[\"YNSYLP005\"]"),
      }),
    );
    expect(await screen.findByText("已保存关联台设置。")).toBeInTheDocument();
  });

  test("paired zone cancel action stays disabled until at least two rows are selected", async () => {
    const user = userEvent.setup();
    renderWorkbenchPage();

    const pairedZone = await screen.findByTestId("zone-paired");
    const cancelButton = within(pairedZone).getByRole("button", { name: "取消配对" });

    expect(cancelButton).toBeDisabled();

    const pairedBankRow = within(pairedZone).getByRole("row", {
      name: /2026-03-25 14:22.*华东设备供应商/,
    });

    await user.click(pairedBankRow);
    expect(cancelButton).toBeDisabled();

    const pairedInvoiceRow = within(pairedZone).getByRole("row", {
      name: /91310000MA1K8A001X.*华东设备供应商/,
    });

    await user.click(pairedInvoiceRow);
    expect(cancelButton).toBeEnabled();
  });

  test("invoice rows can be ignored into the ignored modal and restored back to open", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ actionDelayMs: 80 });
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

    await user.click(within(openZone).getByRole("button", { name: "已忽略1项" }));

    const ignoredModal = await screen.findByRole("dialog", { name: "已忽略弹窗" });
    expect(within(ignoredModal).getByText("杭州溯源科技有限公司")).toBeInTheDocument();

    await user.click(within(ignoredModal).getByRole("button", { name: "撤回忽略" }));

    expect(await screen.findByRole("dialog", { name: "操作状态弹窗" })).toBeInTheDocument();
    expect(screen.getByText("正在撤回忽略...")).toBeInTheDocument();
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
          month: "2026-03",
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
          month: "2026-03",
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
    await user.click(within(openZone).getByRole("button", { name: "已忽略1项" }));

    const ignoredModal = await screen.findByRole("dialog", { name: "已忽略弹窗" });
    await user.click(within(ignoredModal).getByRole("button", { name: "撤回忽略" }));

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
    await user.click(within(pairedZone).getByRole("button", { name: "取消配对" }));

    expect(await screen.findByText("已取消 1 组配对。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/cancel-link",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
          row_id: "bk-p-202603-001",
          comment: "由关联台批量取消配对",
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
    await user.click(within(exceptionModal).getByRole("button", { name: "继续报异常" }));

    expect(await screen.findByText("已对 2 条记录执行 OA/流水异常处理。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/actions/oa-bank-exception",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
          row_ids: ["oa-o-202603-001", "bk-o-202603-001"],
          exception_code: "oa_bank_amount_mismatch",
          exception_label: "金额不一致，继续异常",
          comment: "金额核对后暂时继续异常",
        }),
      }),
    );
  });

  test("processed exception rows move out of the open zone and appear in the processed exception modal", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    expect(within(openZone).getByRole("button", { name: "已处理异常0项" })).toBeInTheDocument();
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

    await user.click(within(openZone).getByRole("button", { name: "已处理异常2项" }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    expect(within(processedModal).getAllByText("金额不一致，继续异常")).toHaveLength(2);
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

    await user.click(within(openZone).getByRole("button", { name: "已处理异常2项" }));

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
          month: "2026-03",
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

  test("renders an error state when the workbench request fails", async () => {
    installMockApiFetch({ workbenchErrorMonths: ["2026-03"] });
    renderWorkbenchPage();

    expect(await screen.findByText("工作台数据加载失败，请稍后重试。")).toBeInTheDocument();
  });

  test("expands one zone to the full workbench area and restores it", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByText("赵华")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "放大 未配对" }));

    expect(screen.getByTestId("zone-open")).toBeInTheDocument();
    expect(screen.queryByTestId("zone-paired")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复 未配对" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "恢复 未配对" }));

    expect(screen.getByTestId("zone-open")).toBeInTheDocument();
    expect(screen.getByTestId("zone-paired")).toBeInTheDocument();
  });
});
