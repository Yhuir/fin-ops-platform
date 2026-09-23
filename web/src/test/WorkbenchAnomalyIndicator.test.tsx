import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchAnomalyIndicator from "../components/workbench/WorkbenchAnomalyIndicator";
import type { WorkbenchAnomalyItem, WorkbenchRelationGroup, WorkbenchRecord } from "../features/workbench/types";

const anomaly: WorkbenchAnomalyItem = {
  code: "oa_bank_equal_invoice_less",
  label: "OA 流水一致，票少",
  displayLabel: "OA 流水一致，票少",
  fingerprint: "b".repeat(64),
  comparisonUnitId: "case:CASE-1",
  sourceOaIds: ["oa-1"],
  sourceExpenseItemIds: [],
  oaTotal: "100.00",
  bankTotal: "100.00",
  invoiceTotal: "99.00",
  amountDelta: "1.00",
  invoiceRowIds: ["invoice-1"],
  attachmentFileCount: 0,
  displayScope: "row",
  displayPane: "invoice",
  displayRowId: "invoice-1",
};

function renderIndicator() {
  render(<WorkbenchAnomalyIndicator anomalies={[anomaly]} levelLabel="该发票" />);
  return screen.getByRole("button", { name: "该发票有 1 项异常，查看详情" });
}

describe("WorkbenchAnomalyIndicator", () => {
  it("opens and closes from pointer clicks without a prior hover", async () => {
    const user = userEvent.setup({ skipHover: true });
    const trigger = renderIndicator();

    await user.click(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());
  });

  it("dismisses a hover popover on the first click and reopens it on the second click", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());

    fireEvent.mouseEnter(trigger);
    expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument();

    await user.click(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
  });

  it("resets click dismissal after a genuine pointer leave", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());

    await user.unhover(trigger);
    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
  });

  it("shows on keyboard focus and closes with Escape", async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.tab();
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());
    await user.tab();
    await user.tab({ shift: true });
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
  });

  it("runs a row-level resolution action once and closes the popover", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(
      <WorkbenchAnomalyIndicator
        action={{ label: "选择 OA 明细", onPress }}
        anomalies={[{ ...anomaly, code: "oa_invoice_attachment_unassigned", displayLabel: "发票待归属" }]}
        levelLabel="该发票"
      />,
    );

    await user.hover(screen.getByRole("button", { name: "该发票有 1 项异常，查看详情" }));
    await user.click(await screen.findByRole("button", { name: "选择 OA 明细" }));

    expect(onPress).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("button", { name: "选择 OA 明细" })).not.toBeInTheDocument());
  });

  it("shows the reviewer account snapshot and a normal business-time timestamp", async () => {
    const user = userEvent.setup({ skipHover: true });
    render(
      <WorkbenchAnomalyIndicator
        anomalies={[{
          ...anomaly,
          reviewDecision: "accept_paired",
          reviewedByAccount: "YNSYLP007",
          reviewedByName: "杨丽萍",
          reviewedAt: "2026-08-25T17:03:47.404624+08:00",
          reviewNote: "金额差异已核对",
        }]}
        confirmation={{ note: "票面金额少 1.00 元，经确认保留关联" }}
        levelLabel="该关联组"
      />,
    );

    await user.click(screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" }));

    expect(await screen.findByText("已接受该异常风险")).toBeVisible();
    expect(screen.getByText("YNSYLP007（杨丽萍）")).toBeVisible();
    expect(screen.getByText("2026-08-25 17:03:47")).toBeVisible();
    expect(screen.getByText("金额差异已核对")).toBeVisible();
    expect(screen.getByText("确认关联备注")).toBeVisible();
    expect(screen.getByText("票面金额少 1.00 元，经确认保留关联")).toBeVisible();
    expect(screen.queryByText("8")).not.toBeInTheDocument();
    expect(screen.queryByText(/\+08:00/)).not.toBeInTheDocument();
  });
});


