import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import type { WorkbenchRecord, WorkbenchRelationGroup } from "../features/workbench/types";

const anomaly = {
  code: "oa_invoice_amount_mismatch" as const,
  label: "金额不一致",
  displayLabel: "金额不一致",
  fingerprint: "a".repeat(64),
  state: "active" as const,
  oaTotal: "100.00",
  invoiceTotal: "99.99",
  amountDelta: "0.01",
};

const invoiceRow: WorkbenchRecord = {
  id: "invoice-1",
  recordType: "invoice",
  sourceKind: "manual_import",
  label: "进项发票",
  status: "已关联",
  statusCode: "paired",
  statusTone: "success",
  exceptionHandled: false,
  amount: "99.99",
  counterparty: "测试供应商",
  tableValues: {
    sellerName: "测试供应商",
    sellerTaxId: "915300000000000000",
    buyerName: "云南溯源科技有限公司",
    buyerTaxId: "915300007194052520",
    invoiceType: "进项发票",
  },
  detailFields: [],
  actionVariant: "detail-only",
  availableActions: ["detail"],
  amountAnomaly: anomaly,
};

const group: WorkbenchRelationGroup = {
  id: "case:CASE-1",
  groupType: "paired",
  rawGroupType: "relation",
  matchConfidence: "high",
  reason: "active_formal_relation",
  rows: { oa: [], bank: [], invoice: [invoiceRow] },
  amountAnomaly: anomaly,
};

describe("Workbench amount mismatch exception UI", () => {
  test("renders a collapsed three-pane outline and expands all details together", async () => {
    const user = userEvent.setup();
    const onIgnore = vi.fn();

    render(
      <WorkbenchExceptionDrawer
        bucket="active"
        canMutateData
        error={null}
        groups={[group]}
        ignoredRows={[]}
        loading={false}
        open
        onBucketChange={vi.fn()}
        onCancelProcessedException={vi.fn()}
        onClose={vi.fn()}
        onIgnoreAmountMismatch={onIgnore}
        onRestoreAmountMismatch={vi.fn()}
        onUnignoreRow={vi.fn()}
      />,
    );

    const drawer = await screen.findByRole("dialog", { name: "异常处理" });
    expect(within(drawer).getByText("OA · 0项")).toBeInTheDocument();
    expect(within(drawer).getByText("流水 · 0项")).toBeInTheDocument();
    expect(within(drawer).getByText("发票 · 1项")).toBeInTheDocument();
    expect(within(drawer).getByText("99.99")).toBeInTheDocument();
    expect(within(drawer).getByRole("radio", { name: "进行中的异常" })).toHaveAttribute("aria-checked", "true");
    expect(within(drawer).getByRole("radio", { name: "已忽略的异常" })).toBeInTheDocument();
    expect(within(drawer).queryByTestId("pane-invoice")).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "展开异常明细" }));
    expect(await within(drawer).findByText("测试供应商")).toBeInTheDocument();
    expect(within(drawer).queryByTestId("pane-invoice")).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "忽略" }));
    expect(onIgnore).toHaveBeenCalledWith(group);
  });

  test("shows the anomaly chip directly after the invoice source row", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "sellerName", label: "销方", track: "1fr", minWidth: 120 }]}
        paneId="invoice"
        row={invoiceRow}
        rowState="idle"
        showWorkflowActions={false}
        zoneId="paired"
        onOpenDetail={vi.fn()}
        onRowAction={vi.fn()}
        onSelectRow={vi.fn()}
      />,
    );

    const source = screen.getByText("人工导入");
    const chip = screen.getByText("金额不一致");
    expect(source.closest(".invoice-chip-row")?.nextElementSibling).toBe(chip);
    expect(chip).toHaveAttribute("title", "OA 100.00 / 发票 99.99 / 差额 0.01");
  });

  test("shows ignored mismatch and withdraws the ignore without a confirmation modal", async () => {
    const user = userEvent.setup();
    const ignoredAnomaly = {
      ...anomaly,
      displayLabel: "已忽略：金额不一致",
      state: "ignored" as const,
    };
    const ignoredGroup: WorkbenchRelationGroup = {
      ...group,
      amountAnomaly: ignoredAnomaly,
      rows: {
        ...group.rows,
        invoice: [{ ...invoiceRow, amountAnomaly: ignoredAnomaly }],
      },
    };
    const onRestore = vi.fn();

    render(
      <WorkbenchExceptionDrawer
        bucket="processed"
        canMutateData
        error={null}
        groups={[ignoredGroup]}
        ignoredRows={[]}
        loading={false}
        open
        onBucketChange={vi.fn()}
        onCancelProcessedException={vi.fn()}
        onClose={vi.fn()}
        onIgnoreAmountMismatch={vi.fn()}
        onRestoreAmountMismatch={onRestore}
        onUnignoreRow={vi.fn()}
      />,
    );

    const drawer = await screen.findByRole("dialog", { name: "异常处理" });
    expect(within(drawer).getAllByText("已忽略：金额不一致").length).toBeGreaterThan(0);
    await user.click(within(drawer).getByRole("button", { name: "撤回忽略" }));
    expect(onRestore).toHaveBeenCalledWith(ignoredGroup);
    expect(screen.queryByRole("dialog", { name: "取消异常处理确认弹窗" })).not.toBeInTheDocument();
  });

  test("keeps only one relation group expanded", async () => {
    const user = userEvent.setup();
    const secondGroup: WorkbenchRelationGroup = {
      ...group,
      id: "case:CASE-2",
      rows: {
        ...group.rows,
        invoice: [{ ...invoiceRow, id: "invoice-2", counterparty: "第二供应商" }],
      },
    };

    render(
      <WorkbenchExceptionDrawer
        bucket="active"
        canMutateData
        error={null}
        groups={[group, secondGroup]}
        ignoredRows={[]}
        loading={false}
        open
        onBucketChange={vi.fn()}
        onCancelProcessedException={vi.fn()}
        onClose={vi.fn()}
        onIgnoreAmountMismatch={vi.fn()}
        onRestoreAmountMismatch={vi.fn()}
        onUnignoreRow={vi.fn()}
      />,
    );

    const drawer = await screen.findByRole("dialog", { name: "异常处理" });
    const triggers = within(drawer).getAllByRole("button", { name: "展开异常明细" });
    await user.click(triggers[0]);
    expect(triggers[0]).toHaveAttribute("aria-expanded", "true");
    await user.click(within(drawer).getAllByRole("button", { name: "展开异常明细" })[0]);
    expect(triggers[0]).toHaveAttribute("aria-expanded", "false");
  });
});
