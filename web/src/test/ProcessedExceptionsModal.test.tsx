import { render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import ProcessedExceptionsModal from "../components/workbench/ProcessedExceptionsModal";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../features/workbench/types";

describe("ProcessedExceptionsModal", () => {
  test("keeps three panes on one row and appends exception reason and note columns", () => {
    render(
      <ProcessedExceptionsModal
        canMutateData
        groups={[processedExceptionGroup]}
        panes={[
          { id: "oa", title: "OA", rows: processedExceptionGroup.rows.oa },
          { id: "bank", title: "银行流水", rows: processedExceptionGroup.rows.bank },
          { id: "invoice", title: "进销项发票", rows: processedExceptionGroup.rows.invoice },
        ]}
        onCancelException={() => undefined}
        onClose={() => undefined}
      />,
    );

    const dialog = screen.getByRole("dialog", { name: "已处理异常弹窗" });
    expect(within(dialog).getByRole("columnheader", { name: "异常原因" })).toBeInTheDocument();
    expect(within(dialog).getByRole("columnheader", { name: "异常备注" })).toBeInTheDocument();
    expect(within(dialog).getByText("OA和支出流水一致，缺进项发票")).toBeInTheDocument();
    expect(within(dialog).getByText("缺进项票，等待补票")).toBeInTheDocument();

    const groupRow = within(dialog).getByTestId("candidate-group-paired-case:EXC-001");
    expect(groupRow.style.gridTemplateColumns).toContain("minmax(360px, 1fr)");
    expect(groupRow.style.gridTemplateColumns).toContain("minmax(220px, 0.5fr)");
    expect(groupRow.style.gridTemplateColumns).toContain("minmax(260px, 0.6fr)");
    expect(within(groupRow).getByText("OA-001")).toBeInTheDocument();
    expect(within(groupRow).getByText("银行供应商")).toBeInTheDocument();
    expect(within(groupRow).getByText("发票供应商")).toBeInTheDocument();
  });
});

const processedExceptionGroup = {
  id: "case:EXC-001",
  groupType: "candidate",
  matchConfidence: "medium",
  reason: "processed_exception",
  rows: {
    oa: [
      buildRow({
        id: "oa-001",
        recordType: "oa",
        tableValues: { projectName: "OA-001", applicant: "刘际涛", amount: "6868.55" },
      }),
    ],
    bank: [
      buildRow({
        id: "bank-001",
        recordType: "bank",
        counterparty: "银行供应商",
        tableValues: {
          counterparty: "银行供应商",
          amount: "6868.55",
          direction: "支出",
          paymentAccount: "建行 8106",
        },
      }),
    ],
    invoice: [
      buildRow({
        id: "invoice-001",
        recordType: "invoice",
        counterparty: "发票供应商",
        tableValues: {
          sellerName: "发票供应商",
          sellerTaxId: "91530000MA001",
          amount: "6868.55",
        },
      }),
    ],
  },
  processedExceptionSummary: {
    scenario: {
      label: "OA和支出流水一致，缺进项发票",
    },
    resolution: {
      action_label: "等待进项发票",
      note: "缺进项票，等待补票",
    },
  },
} as WorkbenchCandidateGroup & {
  processedExceptionSummary: Record<string, unknown>;
};

function buildRow(overrides: Partial<WorkbenchRecord>): WorkbenchRecord {
  return {
    id: "row",
    recordType: "oa",
    label: "测试记录",
    status: "追进项发票",
    statusCode: "wait_input_invoice",
    statusTone: "danger",
    exceptionHandled: true,
    amount: "0.00",
    counterparty: "--",
    tableValues: {},
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["cancel_exception"],
    ...overrides,
  };
}
