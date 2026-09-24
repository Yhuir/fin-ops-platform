import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchAnomalyIndicator from "../components/workbench/WorkbenchAnomalyIndicator";
import type { WorkbenchAnomalyItem } from "../features/workbench/types";

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
  bankOriginalTotal: "100.00",
  invoiceTotal: "99.00",
  evidenceTotal: "99.00",
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
    expect(await screen.findByRole("dialog")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("dismisses a hover popover on the first click and reopens it on the second click", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByRole("dialog")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.mouseEnter(trigger);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(trigger);
    expect(await screen.findByRole("dialog")).toBeVisible();
  });

  it("resets click dismissal after a genuine pointer leave", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByRole("dialog")).toBeVisible();
    await user.click(trigger);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.unhover(trigger);
    await user.hover(trigger);
    expect(await screen.findByRole("dialog")).toBeVisible();
  });

  it("shows on keyboard focus and closes with Escape", async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.tab();
    expect(await screen.findByRole("dialog")).toBeVisible();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.tab();
    await user.tab({ shift: true });
    expect(await screen.findByRole("dialog")).toBeVisible();
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

  it("renders only authoritative group amounts with an icon-only trigger", async () => {
    render(<WorkbenchAnomalyIndicator amountScope="group" levelLabel="该关联组" anomalies={[{
      ...anomaly, oaTotal: "1273.06", bankTotal: "1273.06", bankOriginalTotal: "1273.06", invoiceTotal: "1139.63", evidenceTotal: "1279.63",
      reviewDecision: "accept_paired", reviewedByAccount: "ACCOUNT", reviewNote: "说明",
      expenseItemDifferences: [{ expenseItemIds: ["item"], oaTotal: "182.44", evidenceTotal: "189.01", amountDelta: "6.57" }],
    }]} />);
    const trigger = screen.getByRole("button");
    expect(trigger).toHaveTextContent("");
    await userEvent.setup({ skipHover: true }).click(trigger);
    expect(screen.getByRole("dialog").textContent).toBe("OA1273.06银行流水1273.06票据凭证1279.63");
  });

  it("uses item evidence for a precisely located row without showing group amounts", async () => {
    render(<WorkbenchAnomalyIndicator levelLabel="该付款项" anomalies={[{
      ...anomaly, expenseItemDifferences: [{ expenseItemIds: ["item"], oaTotal: "182.44", evidenceTotal: "189.01", amountDelta: "6.57" }],
    }]} />);
    await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
    expect(screen.getByRole("dialog").textContent).toBe("OA182.44票据凭证189.01");
  });

  it("preserves independent shared-item comparisons when total differences cancel out", async () => {
    render(<WorkbenchAnomalyIndicator amountScope="group" levelLabel="该关联组" anomalies={[{
      ...anomaly, code: "expense_item_amount_mismatch", amountDelta: "0.00", evidenceTotal: "100.00",
      expenseItemDifferences: [
        { expenseItemIds: ["item-1", "item-2"], oaTotal: "40.00", evidenceTotal: "0.00", amountDelta: "40.00" },
        { expenseItemIds: ["item-3"], oaTotal: "60.00", evidenceTotal: "100.00", amountDelta: "-40.00" },
      ],
    }]} />);
    await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
    expect(Array.from(screen.getByRole("dialog").querySelectorAll("dl"), node => node.textContent)).toEqual([
      "OA40.00票据凭证0.00", "OA60.00票据凭证100.00",
    ]);
  });

  it("does not replace unknown evidence with formal invoices or zero, or remove a party", async () => {
    render(<WorkbenchAnomalyIndicator levelLabel="该关联组" anomalies={[
      { ...anomaly, fingerprint: "unknown", evidenceTotal: undefined, bankTotal: undefined, bankOriginalTotal: undefined },
      { ...anomaly, fingerprint: "zero", evidenceTotal: "0.00" },
    ]} />);
    await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
    expect(Array.from(screen.getByRole("dialog").querySelectorAll("dl"), node => node.textContent)).toEqual([
      "OA100.00银行流水—票据凭证—", "OA100.00银行流水100.00票据凭证0.00",
    ]);
  });

  it("keeps document resolution disabled for read-only users", async () => {
    const onPress = vi.fn();
    render(<WorkbenchAnomalyIndicator levelLabel="该发票" anomalies={[{
      ...anomaly, code: "oa_invoice_attachment_unassigned", displayLabel: "发票待归属",
    }]} action={{ label: "选择 OA 明细", disabled: true, disabledReason: "当前账号无归属权限", onPress }} />);
    await userEvent.setup({ skipHover: true }).click(screen.getByRole("button"));
    expect(screen.getByText("发票待归属")).toBeVisible();
    expect(screen.getByRole("button", { name: "选择 OA 明细" })).toBeDisabled();
    expect(onPress).not.toHaveBeenCalled();
  });
});


it("distinguishes original bank total from the actual related child amount", async () => {
  const user = userEvent.setup({ skipHover: true });
  render(<WorkbenchAnomalyIndicator anomalies={[{
    ...anomaly, oaTotal: "1001497.22", bankOriginalTotal: "1001497.22",
    bankTotal: "1497.22", bankRelatedTotal: "1497.22", evidenceTotal: "1497.22",
  }]} levelLabel="该关系" />);
  await user.click(screen.getByRole("button", { name: "该关系有 1 项异常，查看详情" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog.querySelector("dl")).toHaveTextContent("银行流水1001497.22本次关联1497.22");
});

it("does not call a purpose-only comparison a partial bank association", async () => {
  const user = userEvent.setup({ skipHover: true });
  render(<WorkbenchAnomalyIndicator anomalies={[{
    ...anomaly, bankOriginalTotal: "1001497.22", bankRelatedTotal: "1001497.22",
    bankTotal: "1497.22", evidenceTotal: "1400.00",
  }]} levelLabel="该关系" />);
  await user.click(screen.getByRole("button", { name: "该关系有 1 项异常，查看详情" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("银行流水1001497.22");
  expect(dialog).not.toHaveTextContent("本次关联");
});
