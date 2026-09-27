import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import BankFlowBatchWithdrawPreview from "../components/workbench/BankFlowBatchWithdrawPreview";
import { fetchBankFlowRuleBatchDetail } from "../features/bankFlowRuleBatches/api";
import type { BankFlowRuleBatchDetail } from "../features/bankFlowRuleBatches/types";

vi.mock("../features/bankFlowRuleBatches/api", () => ({ fetchBankFlowRuleBatchDetail: vi.fn() }));

const detail = {
  batch: { batchId: "batch-1", batchLabel: "费用", version: 7, status: "submitted", canWithdraw: true, totalAmount: "20.00" },
  rows: [{ transactionId: "bank-1", amount: "20.00", counterpartyName: "测试商户", tradeTime: "2026-09-27", directionLabel: "支出", summary: "手续费" }],
} as BankFlowRuleBatchDetail;

beforeEach(() => { vi.mocked(fetchBankFlowRuleBatchDetail).mockReset().mockResolvedValue(detail); });

test("reads formal members, cancelling the preview never submits", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  const onSubmit = vi.fn();
  render(<BankFlowBatchWithdrawPreview batchId="batch-1" onClose={onClose} onSubmit={onSubmit} />);
  expect(await screen.findByText("测试商户")).toBeInTheDocument();
  expect(fetchBankFlowRuleBatchDetail).toHaveBeenCalledWith("batch-1", undefined, "formal", expect.any(AbortSignal));
  await user.click(screen.getByRole("button", { name: "关闭关联预览" }));
  expect(onClose).toHaveBeenCalledOnce();
  expect(onSubmit).not.toHaveBeenCalled();
});

test("confirmation uses the preview version and blocks repeated submits", async () => {
  const user = userEvent.setup();
  let finish!: () => void;
  const onSubmit = vi.fn((_version: number, committed: () => void) => new Promise<void>(resolve => {
    finish = () => { committed(); resolve(); };
  }));
  render(<BankFlowBatchWithdrawPreview batchId="batch-1" onClose={vi.fn()} onSubmit={onSubmit} />);
  await screen.findByText("测试商户");
  await user.dblClick(screen.getByRole("button", { name: "确认撤回" }));
  expect(onSubmit).toHaveBeenCalledOnce();
  expect(onSubmit).toHaveBeenCalledWith(7, expect.any(Function));
  expect(screen.getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
  await act(async () => finish());
  expect(await screen.findByRole("status")).toHaveTextContent("关联操作已完成");
  expect(screen.queryByRole("button", { name: "确认撤回" })).not.toBeInTheDocument();
});

test.each(["读取失败", "没有权限读取批次"])("read failure remains visible without a write: %s", async message => {
  vi.mocked(fetchBankFlowRuleBatchDetail).mockRejectedValue(new Error(message));
  const onSubmit = vi.fn();
  render(<BankFlowBatchWithdrawPreview batchId="batch-1" onClose={vi.fn()} onSubmit={onSubmit} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("button", { name: "确认撤回" })).toBeDisabled();
  expect(onSubmit).not.toHaveBeenCalled();
});

test.each([false, true])("submission error prevents reuse of the preview, committed=%s", async committed => {
  const user = userEvent.setup();
  const onSubmit = vi.fn(async (_version: number, markCommitted: () => void) => {
    if (committed) markCommitted();
    throw new Error(committed ? "页面读取失败" : "版本冲突");
  });
  render(<BankFlowBatchWithdrawPreview batchId="batch-1" onClose={vi.fn()} onSubmit={onSubmit} />);
  await screen.findByText("测试商户");
  await user.click(screen.getByRole("button", { name: "确认撤回" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(committed ? "撤回已提交" : "版本冲突");
  expect(screen.getByRole("button", { name: "确认撤回" })).toBeDisabled();
});

test("closing while loading aborts the detail read", async () => {
  vi.mocked(fetchBankFlowRuleBatchDetail).mockReturnValue(new Promise(() => {}));
  const { unmount } = render(<BankFlowBatchWithdrawPreview batchId="batch-1" onClose={vi.fn()} onSubmit={vi.fn()} />);
  await waitFor(() => expect(fetchBankFlowRuleBatchDetail).toHaveBeenCalledOnce());
  const signal = vi.mocked(fetchBankFlowRuleBatchDetail).mock.calls[0][3]!;
  unmount();
  expect(signal.aborted).toBe(true);
});
