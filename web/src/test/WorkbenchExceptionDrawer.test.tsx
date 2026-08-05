import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import type { WorkbenchRecord, WorkbenchRelationGroup } from "../features/workbench/types";

const anomalyItem = {
  code: "oa_invoice_amount_mismatch" as const,
  label: "金额不一致",
  displayLabel: "金额不一致",
  fingerprint: "a".repeat(64),
  comparisonUnitId: "case:CASE-1",
  oaTotal: "100.00",
  invoiceTotal: "99.99",
  amountDelta: "0.01",
  invoiceRowIds: ["invoice-1"],
  attachmentFileCount: 0,
};

const anomaly = {
  code: "oa_invoice_anomaly" as const,
  fingerprint: "b".repeat(64),
  state: "active" as const,
  items: [anomalyItem],
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
  oaInvoiceAnomaly: anomalyItem,
};

const group: WorkbenchRelationGroup = {
  id: "case:CASE-1",
  groupType: "paired",
  rawGroupType: "relation",
  matchConfidence: "high",
  reason: "active_formal_relation",
  rows: { oa: [], bank: [], invoice: [invoiceRow] },
  oaInvoiceAnomaly: anomaly,
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
        loading={false}
        open
        onBucketChange={vi.fn()}
        onClose={vi.fn()}
        onIgnoreOaInvoiceAnomaly={onIgnore}
        onRestoreOaInvoiceAnomaly={vi.fn()}
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
    const chip = screen.getByText("金额不一致").closest('[data-slot="chip"]');
    expect(source.closest(".invoice-chip-row")?.nextElementSibling).toBe(chip);
    expect(chip).toHaveAttribute("title", "OA 100.00 / 发票 99.99 / 差额 0.01");
  });

  test("renders a missing OA attachment as one non-interactive invoice anomaly row", async () => {
    const missingItem = {
      ...anomalyItem,
      code: "oa_invoice_attachment_missing" as const,
      label: "OA发票附件缺失",
      displayLabel: "OA发票附件缺失",
      invoiceTotal: undefined,
      amountDelta: undefined,
      invoiceRowIds: [],
      attachmentFileCount: 1,
    };
    const onSelectRow = vi.fn();

    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "sellerName", label: "销方", track: "1fr", minWidth: 120 }]}
        paneId="invoice"
        row={{
          ...invoiceRow,
          id: "missing-item",
          displayOnly: true,
          sourceKind: "oa_attachment_unknown",
          label: "OA发票附件缺失",
          oaInvoiceAnomaly: missingItem,
        }}
        rowState="idle"
        showWorkflowActions={false}
        zoneId="unpaired"
        onOpenDetail={vi.fn()}
        onRowAction={vi.fn()}
        onSelectRow={onSelectRow}
      />,
    );

    const chip = screen.getByText("OA发票附件缺失").closest('[data-slot="chip"]');
    expect(chip).toHaveAttribute("title", "OA子付款项已上传 1 个附件，但未解析出发票");
    await userEvent.click(chip!.closest('[role="row"]') as HTMLElement);
    expect(onSelectRow).not.toHaveBeenCalled();
  });

  test("shows ignored mismatch and withdraws the ignore without a confirmation modal", async () => {
    const user = userEvent.setup();
    const ignoredItem = {
      ...anomalyItem,
      displayLabel: "已忽略：金额不一致",
    };
    const ignoredAnomaly = {
      ...anomaly,
      state: "ignored" as const,
      items: [ignoredItem],
    };
    const ignoredGroup: WorkbenchRelationGroup = {
      ...group,
      oaInvoiceAnomaly: ignoredAnomaly,
      rows: {
        ...group.rows,
        invoice: [{ ...invoiceRow, oaInvoiceAnomaly: ignoredItem }],
      },
    };
    const onRestore = vi.fn();

    render(
      <WorkbenchExceptionDrawer
        bucket="processed"
        canMutateData
        error={null}
        groups={[ignoredGroup]}
        loading={false}
        open
        onBucketChange={vi.fn()}
        onClose={vi.fn()}
        onIgnoreOaInvoiceAnomaly={vi.fn()}
        onRestoreOaInvoiceAnomaly={onRestore}
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
        loading={false}
        open
        onBucketChange={vi.fn()}
        onClose={vi.fn()}
        onIgnoreOaInvoiceAnomaly={vi.fn()}
        onRestoreOaInvoiceAnomaly={vi.fn()}
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
