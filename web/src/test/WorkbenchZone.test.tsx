import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import WorkbenchPaneSearch from "../components/workbench/WorkbenchPaneSearch";
import WorkbenchZone from "../components/workbench/WorkbenchZone";

const panes = [
  {
    id: "oa",
    title: "OA",
    rows: [
      {
        id: "OA-001",
        recordType: "oa",
        label: "付款申请",
        status: "完全关联",
        amount: "128,000.00",
        counterparty: "华东设备供应商",
        actionVariant: "detail-only",
        tableValues: {
          applicant: "赵华",
          projectName: "华东改造项目",
          applicationType: "供应商付款申请",
          amount: "128,000.00",
          counterparty: "华东设备供应商",
          reason: "设备首付款支付",
          reconciliationStatus: "完全关联",
        },
        detailFields: [],
      },
    ],
  },
  {
    id: "bank",
    title: "银行流水",
    rows: [
      {
        id: "BNK-001",
        recordType: "bank",
        label: "支取",
        status: "完全关联",
        amount: "128,000.00",
        counterparty: "华东设备供应商",
        actionVariant: "bank-review",
        tableValues: {
          direction: "支出",
          transactionTime: "2026-03-25 14:22",
          amount: "128,000.00",
          debitAmount: "128,000.00",
          creditAmount: "--",
          counterparty: "华东设备供应商",
          paymentAccount: "招商银行 9123",
          invoiceRelationStatus: "完全关联",
          paymentOrReceiptTime: "2026-03-25 14:22",
          note: "设备采购款",
          loanRepaymentDate: "--",
        },
        detailFields: [],
      },
    ],
  },
  {
    id: "invoice",
    title: "进销项发票",
    rows: [
      {
        id: "INV-001",
        recordType: "invoice",
        label: "销项票",
        status: "已核销",
        amount: "128,000.00",
        counterparty: "华东项目甲方",
        actionVariant: "detail-only",
        tableValues: {
          sellerTaxId: "91310000MA1K8A001X",
          sellerName: "溯源科技有限公司",
          buyerTaxId: "91310110MA1F99088Q",
          buyerName: "华东项目甲方",
          issueDate: "2026-03-25",
          amount: "128,000.00",
          taxRate: "13%",
          taxAmount: "16,640.00",
          grossAmount: "144,640.00",
          invoiceType: "数电专票",
        },
        detailFields: [],
      },
    ],
  },
];

function dispatchMouseEvent(target: EventTarget, type: string, clientX: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX });
  Object.defineProperty(event, "clientX", {
    configurable: true,
    value: clientX,
  });
  target.dispatchEvent(event);
}

