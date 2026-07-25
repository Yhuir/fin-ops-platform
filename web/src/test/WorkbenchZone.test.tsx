import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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
        availableActions: ["detail"],
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
        availableActions: ["detail"],
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
        availableActions: ["detail"],
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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

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
        selectionActionNotice="OA 正在同步，完成后将自动恢复关联操作。"
        secondarySelectionActionLabel="异常处理"
        selectionSummary={{
          explicitTotal: 2,
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
        searchQuery=""
        onSearchQueryChange={() => {}}
        onClearSelection={onClearSelection}
        onOpenDetail={() => {}}
        onPrimarySelectionAction={onPrimarySelectionAction}
        onRowAction={() => {}}
        onSecondarySelectionAction={onSecondarySelectionAction}
        onSelectRow={() => {}}
        onTertiarySelectionAction={onTertiarySelectionAction}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="unpaired"
      />,
    );

    const zone = screen.getByTestId("zone-unpaired");
    const toolbar = within(zone).getByText("已选 2").closest(".zone-selection-toolbar");

    expect(toolbar).not.toBeNull();
    expect(within(toolbar as HTMLElement).getByText("带入 1")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByText("OA 1 / 128,000.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByText("流水 1 / 128,000.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByText("发票 1 / 144,640.00")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).getByRole("button", { name: "确认关联" })).toBeDisabled();
    expect(within(toolbar as HTMLElement).getByRole("status", {
      name: "OA 正在同步，完成后将自动恢复关联操作。",
    })).toBeInTheDocument();

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

  test("renders an accessible busy primary selection action on the next render", () => {
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        primarySelectionActionLabel="确认关联"
        primarySelectionActionPending
        primarySelectionActionPendingLabel="正在准备确认预览"
        selectionSummary={{
          total: 2,
          oa: 1,
          bank: 1,
          invoice: 0,
          amounts: { oa: "128,000.00", bank: "128,000.00", invoice: "0.00" },
        }}
        title="未配对"
        tone="warning"
        searchQuery=""
        onSearchQueryChange={() => {}}
        onClearSelection={() => {}}
        onOpenDetail={() => {}}
        onPrimarySelectionAction={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        zoneId="unpaired"
      />,
    );

    const button = screen.getByRole("button", { name: "正在准备确认预览" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(within(button).getByRole("status", { name: "正在准备确认预览" })).toBeInTheDocument();
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
        searchQuery=""
        onSearchQueryChange={() => {}}
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

  test("renders one HeroUI search field inside the zone header", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <WorkbenchZone
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSearchQueryChange={onChange}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        panes={panes}
        searchPending
        searchQuery="陈涛"
        title="未配对"
        tone="warning"
        zoneId="unpaired"
      />,
    );

    const zone = screen.getByTestId("zone-unpaired");
    const searchbox = within(zone).getByRole("searchbox", { name: "搜索未配对区域" });
    expect(searchbox).toHaveValue("陈涛");
    expect(searchbox).toHaveAttribute("maxlength", "200");
    expect(searchbox.closest(".zone-header")).not.toBeNull();
    expect(within(zone).getByLabelText("搜索中")).toBeInTheDocument();

    await user.type(searchbox, "A");
    expect(onChange).toHaveBeenCalled();
  });

  test("requests the next page at the grid end and only shows a manual action after failure", async () => {
    const user = userEvent.setup();
    const onRequestNextPage = vi.fn();
    const observe = vi.fn();
    const disconnect = vi.fn();
    let observerCallback: IntersectionObserverCallback | null = null;

    vi.stubGlobal("IntersectionObserver", class {
      constructor(callback: IntersectionObserverCallback) {
        observerCallback = callback;
      }

      observe = observe;
      disconnect = disconnect;
      unobserve = vi.fn();
      takeRecords = () => [];
      root = null;
      rootMargin = "0px";
      thresholds = [0];
    });

    const pageInfo = {
      zone: "unpaired" as const,
      page: 1,
      pageSize: 50,
      total: 205,
      rowCounts: { oa: 69, bank: 68, invoice: 68, rows: 205 },
      hasMore: true,
      readModelStatus: "fresh" as const,
      readModelVersion: "generation-set-1",
    };
    const zone = (
      <WorkbenchZone
        canMutateData
        getRowState={() => "idle"}
        isExpanded={false}
        isVisible
        onOpenDetail={() => {}}
        onRequestNextPage={onRequestNextPage}
        onRowAction={() => {}}
        onSearchQueryChange={() => {}}
        onSelectRow={() => {}}
        onToggleExpand={() => {}}
        pageInfo={pageInfo}
        panes={panes}
        searchQuery=""
        title="未配对"
        tone="warning"
        zoneId="unpaired"
      />
    );
    const { rerender } = render(zone);

    expect(observe).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();
    act(() => {
      observerCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    });
    expect(onRequestNextPage).toHaveBeenCalledWith("unpaired");

    rerender(<WorkbenchZone
      {...zone.props}
      loadMoreError="自动加载下一页失败，请重试。"
    />);
    expect(disconnect).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "重试自动加载" }));
    expect(onRequestNextPage).toHaveBeenCalledTimes(2);

    rerender(<WorkbenchZone
      {...zone.props}
      pageInfo={{ ...pageInfo, readModelStatus: "stale" }}
    />);
    expect(observe).toHaveBeenCalledTimes(1);
  });

  test("uses the native HeroUI zone search and removes the workbench pane-search chain", () => {
    const workbenchStyles = readFileSync(resolve(__dirname, "../app/styles.css"), "utf8");
    const zoneSource = readFileSync(resolve(__dirname, "../components/workbench/WorkbenchZone.tsx"), "utf8");
    const gridSource = readFileSync(resolve(__dirname, "../components/workbench/RelationGroupGrid.tsx"), "utf8");
    const searchRule = workbenchStyles.match(/\.workbench-zone-search\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(zoneSource).toContain("SearchField");
    expect(zoneSource).toContain("SearchField.Group");
    expect(zoneSource).toContain("SearchField.ClearButton");
    expect(gridSource).not.toContain("WorkbenchPaneSearch");
    expect(searchRule).toMatch(/width:\s*clamp\(/);
    expect(searchRule).toMatch(/max-width:\s*320px;/);
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
      "components/workbench/RelationGroupGrid.tsx",
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

  test("does not expose removed automatic-candidate warning state", () => {
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

    expect(screen.queryByLabelText("查看自动匹配警示")).not.toBeInTheDocument();
  });

  test("keeps paired/unpaired zones as the only visible display states", () => {
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
        zoneId="unpaired"
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
        zoneId="unpaired"
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
        zoneId="unpaired"
      />,
    );

    expect(screen.getByRole("button", { name: "放大 未配对" })).toBeInTheDocument();
  });
});
