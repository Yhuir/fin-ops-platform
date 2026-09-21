import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import WorkbenchInvoiceEntryDrawer from "../components/workbench/WorkbenchInvoiceEntryDrawer";
import type { ManualInvoiceEntryBatchPreview } from "../features/imports/types";
import type { WorkbenchOaSupportingDocumentSet } from "../features/workbench/types";
import {
  confirmWorkbenchManualInvoiceSupplement,
  listWorkbenchOaSupportingDocuments,
  previewWorkbenchManualInvoices,
  saveWorkbenchOaSupportingDocuments,
  WorkbenchApiError,
} from "../features/workbench/api";

const batchPreview = { fileIds: ["file-1"], importSession: { session: { id: "session-1" } } } as ManualInvoiceEntryBatchPreview;
vi.mock("../components/imports/ManualInvoiceBatchEditor", () => ({
  default: ({ onSubmit, previewInvoices }: {
    onSubmit: (preview: ManualInvoiceEntryBatchPreview) => Promise<void>;
    previewInvoices: () => Promise<ManualInvoiceEntryBatchPreview>;
  }) => <button type="button" onClick={() => { void previewInvoices().then(onSubmit); }}>提交发票录入测试</button>,
}));
vi.mock("../features/workbench/api", async () => ({
  ...await vi.importActual<typeof import("../features/workbench/api")>("../features/workbench/api"),
  confirmWorkbenchManualInvoiceSupplement: vi.fn(),
  listWorkbenchOaSupportingDocuments: vi.fn(),
  previewWorkbenchManualInvoices: vi.fn(),
  saveWorkbenchOaSupportingDocuments: vi.fn(),
}));
const target = { caseId: "CASE-1", oaRowId: "oa-1", expenseItemId: "oa-1:item:0" };
const otherTarget = { ...target, oaRowId: "oa-2", expenseItemId: "oa-2:item:0" };
const document = {
  id: "document-1", oaRowId: target.oaRowId, expenseItemId: target.expenseItemId,
  fileName: "voucher.png", contentType: "image/png", sha256: "sha", sizeBytes: 12,
  createdBy: "finance-user", createdAt: "2026-08-18", contentUrl: "/documents/document-1/content", thumbnailUrl: "",
};
const empty: WorkbenchOaSupportingDocumentSet = { documents: [], totalAmount: null, version: 0 };
const existing: WorkbenchOaSupportingDocumentSet = { documents: [document], totalAmount: "100.00", version: 3 };
const file = () => new File(["png"], "new.png", { type: "image/png" });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
function setup(props: Partial<React.ComponentProps<typeof WorkbenchInvoiceEntryDrawer>> = {}) {
  const onClose = vi.fn();
  const onSupportingDocumentsChanged = vi.fn();
  const baseProps = { open: true, initialMode: "upload" as const, target, onClose, onCompleted: vi.fn(), onSupportingDocumentsChanged, ...props };
  return { ...render(<WorkbenchInvoiceEntryDrawer {...baseProps} />), baseProps, onClose, onSupportingDocumentsChanged, user: userEvent.setup() };
}
async function ready() { await waitFor(() => expect(screen.getByLabelText("上传 JPG、PNG 或 PDF 补充凭证")).toBeEnabled()); }
beforeEach(() => { vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue(empty); });
afterEach(() => vi.resetAllMocks());

