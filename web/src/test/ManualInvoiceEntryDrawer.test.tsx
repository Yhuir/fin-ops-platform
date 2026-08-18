import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import ManualInvoiceEntryDrawer from "../components/imports/ManualInvoiceEntryDrawer";
import type { ImportSessionPayload, ManualInvoiceEntryBatchPreview } from "../features/imports/types";
import {
  confirmImportFiles,
  previewManualInvoices,
  recognizeManualInvoice,
} from "../features/imports/api";

vi.mock("../features/imports/api", async () => {
  const actual = await vi.importActual<typeof import("../features/imports/api")>("../features/imports/api");
  return {
    ...actual,
    confirmImportFiles: vi.fn(),
    previewManualInvoices: vi.fn(),
    recognizeManualInvoice: vi.fn(),
  };
});

const sessionPayload: ImportSessionPayload = {
  session: {
    id: "manual_session_1",
    importedBy: "web_finance_user",
    fileCount: 1,
    status: "awaiting_confirmation",
    createdAt: "2026-08-14T10:00:00+08:00",
  },
  files: [{
    id: "manual_file_1",
    fileName: "发票录入",
    templateCode: "manual_invoice_entry",
    batchType: "input_invoice",
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
    rowResults: [],
  }],
  duplicateGroups: [],
  affectedScopeKeys: [],
};

const previewPayload: ManualInvoiceEntryBatchPreview = {
  values: [{
    invoiceDirection: "input",
    invoiceNature: "blue",
    sellerName: "云南供应商",
    sellerTaxNo: "915300001",
    buyerName: "云南采购方",
    buyerTaxNo: "915300002",
    invoiceNumber: "12345678901234567890",
    invoiceCode: "",
    invoiceDate: "2026-08-14",
    netAmount: "100.00",
    taxRate: "13",
    taxAmount: "13.00",
    totalWithTax: "113.00",
  }],
  fileIds: ["manual_file_1"],
  importSession: sessionPayload,
};

afterEach(() => {
  vi.clearAllMocks();
});

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText("销方名称"), { target: { value: "云南供应商" } });
  fireEvent.change(screen.getByLabelText("销方识别号"), { target: { value: "915300001" } });
  fireEvent.change(screen.getByLabelText("购方名称"), { target: { value: "云南采购方" } });
  fireEvent.change(screen.getByLabelText("购方识别号"), { target: { value: "915300002" } });
  fireEvent.change(screen.getByLabelText("发票号码"), { target: { value: "12345678901234567890" } });
  fireEvent.change(screen.getByLabelText("开票日期"), { target: { value: "2026-08-14" } });
  fireEvent.change(screen.getByLabelText("税率"), { target: { value: "13" } });
  fireEvent.change(screen.getByLabelText("不含税价格"), { target: { value: "100" } });
  fireEvent.change(screen.getByLabelText("税额"), { target: { value: "13" } });
  fireEvent.change(screen.getByLabelText("价税合计"), { target: { value: "113" } });
}

describe("ManualInvoiceEntryDrawer", () => {
  test("saves invoice information locally before one batch preview and canonical confirm", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onImportAccepted = vi.fn();
    vi.mocked(previewManualInvoices).mockResolvedValue(previewPayload);
    vi.mocked(confirmImportFiles).mockResolvedValue({
      ...sessionPayload,
      session: { ...sessionPayload.session, status: "confirmed" },
      files: [{ ...sessionPayload.files[0]!, status: "confirmed" }],
    });

    render(
      <ManualInvoiceEntryDrawer
        onClose={onClose}
        onImportAccepted={onImportAccepted}
        open
      />,
    );

    expect(screen.getByRole("dialog", { name: "发票录入" })).toBeInTheDocument();
    expect(screen.getByText("上传识别")).toBeInTheDocument();
    fillRequiredFields();
    await user.click(screen.getByRole("button", { name: "预览" }));

    expect(await screen.findByText("12345678901234567890")).toBeInTheDocument();
    expect(screen.getByText("12345678901234567890")).toBeInTheDocument();
    expect(previewManualInvoices).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "返回编辑" }));
    expect(screen.getByLabelText("销方名称")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "预览" }));
    await user.click(screen.getByRole("button", { name: "保存信息" }));
    await user.click(screen.getByRole("button", { name: "录入发票池" }));

    await waitFor(() => {
      expect(previewManualInvoices).toHaveBeenCalledWith([expect.objectContaining({
        invoiceDirection: "input",
        invoiceNature: "blue",
        invoiceCode: "",
      })]);
      expect(confirmImportFiles).toHaveBeenCalledWith("manual_session_1", ["manual_file_1"]);
      expect(onImportAccepted).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  test("recognizes a dropped PNG file and keeps OCR fields editable", async () => {
    const user = userEvent.setup();
    vi.mocked(recognizeManualInvoice).mockResolvedValue({
      sellerName: "OCR销方",
      invoiceNumber: "12345678901234567890",
    });

    render(<ManualInvoiceEntryDrawer onClose={vi.fn()} onImportAccepted={vi.fn()} open />);
    await user.click(screen.getByText("上传识别"));
    const dropzoneText = screen.getByText("拖入或选择 JPG / PNG / PDF");
    const file = new File(["png"], "invoice.png", { type: "image/png" });
    fireEvent.drop(dropzoneText.closest("label")!, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(recognizeManualInvoice).toHaveBeenCalledWith(file));
    const seller = screen.getByLabelText("销方名称") as HTMLInputElement;
    expect(seller.value).toBe("OCR销方");
    await user.clear(seller);
    await user.type(seller, "人工修正销方");
    expect(seller.value).toBe("人工修正销方");
  });
});
