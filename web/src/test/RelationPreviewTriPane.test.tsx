import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import RelationPreviewTriPane from "../components/workbench/RelationPreviewTriPane";
import type {
  WorkbenchRecord,
  WorkbenchRelationGroup,
} from "../features/workbench/types";

function row(
  id: string,
  recordType: WorkbenchRecord["recordType"],
  overrides: Partial<WorkbenchRecord> = {},
): WorkbenchRecord {
  return {
    id,
    recordType,
    label: id,
    status: "",
    statusCode: "",
    statusTone: "",
    exceptionHandled: false,
    amount: "100.00",
    counterparty: "贷款户",
    detailFields: [],
    actionVariant: "none",
    availableActions: [],
    tableValues: {
      applicant: "申请人",
      projectName: "项目",
      amount: "100.00",
      transactionTime: "2026-04-29",
      direction: "支出",
      paymentAccount: "民生银行 9486",
      sellerName: "销方",
      sellerTaxId: "913000000000000001",
      buyerName: "购方",
      buyerTaxId: "913000000000000002",
      grossAmount: "100.00",
      taxRate: "6%",
      taxAmount: "5.66",
    },
    ...overrides,
  };
}
function group(id: string, rows: WorkbenchRecord[]): WorkbenchRelationGroup {
  return {
    id,
    groupType: "paired",
    rawGroupType: "paired",
    matchConfidence: "high",
    reason: "",
    rows: {
      oa: rows.filter((r) => r.recordType === "oa"),
      bank: rows.filter((r) => r.recordType === "bank"),
      invoice: rows.filter((r) => r.recordType === "invoice"),
    },
  };
}
function preview(groups: WorkbenchRelationGroup[]) {
  return (
    <RelationPreviewTriPane
      side="before"
      title="操作前"
      testId="before"
      groups={groups}
      totals={{ oaTotal: "100", bankTotal: "100", invoiceTotal: "100" }}
      status="matched"
      mismatchFields={[]}
    />
  );
}

