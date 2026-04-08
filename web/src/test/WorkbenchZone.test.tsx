import { act, fireEvent, render, screen } from "@testing-library/react";

import WorkbenchZone from "../components/workbench/WorkbenchZone";

const panes = [
  {
    id: "oa",
    title: "OA",
    rows: [
      {
        id: "OA-001",
        recordType: "oa",
        label: "付款申请",
        status: "完全关联",
        amount: "128,000.00",
        counterparty: "华东设备供应商",
        actionVariant: "detail-only",
        tableValues: {
          applicant: "赵华",
          projectName: "华东改造项目",
          applicationType: "供应商付款申请",
          amount: "128,000.00",
          counterparty: "华东设备供应商",
          reason: "设备首付款支付",
          reconciliationStatus: "完全关联",
        },
        detailFields: [],
      },
    ],
  },
  {
    id: "bank",
    title: "银行流水",
    rows: [
      {
        id: "BNK-001",
        recordType: "bank",
        label: "支取",
        status: "完全关联",
        amount: "128,000.00",
        counterparty: "华东设备供应商",
        actionVariant: "bank-review",
        tableValues: {
          direction: "支出",
          transactionTime: "2026-03-25 14:22",
          amount: "128,000.00",
          debitAmount: "128,000.00",
          creditAmount: "--",
          counterparty: "华东设备供应商",
          paymentAccount: "招商银行 9123",
          invoiceRelationStatus: "完全关联",
          paymentOrReceiptTime: "2026-03-25 14:22",
          note: "设备采购款",
          loanRepaymentDate: "--",
        },
        detailFields: [],
      },
    ],
  },
  {
    id: "invoice",
    title: "进销项发票",
    rows: [
      {
        id: "INV-001",
        recordType: "invoice",
        label: "销项票",
        status: "已核销",
        amount: "128,000.00",
        counterparty: "华东项目甲方",
        actionVariant: "detail-only",
        tableValues: {
          sellerTaxId: "91310000MA1K8A001X",
          sellerName: "溯源科技有限公司",
          buyerTaxId: "91310110MA1F99088Q",
          buyerName: "华东项目甲方",
          issueDate: "2026-03-25",
          amount: "128,000.00",
          taxRate: "13%",
          taxAmount: "16,640.00",
          grossAmount: "144,640.00",
          invoiceType: "数电专票",
        },
        detailFields: [],
      },
    ],
  },
];

function dispatchMouseEvent(target: EventTarget, type: string, clientX: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX });
  Object.defineProperty(event, "clientX", {
    configurable: true,
    value: clientX,
  });
  target.dispatchEvent(event);
}

describe("WorkbenchZone", () => {
  test("collapses and restores panes per zone without affecting splitter count rules", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        meta="自动闭环与人工确认后的记录"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="paired"
      />,
    );

    expect(screen.getAllByRole("separator")).toHaveLength(2);
    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "银行流水" }));

    expect(screen.queryByTestId("pane-bank")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "OA" }));

    expect(screen.queryByTestId("pane-oa")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("separator")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "银行流水" }));

    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();
    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  test("dragging a splitter can collapse a pane to zero width", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="未配对"
        tone="warning"
        meta="等待人工处理"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="open"
      />,
    );

    const triPane = screen.getByTestId("tri-pane");
    Object.defineProperty(triPane, "clientWidth", {
      configurable: true,
      value: 1000,
    });

    const firstSplitter = screen.getAllByRole("separator")[0];
    act(() => {
      dispatchMouseEvent(firstSplitter, "mousedown", 320);
    });
    act(() => {
      dispatchMouseEvent(window, "mousemove", -40);
      dispatchMouseEvent(window, "mouseup", -40);
    });

    expect(screen.queryByTestId("pane-oa")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  test("shows an expand toggle in the zone header", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        title="未配对"
        tone="warning"
        meta="等待人工处理"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        panes={panes}
        isExpanded={false}
        isVisible
        onToggleExpand={() => {}}
        zoneId="open"
      />,
    );

    expect(screen.getByRole("button", { name: "放大 未配对" })).toBeInTheDocument();
  });
});
