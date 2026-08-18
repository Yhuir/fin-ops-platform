import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import WorkbenchInvoiceEntryDrawer from "../components/workbench/WorkbenchInvoiceEntryDrawer";
import type { ManualInvoiceEntryBatchPreview } from "../features/imports/types";
import {
  confirmWorkbenchManualInvoiceSupplement,
  deleteWorkbenchOaSupportingDocument,
  listWorkbenchOaSupportingDocuments,
  uploadWorkbenchOaSupportingDocuments,
  WorkbenchApiError,
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
    const onSupportingDocumentsChanged = vi.fn();
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue([]);
    vi.mocked(uploadWorkbenchOaSupportingDocuments).mockResolvedValue([{
      id: "document-1",
      oaRowId: target.oaRowId,
      expenseItemId: target.expenseItemId,
      fileName: "voucher.png",
      contentType: "image/png",
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
        onSupportingDocumentsChanged={onSupportingDocumentsChanged}
      />,
    );

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("tab", { name: "上传凭证" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "手工录入" })).toBeInTheDocument();
    expect(screen.getByText("补充凭证直接关联当前 OA 子付款项，不进入统一发票池。")).toBeInTheDocument();

    const dropzoneText = await screen.findByText("拖拽文件到此处，或点击选择");
    const dropzone = dropzoneText.closest("label")!;
    const file = new File(["png"], "voucher.png", { type: "image/png" });
    fireEvent.dragEnter(dropzone, { dataTransfer: { files: [file] } });
    expect(screen.getByText("松开以上传文件")).toBeInTheDocument();
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
    await waitFor(() => expect(uploadWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target, [file]));
    expect(await screen.findByRole("link", { name: "voucher.png" })).toHaveAttribute("href", "/documents/document-1/content");
    expect(onSupportingDocumentsChanged).toHaveBeenCalledWith(target, [expect.objectContaining({ id: "document-1" })]);

    await user.click(screen.getByRole("tab", { name: "手工录入" }));
    await user.click(screen.getByRole("button", { name: "提交手工录入测试" }));
    await waitFor(() => {
      expect(confirmWorkbenchManualInvoiceSupplement).toHaveBeenCalledWith(target, batchPreview);
      expect(onCompleted).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  test("shows a specific upload error instead of a generic failure", async () => {
    const user = userEvent.setup();
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue([]);
    vi.mocked(uploadWorkbenchOaSupportingDocuments).mockRejectedValue(new WorkbenchApiError(
      "文件内容与扩展名不一致，请重新选择有效文件。",
      { status: 400, code: "supporting_document_signature_invalid", requestId: "request-1" },
    ));

    render(
      <WorkbenchInvoiceEntryDrawer
        open
        target={target}
        onClose={vi.fn()}
        onCompleted={vi.fn()}
      />,
    );

    const input = await screen.findByLabelText("上传 JPG、PNG 或 PDF 补充凭证") as HTMLInputElement;
    await user.upload(input, new File(["invalid"], "voucher.jpg", { type: "image/jpeg" }));

    expect(await screen.findByText("文件内容与扩展名不一致，请重新选择有效文件。（请求编号：request-1）")).toBeInTheDocument();
  });
});
