import { render, screen } from "@testing-library/react";

import DetailDrawer from "../components/workbench/DetailDrawer";
import type { WorkbenchRecord } from "../features/workbench/types";

vi.mock("../features/bankSplits/BankSplitEditor", () => ({ default: () => <div>拆分编辑器</div> }));

function buildOaRow(): WorkbenchRecord {
  return {
    id: "oa-exp-1994",
    caseId: "CASE-202603-OA-AGG",
    recordType: "oa",
    label: "日常报销",
    status: "待找流水与发票",
    statusCode: "pending_match",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "1,549.00",
    counterparty: "张敏",
    tableValues: {
      applicant: "张敏",
      applicationTime: "2026-03-20 10:00",
      projectName: "现场报销项目",
      applicationType: "日常报销",
      amount: "1,549.00",
      counterparty: "张敏",
      reason: "聚合报销单",
      reconciliationStatus: "待找流水与发票",
    },
    detailFields: [
      { label: "申请人", value: "真实申请人" },
      { label: "流程状态", value: "completed" },
      { label: "申请时间", value: "2026-03-20" },
      { label: "备注", value: "normal (0123456789abcdef.pdf)" },
    ],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

describe("DetailDrawer", () => {
  test("shows source OA fields without modifying the original remark", () => {
    render(<DetailDrawer row={buildOaRow()} loading={false} error={null} onClose={() => undefined} />);

    expect(screen.getByRole("dialog", { name: "OA详情" })).toBeInTheDocument();
    expect(screen.getByText("真实申请人")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("2026-03-20")).toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "基本信息详情" })).toBeInTheDocument();
    expect(screen.getByText("normal (0123456789abcdef.pdf)")).toBeInTheDocument();
  });
});


test("OA detail exposes every expense including duplicate labels without exposing item identities", () => {
  const row = buildOaRow();
  row.expenseItems = ["299.00", "1.22"].map((amount, index) => ({
    id: `private-item-${index}`, rowIndex: String(index), projectName: "公司",
    amount, expenseContent: "设备报销", reimbursementDate: "2025-12-27",
    paymentMethod: "微信支付", invoiceKind: "普通发票/行政收据", ticketCount: index === 0 ? "34" : "0", attachmentFileCount: 0,
  }));
  render(<DetailDrawer row={row} loading={false} error={null} onClose={() => undefined} />);
  expect(screen.getByText("费用明细 1")).toBeInTheDocument();
  expect(screen.getByText("费用明细 2")).toBeInTheDocument();
  expect(screen.getAllByText("设备报销")).toHaveLength(2);
  expect(screen.getByText("299.00")).toBeInTheDocument();
  expect(screen.getByText("1.22")).toBeInTheDocument();
  expect(screen.getAllByText("票据张数")).toHaveLength(2);
  expect(screen.getByText("34")).toBeInTheDocument();
  expect(screen.queryByText("附件文件数")).not.toBeInTheDocument();
  expect(screen.getAllByText("微信支付")).toHaveLength(2);
  expect(screen.queryByText("private-item-0")).not.toBeInTheDocument();
});


test("does not render old list facts while detail loads or fails", () => {
  const { rerender } = render(<DetailDrawer row={buildOaRow()} loading error={null} onClose={() => undefined} />);
  expect(screen.queryByText("真实申请人")).not.toBeInTheDocument();
  expect(screen.getByLabelText("正在加载详情")).toBeInTheDocument();
  rerender(<DetailDrawer row={buildOaRow()} loading={false} error="来源读取失败" onClose={() => undefined} />);
  expect(screen.getByText("来源读取失败")).toBeInTheDocument();
  expect(screen.queryByText("真实申请人")).not.toBeInTheDocument();
});

test("bank source detail renders transaction date, amount and remark with splitting", () => {
  const row: WorkbenchRecord = { ...buildOaRow(), recordType: "bank", id: "bank-source", detailFields: [
    { label: "txn_date", value: "2026-09-27" },
    { label: "amount", value: "100.00" },
    { label: "remark", value: "normal" },
  ] };
  render(<DetailDrawer row={row} loading={false} error={null} onClose={() => undefined} />);
  expect(screen.queryByText("pending")).not.toBeInTheDocument();
  expect(screen.queryByText("状态")).not.toBeInTheDocument();
  expect(screen.queryByText("2026-09-27 00:00:00")).not.toBeInTheDocument();
  expect(screen.getByText("交易日期")).toBeInTheDocument();
  expect(screen.getByText("2026-09-27")).toBeInTheDocument();
  expect(screen.getByText("100.00")).toBeInTheDocument();
  expect(screen.getByText("normal")).toBeInTheDocument();
  expect(screen.getByText("拆分编辑器")).toBeInTheDocument();
});

test("invoice keeps its uploaded source status and zero tax", () => {
  const row: WorkbenchRecord = { ...buildOaRow(), recordType: "invoice", detailFields: [
    { label: "invoice_status_from_source", value: "正常" },
    { label: "tax_amount", value: "0" },
    { label: "invoice_no", value: "INV-SOURCE" },
  ] };
  render(<DetailDrawer row={row} loading={false} error={null} onClose={() => undefined} />);
  expect(screen.getByText("发票状态")).toBeInTheDocument();
  expect(screen.getByText("正常")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("INV-SOURCE")).toBeInTheDocument();
  expect(screen.queryByText("pending")).not.toBeInTheDocument();
  expect(screen.queryByText("input")).not.toBeInTheDocument();
});
