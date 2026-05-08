import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, test, vi } from "vitest";

import OaBankExceptionModal from "../components/workbench/OaBankExceptionModal";
import type { WorkbenchRecord } from "../features/workbench/types";

describe("OaBankExceptionModal", () => {
  test("summarizes bank debit and credit separately", () => {
    renderModal([
      buildRow({ id: "oa-1", recordType: "oa", amount: "300,000.00" }),
      buildRow({
        id: "bank-out-1",
        recordType: "bank",
        amount: "300,000.00",
        tableValues: { direction: "支出", debitAmount: "300,000.00", creditAmount: "—" },
      }),
      buildRow({
        id: "bank-in-1",
        recordType: "bank",
        amount: "200,000.00",
        tableValues: { direction: "收入", debitAmount: "—", creditAmount: "200,000.00" },
      }),
      buildRow({
        id: "bank-in-2",
        recordType: "bank",
        amount: "100,000.00",
        tableValues: { direction: "收入", debitAmount: "—", creditAmount: "100,000.00" },
      }),
    ]);

    const dialog = screen.getByRole("dialog", { name: "OA流水异常处理弹窗" });
    expect(within(dialog).getByText("OA合计")).toBeInTheDocument();
    expect(within(dialog).getByText("流水支出")).toBeInTheDocument();
    expect(within(dialog).getByText("流水收入")).toBeInTheDocument();
    expect(within(dialog).getByText("流水净额")).toBeInTheDocument();
    expect(within(dialog).getAllByText("300,000.00")).toHaveLength(3);
    expect(within(dialog).queryByText("600,000.00")).not.toBeInTheDocument();
  });

  test("settlement option calls settle callback", async () => {
    const user = userEvent.setup();
    const onSettleAsPair = vi.fn();
    renderModal(
      [
        buildRow({ id: "oa-1", recordType: "oa", amount: "300,000.00" }),
        buildRow({ id: "bank-out-1", recordType: "bank", amount: "300,000.00", tableValues: { direction: "支出" } }),
        buildRow({ id: "bank-in-1", recordType: "bank", amount: "300,000.00", tableValues: { direction: "收入" } }),
      ],
      { onSettleAsPair },
    );

    await user.selectOptions(screen.getByLabelText("异常情况"), "personal_advance_repayment_settlement");
    await user.type(screen.getByLabelText("备注"), "已确认闭环");
    await user.click(screen.getByRole("button", { name: "确认闭环" }));

    expect(onSettleAsPair).toHaveBeenCalledWith({ comment: "已确认闭环" });
  });
});

function renderModal(
  rows: WorkbenchRecord[],
  overrides: Partial<ComponentProps<typeof OaBankExceptionModal>> = {},
) {
  return render(
    <OaBankExceptionModal
      rows={rows}
      onClose={() => undefined}
      onConfirmLink={() => undefined}
      onSettleAsPair={() => undefined}
      onSubmitException={() => undefined}
      {...overrides}
    />,
  );
}

function buildRow(overrides: Partial<WorkbenchRecord>): WorkbenchRecord {
  return {
    id: "row",
    recordType: "oa",
    label: "row",
    status: "待处理",
    statusCode: "pending",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "0.00",
    counterparty: "counterparty",
    tableValues: {},
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: [],
    ...overrides,
  };
}
