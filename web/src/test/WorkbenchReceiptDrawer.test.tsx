import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import WorkbenchReceiptDrawer from "../components/workbench/WorkbenchReceiptDrawer";
import { fetchWorkbenchReceiptDraft, printWorkbenchReceipt } from "../features/workbench/api";
import type { WorkbenchReceiptDraft } from "../features/workbench/types";

vi.mock("../features/workbench/api", async () => {
  const actual = await vi.importActual<typeof import("../features/workbench/api")>("../features/workbench/api");
  return {
    ...actual,
    fetchWorkbenchReceiptDraft: vi.fn(),
    printWorkbenchReceipt: vi.fn(),
  };
});

const validDraft: WorkbenchReceiptDraft = {
  caseId: "CASE-RECEIPT-1",
  relationVersion: 7,
  sourceFingerprint: "f".repeat(64),
  totalAmount: "100.00",
  canPrint: true,
  receipts: [
    {
      receiptKey: "昆明示例客户|2026-08-30|CNY",
      payer: "昆明示例客户",
      date: "2026-08-30",
      currency: "CNY",
      incomeAmount: "100.00",
      lineTotal: "100.00",
      balanced: true,
      handler: "经手人甲",
      supervisor: "主管乙",
      bankTransactionIds: ["bank-1"],
      lines: [
        {
          summary: "技术服务费",
          amount: "100.00",
          note: "发票 12345678901234567890",
          invoiceNo: "12345678901234567890",
          sourceInvoiceIds: ["invoice-1"],
        },
      ],
    },
  ],
  issues: [],
  reversalAdjustments: [
    {
      kind: "partial",
      redInvoiceId: "invoice-red",
      redInvoiceNo: "22345678901234567890",
      blueInvoiceId: "invoice-1",
      blueInvoiceNo: "12345678901234567890",
      amount: "20.00",
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
});

describe("WorkbenchReceiptDrawer", () => {
  test("loads the editable template and blocks printing until the line total matches income", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchWorkbenchReceiptDraft).mockResolvedValue(validDraft);

    render(
      <WorkbenchReceiptDrawer
        caseId="CASE-RECEIPT-1"
        onClose={() => undefined}
        open
      />,
    );

    expect(await screen.findByDisplayValue("昆明示例客户")).toBeInTheDocument();
    expect(screen.getByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(screen.getByText(/已依据红票备注中的明确蓝票号码处理 1 组冲销/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打印收据" })).toBeEnabled();

    const amount = screen.getByRole("textbox", { name: "收据 1 明细 1 金额" });
    await user.clear(amount);
    await user.type(amount, "90");

    expect(screen.getByText("明细与收入相差 ¥10.00，调整一致后才能打印。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打印收据" })).toBeDisabled();

    await user.clear(amount);
    await user.type(amount, "100");
    expect(screen.getByRole("button", { name: "打印收据" })).toBeEnabled();
  });

  test("requires an explicit acknowledgement when exact reversal matching reports an issue", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchWorkbenchReceiptDraft).mockResolvedValue({
      ...validDraft,
      reversalAdjustments: [],
      issues: [
        {
          code: "receipt_reversal_target_unresolved",
          message: "红票备注中的蓝票号码无法唯一匹配，请人工核对。",
          invoiceIds: ["invoice-red"],
        },
      ],
    });

    render(
      <WorkbenchReceiptDrawer
        caseId="CASE-RECEIPT-1"
        onClose={() => undefined}
        open
      />,
    );

    expect(await screen.findByText("红票备注中的蓝票号码无法唯一匹配，请人工核对。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打印收据" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "我已人工核对并修正上述冲销异常" }));
    expect(screen.getByRole("button", { name: "打印收据" })).toBeEnabled();
  });

  test("submits edited receipt fields and confirms before discarding dirty changes", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const popupFrame = {
      addEventListener: vi.fn(),
      contentWindow: { focus: vi.fn(), print: vi.fn() },
      src: "",
    };
    const popup = {
      addEventListener: vi.fn(),
      close: vi.fn(),
      document: {
        close: vi.fn(),
        getElementById: vi.fn().mockReturnValue(popupFrame),
        open: vi.fn(),
        write: vi.fn(),
      },
    };
    vi.mocked(fetchWorkbenchReceiptDraft).mockResolvedValue(validDraft);
    vi.mocked(printWorkbenchReceipt).mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" }));
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn().mockReturnValue("blob:receipt-pdf"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    render(
      <WorkbenchReceiptDrawer
        caseId="CASE-RECEIPT-1"
        onClose={onClose}
        open
      />,
    );

    const payer = await screen.findByRole("textbox", { name: "收据 1 付款单位" });
    await user.clear(payer);
    await user.type(payer, "编辑后的付款单位");
    await user.clear(screen.getByRole("textbox", { name: "收据 1 明细 1 摘要" }));
    await user.type(screen.getByRole("textbox", { name: "收据 1 明细 1 摘要" }), "编辑后的服务费");

    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "打印收据" }));
    await waitFor(() => expect(printWorkbenchReceipt).toHaveBeenCalledWith({
      caseId: "CASE-RECEIPT-1",
      relationVersion: 7,
      sourceFingerprint: "f".repeat(64),
      issuesAcknowledged: false,
      receipts: [
        {
          receiptKey: "昆明示例客户|2026-08-30|CNY",
          payer: "编辑后的付款单位",
          date: "2026-08-30",
          handler: "经手人甲",
          supervisor: "主管乙",
          lines: [
            {
              summary: "编辑后的服务费",
              amount: "100.00",
              note: "发票 12345678901234567890",
            },
          ],
        },
      ],
    }));

    await waitFor(() => expect(screen.getByText("金额已核对，可以打印")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledTimes(1);
  });
});
