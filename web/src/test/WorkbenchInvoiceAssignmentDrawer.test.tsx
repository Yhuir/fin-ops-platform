import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import WorkbenchInvoiceAssignmentDrawer from "../components/workbench/WorkbenchInvoiceAssignmentDrawer";
import { assignWorkbenchInvoiceExpenseItems } from "../features/workbench/api";
import type { WorkbenchInvoiceExpenseItemAssignmentTarget } from "../features/workbench/types";

vi.mock("../features/workbench/api", async () => {
  const actual = await vi.importActual<typeof import("../features/workbench/api")>("../features/workbench/api");
  return {
    ...actual,
    assignWorkbenchInvoiceExpenseItems: vi.fn(),
  };
});

const target: WorkbenchInvoiceExpenseItemAssignmentTarget = {
  caseId: "CASE-1",
  invoiceRowId: "invoice-27.05",
  invoiceNo: "2653700000268955191",
  sellerName: "云南天谷科技开发有限公司",
  amount: "27.05",
  anomalyFingerprint: "a".repeat(64),
  idempotencyKey: "assignment-stable-1",
  candidates: [
    {
      key: "oa-1:item-2",
      oaRowId: "oa-1",
      oaLabel: "日常报销 OA-1",
      expenseItemId: "item-2",
      rowIndex: "2",
      projectName: "项目乙",
      amount: "39.95",
      expenseType: "住宿费",
    },
    {
      key: "oa-1:item-1",
      oaRowId: "oa-1",
      oaLabel: "日常报销 OA-1",
      expenseItemId: "item-1",
      rowIndex: "1",
      projectName: "项目甲",
      amount: "27.05",
      expenseType: "交通费",
    },
  ],
};

afterEach(() => vi.clearAllMocks());

describe("WorkbenchInvoiceAssignmentDrawer", () => {
  test("starts unselected, supports explicit multi-selection, and rereads once after the command", async () => {
    const user = userEvent.setup();
    const onCompleted = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    vi.mocked(assignWorkbenchInvoiceExpenseItems).mockResolvedValue(undefined);

    render(
      <WorkbenchInvoiceAssignmentDrawer
        open
        target={target}
        onClose={onClose}
        onCompleted={onCompleted}
      />,
    );

    const confirmButton = screen.getByRole("button", { name: "确认归属" });
    expect(screen.getByText("尚未选择")).toBeInTheDocument();
    expect(confirmButton).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "项目乙，39.95，住宿费 · 明细 2" })).not.toBeChecked();

    await user.click(screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" }));
    await user.click(screen.getByRole("checkbox", { name: "项目乙，39.95，住宿费 · 明细 2" }));
    expect(screen.getByText("已选 2 项")).toBeInTheDocument();
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);

    await waitFor(() => {
      expect(assignWorkbenchInvoiceExpenseItems).toHaveBeenCalledWith({
        caseId: "CASE-1",
        invoiceRowId: "invoice-27.05",
        targets: [
          { oaRowId: "oa-1", expenseItemId: "item-1" },
          { oaRowId: "oa-1", expenseItemId: "item-2" },
        ],
        anomalyFingerprint: "a".repeat(64),
        idempotencyKey: "assignment-stable-1",
      });
      expect(onCompleted).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  test("reuses an idempotency key for the same normalized selection and rotates it after a change", async () => {
    const user = userEvent.setup();
    const onCompleted = vi.fn();
    const onClose = vi.fn();
    vi.mocked(assignWorkbenchInvoiceExpenseItems).mockRejectedValue(new Error("write failed"));

    render(
      <WorkbenchInvoiceAssignmentDrawer
        open
        target={target}
        onClose={onClose}
        onCompleted={onCompleted}
      />,
    );

    const firstItem = screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" });
    const secondItem = screen.getByRole("checkbox", { name: "项目乙，39.95，住宿费 · 明细 2" });
    await user.click(firstItem);
    await user.click(screen.getByRole("button", { name: "确认归属" }));
    await screen.findByText("write failed");
    await user.click(screen.getByRole("button", { name: "确认归属" }));
    await waitFor(() => expect(assignWorkbenchInvoiceExpenseItems).toHaveBeenCalledTimes(2));

    expect(vi.mocked(assignWorkbenchInvoiceExpenseItems).mock.calls.map(([payload]) => payload.idempotencyKey))
      .toEqual(["assignment-stable-1", "assignment-stable-1"]);

    await user.click(firstItem);
    await user.click(secondItem);
    await user.click(screen.getByRole("button", { name: "确认归属" }));
    await waitFor(() => expect(assignWorkbenchInvoiceExpenseItems).toHaveBeenCalledTimes(3));

    const changedPayload = vi.mocked(assignWorkbenchInvoiceExpenseItems).mock.calls[2]?.[0];
    expect(changedPayload?.targets).toEqual([{ oaRowId: "oa-1", expenseItemId: "item-2" }]);
    expect(changedPayload?.idempotencyKey).not.toBe("assignment-stable-1");
    expect(onCompleted).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  test("locks the committed selection and retries only the canonical reread", async () => {
    const user = userEvent.setup();
    const onCompleted = vi.fn()
      .mockRejectedValueOnce(new Error("canonical reread failed"))
      .mockResolvedValueOnce(undefined);
    const onClose = vi.fn();
    vi.mocked(assignWorkbenchInvoiceExpenseItems).mockResolvedValue(undefined);

    render(
      <WorkbenchInvoiceAssignmentDrawer
        open
        target={target}
        onClose={onClose}
        onCompleted={onCompleted}
      />,
    );

    await user.click(screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" }));
    await user.click(screen.getByRole("button", { name: "确认归属" }));

    expect(await screen.findByText("canonical reread failed")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "项目甲，27.05，交通费 · 明细 1" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "项目乙，39.95，住宿费 · 明细 2" })).toBeDisabled();
    expect(screen.getByText("归属已保存，等待刷新")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "重试刷新结果" }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(assignWorkbenchInvoiceExpenseItems).toHaveBeenCalledTimes(1);
    expect(onCompleted).toHaveBeenCalledTimes(2);
  });

  test("distinguishes same-project same-amount candidates with existing expense details", () => {
    render(
      <WorkbenchInvoiceAssignmentDrawer
        open
        target={{
          ...target,
          candidates: [
            {
              ...target.candidates[0]!,
              projectName: "同一项目",
              amount: "27.05",
              expenseType: "交通费",
              feeContent: "高铁票",
              feeDescription: "昆明出差",
              rowIndex: "1",
            },
            {
              ...target.candidates[1]!,
              projectName: "同一项目",
              amount: "27.05",
              expenseType: "交通费",
              feeContent: "出租车",
              feeDescription: "机场返回",
              rowIndex: "2",
            },
          ],
        }}
        onClose={() => undefined}
        onCompleted={() => undefined}
      />,
    );

    expect(screen.getByRole("checkbox", {
      name: "同一项目，27.05，交通费 · 高铁票 · 昆明出差 · 明细 1",
    })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", {
      name: "同一项目，27.05，交通费 · 出租车 · 机场返回 · 明细 2",
    })).toBeInTheDocument();
    expect(screen.getByText("交通费 · 高铁票 · 昆明出差 · 明细 1")).toBeVisible();
    expect(screen.getByText("交通费 · 出租车 · 机场返回 · 明细 2")).toBeVisible();
  });
});