describe("WorkbenchZone", () => {
  test("keeps selection toolbar actions and counts in the zone header", async () => {
    const user = userEvent.setup();
    const onClearSelection = vi.fn();
    const onPrimarySelectionAction = vi.fn();
    const onSecondarySelectionAction = vi.fn();
    const onTertiarySelectionAction = vi.fn();
    const onAuxiliaryAction = vi.fn();

    render(
      <WorkbenchZone
        auxiliaryHeaderActions={[{ label: "查看已处理异常", onClick: onAuxiliaryAction, tone: "warning" }]}
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        primarySelectionActionDisabled
        primarySelectionActionLabel="确认关联"
        secondarySelectionActionLabel="异常处理"
        selectionSummary={{
          total: 3,
          oa: 1,
          bank: 1,
          invoice: 1,
          amounts: {
            oa: "128,000.00",
            bank: "128,000.00",
            invoice: "144,640.00",
          },
        }}
        tertiarySelectionActionLabel="取消异常"
        title="未配对"
        tone="warning"
        onClearSelection={onClearSelection}
        onOpenDetail={() => {}}
        onPrimarySelectionAction={onPrimarySelectionAction}
        onRowAction={() => {}}
        onSecondarySelectionAction={onSecondarySelectionAction}
        onSelectRow={() => {}}
        onTertiarySelectionAction={onTertiarySelectionAction}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="open"
      />,
    );

    const zone = screen.getByTestId("zone-open");
    const toolbar = within(zone).getByText("已选 3").closest(".zone-selection-toolbar");

    expect(toolbar).not.toBeNull();
    expect(within(toolbar as HTMLElement).getByText("OA 1 / 128,000.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByText("流水 1 / 128,000.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByText("发票 1 / 144,640.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByRole("button", { name: "确认关联" })).toBeDisabled();

    await user.click(within(toolbar as HTMLElement).getByRole("button", { name: "清空选择" }));
    await user.click(within(toolbar as HTMLElement).getByRole("button", { name: "异常处理" }));
    await user.click(within(toolbar as HTMLElement).getByRole("button", { name: "取消异常" }));
    await user.click(within(zone).getByRole("button", { name: "查看已处理异常" }));

    expect(onClearSelection).toHaveBeenCalledTimes(1);
    expect(onPrimarySelectionAction).not.toHaveBeenCalled();
    expect(onSecondarySelectionAction).toHaveBeenCalledTimes(1);
    expect(onTertiarySelectionAction).toHaveBeenCalledTimes(1);
    expect(onAuxiliaryAction).toHaveBeenCalledTimes(1);
  });

  test("keeps pane toggles pressed state and expand callback accessible", async () => {
    const user = userEvent.setup();
    const onToggleExpand = vi.fn();

    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={onToggleExpand}
        panes={panes}
        zoneId="paired"
      />,
    );

    const zone = screen.getByTestId("zone-paired");
    const oaToggle = within(zone).getByRole("button", { name: "OA" });
    const bankToggle = within(zone).getByRole("button", { name: "银行流水" });
    const invoiceToggle = within(zone).getByRole("button", { name: "进销项发票" });

    expect(oaToggle).toHaveAttribute("aria-pressed", "true");
    expect(bankToggle).toHaveAttribute("aria-pressed", "true");
    expect(invoiceToggle).toHaveAttribute("aria-pressed", "true");

    await user.click(bankToggle);
    expect(bankToggle).toHaveAttribute("aria-pressed", "false");
    expect(oaToggle).toHaveAttribute("aria-pressed", "true");

    await user.click(invoiceToggle);
    expect(invoiceToggle).toHaveAttribute("aria-pressed", "false");
    expect(oaToggle).toBeDisabled();

    await user.click(within(zone).getByRole("button", { name: "放大 已配对" }));
    expect(onToggleExpand).toHaveBeenCalledTimes(1);
  });

  test("keeps pane search focus, clear, applied summary, and outside-close behavior", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onClear = vi.fn();
    const onClose = vi.fn();
    const onToggle = vi.fn();

    const { rerender } = render(
      <div>
        <button type="button">外部区域</button>
        <WorkbenchPaneSearch
          appliedValue=""
          draftValue="陈涛"
          open
          paneTitle="OA"
          onChange={onChange}
          onClear={onClear}
          onClose={onClose}
          onToggle={onToggle}
        />
      </div>,
    );

    const searchbox = screen.getByRole("searchbox", { name: "搜索 OA" });
    expect(searchbox).toHaveFocus();
    expect(searchbox).toHaveValue("陈涛");

    await user.type(searchbox, "A");
    expect(onChange).toHaveBeenLastCalledWith("陈涛A");

    await user.click(screen.getByRole("button", { name: "清空搜索 OA" }));
    expect(onClear).toHaveBeenCalledTimes(1);

    fireEvent.mouseDown(screen.getByRole("button", { name: "外部区域" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <WorkbenchPaneSearch
        appliedValue="陈涛"
        draftValue="陈涛"
        open={false}
        paneTitle="OA"
        onChange={onChange}
        onClear={onClear}
        onClose={onClose}
        onToggle={onToggle}
      />,
    );

    const summaryButton = screen.getByRole("button", { name: "搜索 OA，当前关键词 陈涛" });
    expect(summaryButton).toHaveTextContent("陈涛");
    await user.click(summaryButton);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  test("records current workbench MUI migration targets without broadening the tri-pane core scope", () => {
    const sourceRoot = resolve(__dirname, "..");
    const runtimeTargets: string[] = [];
    const runtimeOffenders = runtimeTargets.flatMap((path) => {
      const source = readFileSync(resolve(sourceRoot, path), "utf8");
      return /from ["']@mui\/|import\s+[^;]*@mui\/|Mui[A-Z]|\.Mui/.test(source) ? [path] : [];
    });
    const triPaneCoreFiles = [
      "components/workbench/ResizableTriPane.tsx",
      "components/workbench/CandidateGroupGrid.tsx",
    ].flatMap((path) => {
      const source = readFileSync(resolve(sourceRoot, path), "utf8");
      return /from ["']@mui\/|import\s+[^;]*@mui\/|Mui[A-Z]|\.Mui/.test(source) ? [path] : [];
    });
    const workbenchStyles = readFileSync(resolve(sourceRoot, "app/styles.css"), "utf8");
    const hasWorkbenchMuiStyleHooks = /\.Mui|Mui[A-Z]/.test(workbenchStyles);

    expect(runtimeOffenders).toEqual(runtimeTargets);
    expect(triPaneCoreFiles).toEqual([]);
    expect(hasWorkbenchMuiStyleHooks).toBe(false);
  });

  test("shows batch accounting mismatch details from the paired bank amount warning", async () => {
    const user = userEvent.setup();
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={[
          panes[0],
          {
            ...panes[1],
            rows: [
              {
                ...panes[1].rows[0],
                amount: "3,617.41",
                tableValues: {
                  ...panes[1].rows[0].tableValues,
                  amount: "3,617.41",
                  debitAmount: "3,617.41",
                },
                relationNote: "财务确认差额闭环",
                relationAmountCheck: {
                  status: "mismatch",
                  direction: "expense",
                  bankAmount: "3,617.41",
                  oaAmount: "3,425.41",
                  amountDelta: "192.00",
                  requiresNote: true,
                },
              },
            ],
          },
          panes[2],
        ]}
        zoneId="paired"
      />,
    );

    const icon = await screen.findByLabelText("查看金额不一致差额说明");
    expect(icon).toBeInTheDocument();

    await user.click(icon);
    expect(await screen.findByText("金额不一致")).toBeInTheDocument();
    expect(screen.getByText(/银行流水金额：3,617.41/)).toBeInTheDocument();
    expect(screen.getByText(/OA合计：3,425.41/)).toBeInTheDocument();
    expect(screen.getByText(/差额：192.00/)).toBeInTheDocument();
    expect(screen.getByText(/差额说明：财务确认差额闭环/)).toBeInTheDocument();
  });

  test("shows reconciliation warning details on paired OA rows", async () => {
    const user = userEvent.setup();
    const oaRowWithWarning = {
      ...panes[0].rows[0],
      reconciliationWarnings: [
        {
          code: "invoice_amount_mismatch",
          message: "附件发票合计与 OA/流水金额不一致",
        },
      ],
    };

    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={[
          {
            ...panes[0],
            rows: [oaRowWithWarning],
          },
          panes[1],
          panes[2],
        ]}
        zoneId="paired"
      />,
    );

    const icon = await screen.findByLabelText("查看自动匹配警示");
    expect(icon).toBeInTheDocument();

    await user.click(icon);
    expect(await screen.findByText("附件发票合计与 OA/流水金额不一致")).toBeInTheDocument();
    expect(screen.getByText("金额不一致")).toBeInTheDocument();
  });

  test("does not expose automatic matching warning icons in open rows", () => {
    const oaRowWithWarning = {
      ...panes[0].rows[0],
      reconciliationWarnings: [
        {
          code: "invoice_amount_mismatch",
          message: "附件发票合计与 OA/流水金额不一致",
        },
      ],
    };

    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="未配对"
        tone="warning"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={[
          {
            ...panes[0],
            rows: [oaRowWithWarning],
          },
          panes[1],
          panes[2],
        ]}
        zoneId="open"
      />,
    );

    expect(screen.queryByLabelText("查看自动匹配警示")).not.toBeInTheDocument();
  });

  test("keeps paired/open zones as the only visible display states", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="未配对"
        tone="warning"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="open"
      />,
    );

    expect(screen.getByText("未配对")).toBeInTheDocument();
    expect(screen.queryByText("候选")).not.toBeInTheDocument();
    expect(screen.queryByText("needs_review")).not.toBeInTheDocument();
  });

  test("opens batch accounting mismatch details on keyboard focus and hover", async () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={[
          panes[0],
          {
            ...panes[1],
            rows: [
              {
                ...panes[1].rows[0],
                relationNote: "财务确认差额闭环",
                relationAmountCheck: {
                  status: "mismatch",
                  direction: "expense",
                  bankAmount: "3,617.41",
                  oaAmount: "3,425.41",
                  amountDelta: "192.00",
                  requiresNote: true,
                },
              },
            ],
          },
          panes[2],
        ]}
        zoneId="paired"
      />,
    );

    const icon = await screen.findByLabelText("查看金额不一致差额说明");
    fireEvent.focus(icon);
    expect(await screen.findByText("金额不一致")).toBeInTheDocument();

    fireEvent.blur(icon);
    fireEvent.mouseEnter(icon);
    expect(await screen.findByText("金额不一致")).toBeInTheDocument();
  });

  test("does not show batch accounting mismatch warning for matched or note-free optional mismatch rows", () => {
    const matchedBankRow = {
      ...panes[1].rows[0],
      relationNote: "财务确认差额闭环",
      relationAmountCheck: {
        status: "matched",
        direction: "expense",
        bankAmount: "3,617.41",
        oaAmount: "3,617.41",
        amountDelta: "0.00",
        requiresNote: false,
      },
    };
    const noteFreeOptionalMismatchBankRow = {
      ...panes[1].rows[0],
      id: "BNK-002",
      relationNote: "",
      relationAmountCheck: {
        status: "mismatch",
        direction: "expense",
        bankAmount: "3,617.41",
        oaAmount: "3,425.41",
        amountDelta: "192.00",
        requiresNote: false,
      },
    };

    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={[
          panes[0],
          {
            ...panes[1],
            rows: [matchedBankRow, noteFreeOptionalMismatchBankRow],
          },
          panes[2],
        ]}
        zoneId="paired"
      />,
    );

    expect(screen.queryByLabelText("查看金额不一致差额说明")).not.toBeInTheDocument();
  });

  test("collapses and restores panes per zone without affecting splitter count rules", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="已配对"
        tone="success"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="paired"
      />,
    );

    expect(screen.getAllByRole("separator")).toHaveLength(2);
    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "银行流水" }));

    expect(screen.queryByTestId("pane-bank")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "OA" }));

    expect(screen.queryByTestId("pane-oa")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("separator")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "银行流水" }));

    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();
    expect(screen.getByTestId("pane-bank")).toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  test("dragging a splitter can collapse a pane to zero width", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        title="未配对"
        tone="warning"
        meta="等待人工处理"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="open"
      />,
    );

    const triPane = screen.getByTestId("tri-pane");
    Object.defineProperty(triPane, "clientWidth", {
      configurable: true,
      value: 1000,
    });

    const firstSplitter = screen.getAllByRole("separator")[0];
    act(() => {
      dispatchMouseEvent(firstSplitter, "mousedown", 320);
    });
    act(() => {
      dispatchMouseEvent(window, "mousemove", -40);
      dispatchMouseEvent(window, "mouseup", -40);
    });

    expect(screen.queryByTestId("pane-oa")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  test("shows an expand toggle in the zone header", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        title="未配对"
        tone="warning"
        meta="等待人工处理"
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        panes={panes}
        isExpanded={false}
        isVisible
        onToggleExpand={() => {}}
        zoneId="open"
      />,
    );

    expect(screen.getByRole("button", { name: "放大 未配对" })).toBeInTheDocument();
  });
});
