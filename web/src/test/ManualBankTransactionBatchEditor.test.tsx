import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import ManualBankTransactionBatchEditor from "../components/imports/ManualBankTransactionBatchEditor";
import type { ManualBankTransactionEntryBatchPreview } from "../features/imports/types";

const previewPayload: ManualBankTransactionEntryBatchPreview = {
  values: [{
    bankMappingId: "ccb-8106",
    bankName: "中国建设银行",
    bankShortName: "建行",
    last4: "8106",
    accountNo: "6227000012348106",
    accountName: "云南溯源科技有限公司",
    direction: "outflow",
    amount: "100.00",
    balance: "900.00",
    tradeTime: "2026-08-28T09:01:02",
    currency: "CNY",
    counterpartyName: "测试供应商",
    counterpartyAccountNo: "",
    counterpartyBankName: "",
    summary: "电子转账",
    remark: "人工录入",
    referenceFieldKey: "accountDetailNo",
    referenceFieldLabel: "账户明细编号-交易流水号",
    referenceValue: "CCB-UI-001",
  }],
  fileIds: ["manual_bank_file_1"],
  importSession: {
    session: {
      id: "manual_bank_session_1",
      importedBy: "web_finance_user",
      fileCount: 1,
      status: "preview_ready",
      createdAt: "2026-08-28T09:02:00+08:00",
    },
    files: [{
      id: "manual_bank_file_1",
      fileName: "新流水1",
      templateCode: "manual_bank_transaction_entry",
      batchType: "bank_transaction",
      status: "preview_ready",
      message: "预览成功",
      rowCount: 1,
      successCount: 1,
      errorCount: 0,
      duplicateCount: 0,
      suspectedDuplicateCount: 0,
      updatedCount: 0,
      mappingCandidates: [],
      mappingFields: [],
      fieldMapping: {},
      rowResults: [{
        id: "row-1",
        rowNo: 1,
        sourceRecordType: "bank_transaction",
        decision: "created",
        decisionReason: "Ready to create new bank transaction.",
        identityKind: "bank_strong",
        identityKey: "bank-v3:test",
        linkedObjectType: null,
        linkedObjectId: null,
        sourcePayload: {},
        normalizedPayload: {},
      }],
    }],
    duplicateGroups: [],
    affectedScopeKeys: [],
  },
};

describe("ManualBankTransactionBatchEditor", () => {
  test("derives the bank-specific reference field and submits one canonical preview batch", async () => {
    const user = userEvent.setup();
    const previewTransactions = vi.fn().mockResolvedValue(previewPayload);
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onPreviewSessionChange = vi.fn();
    render(
      <ManualBankTransactionBatchEditor
        bankAccounts={[{
          id: "ccb-8106",
          bankName: "中国建设银行",
          shortName: "建行",
          last4: "8106",
          manualEntryReferenceField: {
            key: "accountDetailNo",
            label: "账户明细编号-交易流水号",
          },
        }]}
        onCancel={vi.fn()}
        onPreviewSessionChange={onPreviewSessionChange}
        onSubmit={onSubmit}
        previewTransactions={previewTransactions}
      />,
    );

    await user.click(screen.getByLabelText("银行账户"));
    await user.click(await screen.findByRole("option", { name: "建行 8106" }));
    expect(screen.getByLabelText("账户明细编号-交易流水号")).toBeEnabled();
    fireEvent.change(screen.getByLabelText("本方完整账号"), { target: { value: "6227000012348106" } });
    fireEvent.change(screen.getByLabelText("账户明细编号-交易流水号"), { target: { value: "CCB-UI-001" } });
    fireEvent.change(screen.getByLabelText("金额"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("余额"), { target: { value: "900" } });
    fireEvent.change(screen.getByLabelText("交易时间"), { target: { value: "2026-08-28T09:01" } });
    fireEvent.change(screen.getByLabelText("对方户名"), { target: { value: "测试供应商" } });
    await user.click(screen.getByRole("button", { name: "预览 1 笔流水" }));

    await waitFor(() => expect(previewTransactions).toHaveBeenCalledWith([
      expect.objectContaining({
        bankMappingId: "ccb-8106",
        accountNo: "6227000012348106",
        direction: "outflow",
        tradeTime: "2026-08-28T09:01:00",
        referenceFieldKey: "accountDetailNo",
        referenceValue: "CCB-UI-001",
      }),
    ]));
    expect(onPreviewSessionChange).toHaveBeenCalledWith("manual_bank_session_1");
    expect(screen.getAllByText("可录入")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "录入 1 笔流水" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(previewPayload));
  });

  test("adds and removes independent transaction forms without copying values", async () => {
    const user = userEvent.setup();
    render(
      <ManualBankTransactionBatchEditor
        bankAccounts={[]}
        onCancel={vi.fn()}
        onPreviewSessionChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "添加流水" }));
    expect(screen.getByRole("tab", { name: "流水 2" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("金额")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "删除当前流水" }));
    expect(screen.queryByRole("tab", { name: "流水 2" })).not.toBeInTheDocument();
  });
});