it("shows opposing item differences even when the group total cancels out", async () => {
  render(<WorkbenchAnomalyIndicator levelLabel="该关联组" anomalies={[{ ...anomaly, code: "expense_item_amount_mismatch", displayLabel: "明细金额不一致", amountDelta: "0.00", evidenceTotal: "100.00", expenseItemDifferences: [
    { expenseItemIds: ["item-1"], oaTotal: "40.00", evidenceTotal: "0.00", amountDelta: "40.00" },
    { expenseItemIds: ["item-2"], oaTotal: "60.00", evidenceTotal: "100.00", amountDelta: "-40.00" },
  ] }]} />);
  await userEvent.setup({ skipHover: true }).click(screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" }));
  expect(screen.getByText("OA 40.00 · 票据凭证 0.00 · 差额 40.00")).toBeVisible();
  expect(screen.getByText("OA 60.00 · 票据凭证 100.00 · 差额 -40.00")).toBeVisible();
});

function explanationGroup(): WorkbenchRelationGroup {
  return {
    id: "case:explanation", groupType: "unpaired", matchConfidence: "high", reason: "",
    amountCheck: { status: "mismatch", direction: "expense", bankAmount: "1273.06", oaAmount: "1273.06",
      oaTotal: "1273.06", bankTotal: "1273.06", invoiceTotal: "1139.63", supportingDocumentTotal: "140.00",
      evidenceTotal: "1279.63", amountDelta: "6.57", requiresNote: true },
    workbenchAnomaly: { code: "workbench_anomaly", fingerprint: "group", reviewDecision: "pending", reviewNote: "", reviewedByAccount: "", reviewedByName: "", items: [] },
    rows: { bank: [], invoice: [], oa: [{ id: "oa-test", tableValues: { applicant: "测试申请人" }, expenseItems: [
      { id: "item-car", rowIndex: "1", amount: "182.44", projectName: "测试项目", expenseType: "交通费", expenseContent: "顺风车费用" },
      { id: "item-shared", rowIndex: "2", amount: "50.00", projectName: "另一个项目", expenseType: "住宿费" },
    ] } as WorkbenchRecord] },
  };
}

it("explains valid vouchers and the exact different item without changing group state", async () => {
  const group = explanationGroup();
  render(<WorkbenchAnomalyIndicator group={group} levelLabel="该关联组" anomalies={[{
    ...anomaly, code: "oa_bank_equal_invoice_more", displayLabel: "OA 流水一致，票多", amountDelta: "6.57",
    expenseItemDifferences: [{ expenseItemIds: ["item-car"], oaTotal: "182.44", evidenceTotal: "189.01", amountDelta: "6.57" }],
  }]} />);
  expect(screen.getByText("本组待处理 · OA 流水一致，票多 · 差额 6.57 元")).toBeVisible();
  await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
  expect(screen.getByText("正式发票 1139.63 · 补充凭证 140.00")).toBeVisible();
  expect(screen.getByText("票据凭证合计 1279.63")).toBeVisible();
  expect(screen.getByText("测试申请人 · 交通费 · 顺风车费用 · 测试项目")).toBeVisible();
  expect(screen.getByText("OA 182.44 · 票据凭证 189.01 · 差额 6.57")).toBeVisible();
  expect(group.groupType).toBe("unpaired");
});

it("keeps shared item scope, all anomalies, zero totals and missing details explicit", async () => {
  const group = explanationGroup();
  group.amountCheck!.supportingDocumentTotal = "0.00";
  delete group.amountCheck!.evidenceTotal;
  render(<WorkbenchAnomalyIndicator group={group} levelLabel="该关联组" anomalies={[
    { ...anomaly, expenseItemDifferences: [{ expenseItemIds: ["item-car", "item-shared", "not-loaded"], oaTotal: "232.44", evidenceTotal: "250.00", amountDelta: "17.56" }] },
    { ...anomaly, fingerprint: "second", displayLabel: "另一项异常" },
  ]} />);
  expect(screen.getByText("本组待处理 · 2 项异常")).toBeVisible();
  await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
  expect(screen.getByText("正式发票 1139.63 · 补充凭证 0.00")).toBeVisible();
  expect(screen.getByText("票据凭证合计 待核对")).toBeVisible();
  expect(screen.getByText(/测试申请人 · 交通费.*测试申请人 · 住宿费.*子项 not-loaded（明细未加载或无法定位）/)).toBeVisible();
  expect(screen.getByText("另一项异常")).toBeVisible();
});

it("labels accepted group anomalies without claiming they still block pairing", () => {
  const group = explanationGroup();
  group.groupType = "paired";
  group.workbenchAnomaly!.reviewDecision = "accept_paired";
  render(<WorkbenchAnomalyIndicator group={group} levelLabel="该关联组" anomalies={[anomaly]} />);
  expect(screen.getByText(/本组异常已接受/)).toBeVisible();
  expect(screen.queryByText(/本组待处理/)).not.toBeInTheDocument();
});
