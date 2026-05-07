import { render, screen } from "@testing-library/react";

import DetailDrawer from "../components/workbench/DetailDrawer";
import type { WorkbenchRecord } from "../features/workbench/types";

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
      { label: "明细摘要", value: "交通费 800.00；住宿费 749.00" },
      { label: "明细金额合计", value: "1,549.00" },
      { label: "费用内容摘要", value: "项目现场交通；项目住宿" },
      { label: "附件发票摘要", value: "滴滴出行发票 800.00；酒店发票 749.00" },
      { label: "金额差异", value: "主表 1,549.00；明细合计 1,548.99；差异 0.01" },
    ],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

describe("DetailDrawer", () => {
  test("shows aggregated OA detail fields", () => {
    render(<DetailDrawer row={buildOaRow()} loading={false} error={null} onClose={() => undefined} />);

    expect(screen.getByRole("dialog", { name: "详情弹窗" })).toBeInTheDocument();
    expect(screen.getByText("明细摘要")).toBeInTheDocument();
    expect(screen.getByText("交通费 800.00；住宿费 749.00")).toBeInTheDocument();
    expect(screen.getByText("费用内容摘要")).toBeInTheDocument();
    expect(screen.getByText("项目现场交通；项目住宿")).toBeInTheDocument();
    expect(screen.getByText("附件发票摘要")).toBeInTheDocument();
    expect(screen.getByText("滴滴出行发票 800.00；酒店发票 749.00")).toBeInTheDocument();
    expect(screen.getByText("明细金额合计")).toBeInTheDocument();
    expect(screen.getByText("金额差异")).toBeInTheDocument();
  });
});
