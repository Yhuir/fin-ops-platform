import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import WorkbenchInvoiceEntryDrawer from "../components/workbench/WorkbenchInvoiceEntryDrawer";
import type { ManualInvoiceEntryBatchPreview } from "../features/imports/types";
import {
  confirmWorkbenchManualInvoiceSupplement,
  deleteWorkbenchOaSupportingDocument,
  listWorkbenchOaSupportingDocuments,
  uploadWorkbenchOaSupportingDocuments,
} from "../features/workbench/api";

const batchPreview = { fileIds: ["file-1"], importSession: { session: { id: "session-1" } } } as ManualInvoiceEntryBatchPreview;

vi.mock("../components/imports/ManualInvoiceBatchEditor", () => ({
  default: ({ onSubmit }: { onSubmit: (preview: ManualInvoiceEntryBatchPreview) => Promise<void> }) => (
    <button type="button" onClick={() => { void onSubmit(batchPreview); }}>提交手工录入测试</button>
  ),
}));

vi.mock("../features/workbench/api", async () => {
  const actual = await vi.importActual<typeof import("../features/workbench/api")>("../features/workbench/api");
  return {
    ...actual,
    confirmWorkbenchManualInvoiceSupplement: vi.fn(),
    deleteWorkbenchOaSupportingDocument: vi.fn(),
    listWorkbenchOaSupportingDocuments: vi.fn(),
    uploadWorkbenchOaSupportingDocuments: vi.fn(),
  };
});

const target = { caseId: "CASE-1", oaRowId: "oa-1", expenseItemId: "oa-1:item:0" };

afterEach(() => vi.clearAllMocks());

describe("WorkbenchInvoiceEntryDrawer", () => {
  test("uses one drawer for supporting documents and manual invoice relation", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onCompleted = vi.fn();
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue([]);
    vi.mocked(uploadWorkbenchOaSupportingDocuments).mockResolvedValue([{
      id: "document-1",
      oaRowId: target.oaRowId,
      expenseItemId: target.expenseItemId,
      fileName: "voucher.pdf",
      contentType: "application/pdf",
      sha256: "sha",
      sizeBytes: 12,
      createdAt: "2026-08-18",
      contentUrl: "/documents/document-1/content",
    }]);
    vi.mocked(deleteWorkbenchOaSupportingDocument).mockResolvedValue();
    vi.mocked(confirmWorkbenchManualInvoiceSupplement).mockResolvedValue({ case_id: "CASE-1" });

    render(
      <WorkbenchInvoiceEntryDrawer
        open
        target={target}
        onClose={onClose}
        onCompleted={onCompleted}
      />,
    );

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("tab", { name: "JPG/PDF上传" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "手工录入" })).toBeInTheDocument();
    expect(screen.getByText("这些文件作为补充凭证直接关联当前 OA 子付款项，不进入统一发票池。")).toBeInTheDocument();

    await screen.findByText("选择 JPG / PDF 文件");
    const input = screen.getByLabelText("选择 JPG / PDF 文件") as HTMLInputElement;
    const file = new File(["%PDF-1.7"], "voucher.pdf", { type: "application/pdf" });
    await user.upload(input, file);
    await waitFor(() => expect(uploadWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target, [file]));
    expect(await screen.findByRole("link", { name: "voucher.pdf" })).toHaveAttribute("href", "/documents/document-1/content");

    await user.click(screen.getByRole("tab", { name: "手工录入" }));
    await user.click(screen.getByRole("button", { name: "提交手工录入测试" }));
    await waitFor(() => {
      expect(confirmWorkbenchManualInvoiceSupplement).toHaveBeenCalledWith(target, batchPreview);
      expect(onCompleted).toHaveBeenCalledTimes(2);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