describe("compact relation preview", () => {
  test("uses one payment chip for direction and original money, and chips for unsplit categories", () => {
    render(preview([group("payment", [row("bank", "bank", {
      amount: "8000.00", categoryLabelPath: ["货款", "设备采购"],
    })])]));
    const payment = screen.getByText("8000.00").closest(".chip");
    expect(payment).toHaveTextContent("支8000.00");
    expect(screen.getByText("货款 / 设备采购").closest(".chip")).not.toBeNull();
    expect(screen.getByText("民生", { exact: true }).closest(".bank-account-tag")).not.toBeNull();
  });
  test("keeps reordered unchanged groups in their bands while separating adjacent groups", () => {
    const a = group("a", [row("oa-a", "oa")]), b = group("b", [row("oa-b", "oa")]);
    const renderAfter = (groups: WorkbenchRelationGroup[]) => <RelationPreviewTriPane
      title="操作后" side="after" groups={groups} referenceGroups={[a,b]}
      totals={{oaTotal:"200",bankTotal:"0",invoiceTotal:"0"}} mismatchFields={[]} />;
    const view = render(renderAfter([b,a]));
    expect(screen.getByTestId("candidate-group-b")).toHaveAttribute("data-band", "1");
    expect(screen.getByTestId("candidate-group-a")).toHaveAttribute("data-band", "0");
    view.rerender(renderAfter([group("new", []),a,b]));
    expect(screen.getByTestId("candidate-group-new")).toHaveAttribute("data-band", "1");
    expect(screen.getByTestId("candidate-group-a")).toHaveAttribute("data-band", "0");
    expect(screen.getByTestId("candidate-group-b")).toHaveAttribute("data-band", "1");
  });
  test("renders exact before and after groups without altering members", () => {
    const a = row("oa", "oa"),
      b = row("bank", "bank"),
      c = row("invoice", "invoice");
    const before = [group("ab", [a, b]), group("c", [c])];
    const snapshot = JSON.stringify(before);
    render(
      <>
        {preview(before)}
        <RelationPreviewTriPane
          side="after"
          title="操作后"
          testId="after"
          groups={[group("abc", [a, b, c])]}
          totals={{ oaTotal: "100", bankTotal: "100", invoiceTotal: "100" }}
          status="matched"
          mismatchFields={[]}
        />
      </>,
    );
    expect(
      within(screen.getByTestId("before")).getAllByRole("rowgroup"),
    ).toHaveLength(2);
    expect(
      within(screen.getByTestId("after")).getAllByRole("rowgroup"),
    ).toHaveLength(1);
    expect(
      screen
        .getByTestId("candidate-group-ab")
        .querySelectorAll("[data-member-ids]"),
    ).toHaveLength(2);
    expect(
      screen
        .getByTestId("candidate-group-abc")
        .querySelectorAll("[data-member-ids]"),
    ).toHaveLength(3);
    expect(JSON.stringify(before)).toBe(snapshot);
  });
  test("keeps explicit subgroups aligned and a shared invoice spanning both", () => {
    const g = group("segments", [
      row("a", "oa"),
      row("b", "oa"),
      row("x", "bank"),
      row("y", "bank"),
      row("i", "invoice"),
    ]);
    g.displaySubgroups = [
      { oaRowIds: ["a"], bankRowIds: ["x"] },
      { oaRowIds: ["b"], bankRowIds: ["y"] },
    ];
    render(preview([g]));
    const cells = screen.getByTestId("candidate-group-segments");
    expect(
      cells.querySelector('[data-member-ids="a"]')?.parentElement?.style
        .gridRow,
    ).toBe("1");
    expect(
      cells.querySelector('[data-member-ids="x"]')?.parentElement?.style
        .gridRow,
    ).toBe("1");
    expect(
      cells.querySelector('[data-member-ids="y"]')?.parentElement?.style
        .gridRow,
    ).toBe("2");
    expect(cells.querySelector('[data-pane="invoice"]')).toHaveStyle({
      gridRow: "1 / span 2",
    });
    expect(cells.querySelectorAll('[data-member-ids="i"]')).toHaveLength(1);
  });
  test("does not invent row pairs for an ambiguous many-to-many group", () => {
    render(
      preview([
        group("ambiguous", [
          row("a", "oa", { amount: "400" }),
          row("b", "oa", { amount: "600" }),
          row("x", "bank", { amount: "800" }),
          row("y", "bank", { amount: "200" }),
        ]),
      ]),
    );
    const g = screen.getByTestId("candidate-group-ambiguous");
    expect(g.querySelectorAll("[data-segment]")).toHaveLength(0);
    expect(
      g.querySelectorAll('[data-pane="oa"] [data-member-ids]'),
    ).toHaveLength(2);
    expect(
      g.querySelectorAll('[data-pane="bank"] [data-member-ids]'),
    ).toHaveLength(2);
  });
  test("keeps split parent money and only the exact member tags in each group", () => {
    const parts = [
      {
        id: "principal",
        amount: "1000000.00",
        category_code: "loan",
        category_label: "归还借款",
        category_path: ["外部往来款付款", "归还借款"],
      },
      {
        id: "interest",
        amount: "1497.22",
        category_code: "interest",
        category_label: "利息",
        category_path: ["费用", "利息"],
      },
    ];
    const a = row("principal", "bank", {
      amount: "1000000.00",
      isSplit: true,
      parentRowId: "parent",
      parentAmount: "1001497.22",
      bankSplitParts: parts,
    });
    const b = { ...a, id: "interest", amount: "1497.22" };
    render(
      preview([group("principal-case", [a]), group("interest-case", [b])]),
    );
    const interest = screen.getByTestId("candidate-group-interest-case");
    expect(within(interest).getByText("1001497.22")).toBeInTheDocument();
    expect(within(interest).queryByText(/本次关联/)).not.toBeInTheDocument();
    expect(
      within(interest).queryByRole("button", { name: /归还借款拆分金额/ }),
    ).not.toBeInTheDocument();
    expect(
      within(interest).getByRole("button", { name: "费用 / 利息拆分金额" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("pane-bank")).getByText("1 笔"),
    ).toBeInTheDocument();
  });
  test("keeps secondary invoice fields in details without manufacturing tax values", async () => {
    const view = render(preview([]));
    expect(screen.queryByRole("rowgroup")).not.toBeInTheDocument();
    expect(screen.getByText("暂无记录")).toBeInTheDocument();
    view.rerender(
      preview([
        group("tax", [
          row("i", "invoice", {
            tableValues: {
              sellerName: "同一销方",
              sellerTaxId: "913000000000000001",
              buyerName: "同一购方",
              buyerTaxId: "913000000000000002",
              grossAmount: "100.00",
              amount: "—",
              taxRate: "免税",
              taxAmount: "—",
            },
          }),
        ]),
      ]),
    );
    expect(screen.queryByText(/不含税/)).not.toBeInTheDocument();
    expect(screen.queryByText("913000000000000002")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看发票详情" }));
    const details = await screen.findByRole("dialog", { name: "发票详情" });
    expect(within(details).getByText("913000000000000002")).toBeInTheDocument();
    expect(within(details).queryByText(/税额|不含税/)).not.toBeInTheDocument();
    expect(screen.getByTestId("candidate-group-tax").querySelector("[title]")).toBeNull();
    view.rerender(preview([]));
    expect(screen.queryByRole("dialog", { name: "发票详情" })).not.toBeInTheDocument();
  });
  test("keeps all 500 distinct members even when their names and amounts match", () => {
    render(
      preview([
        group(
          "large",
          Array.from({ length: 500 }, (_, i) => row(`bank-${i}`, "bank")),
        ),
      ]),
    );
    expect(
      screen
        .getByTestId("candidate-group-large")
        .querySelectorAll("[data-member-ids]"),
    ).toHaveLength(500);
  });
});