describe("WorkbenchInvoiceEntryDrawer", () => {
  test("reconfirms a changed invoice basis without requiring amount or file edits", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue({ ...existing, amountConfirmationRequired: true });
    vi.mocked(saveWorkbenchOaSupportingDocuments).mockResolvedValue({ ...existing, version: 4, amountConfirmationRequired: false });
    const { user } = setup();
    await ready();
    expect(screen.getByText(/关联发票已变化/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    await waitFor(() => expect(saveWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target, expect.objectContaining({
      totalAmount: "100.00", expectedVersion: 3, retainedDocumentIds: [document.id], files: [],
    })));
  });

  test("defaults to canonical invoice entry and reports completion without auto-closing", async () => {
    const { user, onClose, baseProps } = setup({ initialMode: "manual" });
    vi.mocked(previewWorkbenchManualInvoices).mockResolvedValue(batchPreview);
    vi.mocked(confirmWorkbenchManualInvoiceSupplement).mockResolvedValue({ case_id: "CASE-1" });
    expect(screen.getByRole("tab", { name: "发票录入" })).toHaveAttribute("aria-selected", "true");
    expect(listWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "提交发票录入测试" }));
    await waitFor(() => expect(baseProps.onCompleted).toHaveBeenCalledOnce());
    expect(confirmWorkbenchManualInvoiceSupplement).toHaveBeenCalledWith(target, batchPreview);
    expect(screen.getByRole("status")).toHaveTextContent("发票已录入");
    expect(onClose).not.toHaveBeenCalled();
  });

  test("stages multiple files and zero total locally, then saves them with one request", async () => {
    const { user, onSupportingDocumentsChanged } = setup();
    await ready();
    const files = [file(), new File(["pdf"], "second.pdf", { type: "application/pdf" })];
    const dropzone = screen.getByText("拖拽文件到此处，或点击选择").closest("label")!;
    fireEvent.dragEnter(dropzone, { dataTransfer: { files } });
    expect(screen.getByText("松开以添加文件")).toBeInTheDocument();
    fireEvent.drop(dropzone, { dataTransfer: { files } });
    expect(screen.getByText("new.png（待保存）")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存凭证" })).toBeDisabled();
    expect(saveWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
    await user.type(screen.getByRole("textbox", { name: "凭证总金额（元）" }), "0");
    vi.mocked(saveWorkbenchOaSupportingDocuments).mockResolvedValue({ ...existing, totalAmount: "0.00" });
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    await waitFor(() => expect(onSupportingDocumentsChanged).toHaveBeenCalledWith(target, [document]));
    expect(saveWorkbenchOaSupportingDocuments).toHaveBeenCalledOnce();
    expect(saveWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target, { files, retainedDocumentIds: [], totalAmount: "0", expectedVersion: 0 });
    expect(screen.getByRole("status")).toHaveTextContent("凭证已保存");
    expect(screen.queryByRole("button", { name: "保存凭证" })).not.toBeInTheDocument();
  });

  test("cancel restores existing files and amount, and switching tabs preserves the draft", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue(existing);
    const { user } = setup(); await ready();
    await user.click(screen.getByRole("button", { name: "删除 voucher.png" }));
    await user.upload(screen.getByLabelText("上传 JPG、PNG 或 PDF 补充凭证"), file());
    fireEvent.change(screen.getByRole("textbox", { name: "凭证总金额（元）" }), { target: { value: "80" } });
    await user.click(screen.getByRole("tab", { name: "发票录入" }));
    await user.click(screen.getByRole("tab", { name: "补充凭证" }));
    expect(screen.getByText("new.png（待保存）")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("80");
    expect(listWorkbenchOaSupportingDocuments).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "取消修改" }));
    expect(screen.getByRole("link", { name: "voucher.png" })).toBeInTheDocument();
    expect(screen.queryByText("new.png（待保存）")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("100.00");
    expect(saveWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
  });

  test("unknown amount stays blank; invalid amounts cannot save and zero is valid", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue({ ...existing, totalAmount: null });
    const { user } = setup(); await ready();
    const amount = screen.getByRole("textbox", { name: "凭证总金额（元）" });
    expect(amount).toHaveValue("");
    for (const value of ["-1", "0.001", "1e3", "", "1."]) {
      fireEvent.change(amount, { target: { value } });
      expect(screen.getByRole("button", { name: "保存凭证" })).toBeDisabled();
    }
    await user.type(amount, "0");
    expect(screen.getByRole("button", { name: "保存凭证" })).toBeEnabled();
  });

  test("deleting the final file saves an empty set and null amount only on save", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue(existing);
    vi.mocked(saveWorkbenchOaSupportingDocuments).mockResolvedValue({ ...empty, version: 4 });
    const { user } = setup(); await ready();
    await user.click(screen.getByRole("button", { name: "删除 voucher.png" }));
    expect(saveWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    await waitFor(() => expect(saveWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target, {
      retainedDocumentIds: [], files: [], totalAmount: null, expectedVersion: 3,
    }));
    expect(screen.getByRole("status")).toHaveTextContent("凭证已保存");
  });

  test("failed saves preserve the complete draft and refresh failure is explicitly already saved", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue(existing);
    vi.mocked(saveWorkbenchOaSupportingDocuments).mockRejectedValueOnce(new WorkbenchApiError(
      "文件内容与扩展名不一致，请重新选择有效文件。", { status: 400, code: "supporting_document_signature_invalid", requestId: "request-1" },
    )).mockResolvedValueOnce({ ...existing, totalAmount: "80.00", version: 4 });
    const onSupportingDocumentsChanged = vi.fn().mockRejectedValue(new Error("刷新失败"));
    const { user } = setup({ onSupportingDocumentsChanged }); await ready();
    const newFile = file();
    await user.upload(screen.getByLabelText("上传 JPG、PNG 或 PDF 补充凭证"), newFile);
    fireEvent.change(screen.getByRole("textbox", { name: "凭证总金额（元）" }), { target: { value: "80" } });
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    expect(await screen.findByText(/文件内容与扩展名不一致.*request-1/)).toBeInTheDocument();
    expect(screen.getByText("new.png（待保存）")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("80");
    expect(onSupportingDocumentsChanged).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("凭证已保存，但页面刷新失败"));
    expect(saveWorkbenchOaSupportingDocuments).toHaveBeenLastCalledWith(target, {
      retainedDocumentIds: [document.id], files: [newFile], totalAmount: "80", expectedVersion: 3,
    });
    expect(screen.queryByRole("button", { name: "保存凭证" })).not.toBeInTheDocument();
  });

  test("ignores a late list response from a previously selected target", async () => {
    const old = deferred<WorkbenchOaSupportingDocumentSet>();
    vi.mocked(listWorkbenchOaSupportingDocuments).mockReturnValueOnce(old.promise).mockResolvedValueOnce(empty);
    const { rerender, baseProps } = setup();
    await waitFor(() => expect(listWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target));
    rerender(<WorkbenchInvoiceEntryDrawer {...baseProps} target={otherTarget} />);
    await ready();
    await act(async () => old.resolve(existing));
    expect(screen.queryByRole("link", { name: "voucher.png" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("");
  });

  test("a late save cannot populate the next target or replace its draft", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValueOnce(existing).mockResolvedValueOnce(empty);
    const old = deferred<WorkbenchOaSupportingDocumentSet>();
    vi.mocked(saveWorkbenchOaSupportingDocuments).mockReturnValueOnce(old.promise);
    const { user, rerender, baseProps } = setup(); await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "凭证总金额（元）" }), { target: { value: "80" } });
    await user.click(screen.getByRole("button", { name: "保存凭证" }));
    rerender(<WorkbenchInvoiceEntryDrawer {...baseProps} target={otherTarget} />);
    await ready();
    await user.upload(screen.getByLabelText("上传 JPG、PNG 或 PDF 补充凭证"), file());
    await act(async () => old.resolve({ ...existing, totalAmount: "80.00" }));
    expect(screen.getByText("new.png（待保存）")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "voucher.png" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("closing without saving discards the draft on the next open", async () => {
    const { user, rerender, baseProps, onClose } = setup(); await ready();
    await user.upload(screen.getByLabelText("上传 JPG、PNG 或 PDF 补充凭证"), file());
    await user.click(screen.getByRole("button", { name: "关闭录入发票" }));
    expect(onClose).toHaveBeenCalledOnce();
    rerender(<WorkbenchInvoiceEntryDrawer {...baseProps} open={false} />);
    rerender(<WorkbenchInvoiceEntryDrawer {...baseProps} />);
    await ready();
    expect(screen.queryByText("new.png（待保存）")).not.toBeInTheDocument();
    expect(saveWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
  });

  test("read-only mode permits file preview but blocks all edits", async () => {
    vi.mocked(listWorkbenchOaSupportingDocuments).mockResolvedValue(existing);
    setup({ disabled: true });
    expect(await screen.findByRole("link", { name: "voucher.png" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "凭证总金额（元）" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "删除 voucher.png" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存凭证" })).toBeDisabled();
  });
});


test("switching from voucher management to another target's invoice mode never inherits loading", async () => {
  const old = deferred<WorkbenchOaSupportingDocumentSet>();
  vi.mocked(listWorkbenchOaSupportingDocuments).mockReturnValueOnce(old.promise);
  const { rerender, baseProps, user, onClose } = setup();
  await waitFor(() => expect(listWorkbenchOaSupportingDocuments).toHaveBeenCalledWith(target));
  rerender(<WorkbenchInvoiceEntryDrawer {...baseProps} target={otherTarget} initialMode="manual" />);
  expect(screen.getByRole("tab", { name: "发票录入" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "补充凭证" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "关闭录入发票" })).toBeEnabled();
  await act(async () => old.resolve(existing));
  expect(listWorkbenchOaSupportingDocuments).toHaveBeenCalledOnce();
  await user.click(screen.getByRole("button", { name: "关闭录入发票" }));
  expect(onClose).toHaveBeenCalledOnce();
});

test("an initial load failure has an explicit retry without allowing an unversioned save", async () => {
  vi.mocked(listWorkbenchOaSupportingDocuments).mockRejectedValueOnce(new Error("加载失败")).mockResolvedValueOnce(existing);
  const { user } = setup();
  await user.click(await screen.findByRole("button", { name: "重新读取凭证" }));
  await ready();
  expect(screen.getByRole("link", { name: "voucher.png" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存凭证" })).toBeDisabled();
  expect(saveWorkbenchOaSupportingDocuments).not.toHaveBeenCalled();
});
