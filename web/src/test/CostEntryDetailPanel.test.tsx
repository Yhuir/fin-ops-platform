import { render, screen, within } from "@testing-library/react";

import CostEntryDetailPanel from "../components/cost-statistics/CostEntryDetailPanel";
import type { CostAllocationDetail } from "../features/cost-statistics/types";

test("shows net allocation and paid-wrong refund as negative drawer evidence", () => {
  const detail: CostAllocationDetail = {
    month: "2026-08",
    kind: "oa_allocation",
    allocation: {
      allocationId: "bank:bank-1050:oa:oa-exp-1:item:lodging",
      oaId: "oa-exp-1",
      oaApplyType: "日常报销",
      expenseItemId: "lodging",
      oaCompletedAt: "2026-07-23 18:00:00",
      projectName: "大理卷烟厂余热综合利用项目",
      projectId: "project-dali",
      expenseType: "住宿费",
      expenseContent: "住宿费（25.11.24-26.05.02）",
      amount: "710.00",
      counterpartyName: "杨丽萍",
      paymentAccountLabel: "建设银行 8106",
      oaApplicant: "杨丽萍",
      oaOriginalAmount: "710.00",
      oaAllocationWeight: "69.95%",
      bankEventAmount: "1050.00",
    },
    paymentEvidence: [
      {
        transactionId: "bank-1050",
        tradeTime: "2026-08-01 15:58:31",
        amount: "1050.00",
        direction: "支出",
        counterpartyName: "杨丽萍",
        paymentAccountLabel: "建设银行 8106",
        remark: "报销",
        bankTagCode: "employee-reimbursement",
        bankTagLabel: "员工报销",
      },
      {
        transactionId: "bank-refund-35",
        tradeTime: "2026-08-01 16:22:04",
        amount: "35.00",
        direction: "收入",
        counterpartyName: "杨丽萍",
        paymentAccountLabel: "建设银行 8106",
        remark: "退报销多转款",
        bankTagCode: "paid-wrong-refund",
        bankTagLabel: "付错退款",
      },
    ],
    reconciliation: {
      relationCaseId: "case-1",
      oaAllocationTotal: "1015.00",
      bankOutflowTotal: "1050.00",
      paidWrongRefundTotal: "35.00",
      netCashCost: "1015.00",
      difference: "0.00",
      cashPaymentRatio: "100.00%",
      status: "balanced",
    },
  };

  render(<CostEntryDetailPanel detail={detail} />);

  const basic = screen.getByRole("grid", { name: "基本信息详情" });
  expect(within(basic).getByText("本项净成本")).toBeInTheDocument();
  expect(within(basic).getAllByText("710.00")).toHaveLength(2);
  expect(within(basic).getByText("本笔支出流水原额")).toBeInTheDocument();
  expect(within(basic).getByText("1050.00")).toBeInTheDocument();

  const reconciliation = screen.getByRole("grid", { name: "金额核对详情" });
  expect(within(reconciliation).getByText("关系净支出")).toBeInTheDocument();
  expect(within(reconciliation).getByText("付错退款")).toBeInTheDocument();
  expect(within(reconciliation).getByText("-35.00")).toBeInTheDocument();

  const refundEvidence = screen.getByRole("grid", { name: "关系内银行流水 2详情" });
  expect(within(refundEvidence).getByText("付错退款金额")).toBeInTheDocument();
  expect(within(refundEvidence).getByText("-35.00")).toBeInTheDocument();
  expect(within(refundEvidence).getByText("退报销多转款")).toBeInTheDocument();
});
