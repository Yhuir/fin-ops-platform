import { fireEvent, render, screen, within } from "@testing-library/react";

import CandidateGroupCell from "../components/workbench/CandidateGroupCell";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import { getWorkbenchColumns, getWorkbenchPaneGridStyle } from "../features/workbench/tableConfig";
import type { WorkbenchRecord } from "../features/workbench/types";
import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

describe("Workbench candidate grouping layout", () => {
  const invoiceColumns = getWorkbenchColumns("invoice");
  const invoiceGridStyle = getWorkbenchPaneGridStyle("invoice", undefined, true);

  function createInvoiceRecord(id: string, invoiceNo: string): WorkbenchRecord {
    return {
      id,
      caseId: "CASE-SHEET-001",
      recordType: "invoice",
      label: "进项发票",
      status: "待匹配",
      statusCode: "pending_match",
      statusTone: "warn",
      exceptionHandled: false,
      amount: "100.00",
      counterparty: "测试供应商",
      tableValues: {
        sellerName: "测试供应商",
        sellerTaxId: "91330100TEST0001",
        buyerName: "云南溯源科技有限公司",
        buyerTaxId: "915300007194052520",
        invoiceCode: "032002600111",
        invoiceNo,
        issueDate: "2026-04-14",
        amount: "100.00",
        taxRate: "13%",
        taxAmount: "13.00",
        grossAmount: "113.00",
        invoiceType: "进",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
  }

  function getZoneGroupOrder(zone: HTMLElement) {
    return Array.from(zone.querySelectorAll<HTMLElement>(".candidate-grid-body > [data-testid^='candidate-group-']")).map(
      (element) => element.getAttribute("data-testid") ?? "",
    );
  }

  test("renders OA, bank, and invoice candidates on the same horizontal group row", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-101");

    expect(within(groupRow).getByText("陈涛")).toBeInTheDocument();
    expect(within(groupRow).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);
    expect(within(groupRow).getAllByText("58,000.00").length).toBeGreaterThan(0);
    expect(within(groupRow).getByText("进")).toBeInTheDocument();
  });

  test("renders each candidate group as a shared sheet band instead of isolated cards", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupedRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-101");
    const emptyRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");

    const oaCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-oa");
    const bankCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-bank");
    const invoiceCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-invoice");
    const bankRow = within(bankCell).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ });
    const emptyBankCell = within(emptyRow).getByTestId("candidate-scroll-open-row:oa-o-202603-002-bank");

    expect(groupedRow).toHaveClass("candidate-group-row-sheet");
    expect(oaCell).toHaveClass("candidate-group-cell-sheet");
    expect(bankCell).toHaveClass("candidate-group-cell-sheet");
    expect(invoiceCell).toHaveClass("candidate-group-cell-sheet");
    expect(bankRow).toHaveClass("record-card-sheet-row");
    expect(emptyBankCell).toHaveClass("candidate-group-cell-empty-sheet");
  });

  test("cycles subtle sheet tones across adjacent candidate groups", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const rows = await screen.findAllByTestId(/candidate-group-open-/);
    expect(rows[0]).toHaveClass("candidate-group-row-tone-0");
    expect(rows[1]).toHaveClass("candidate-group-row-tone-1");
    expect(rows[2]).toHaveClass("candidate-group-row-tone-2");
    expect(rows[3]).toHaveClass("candidate-group-row-tone-3");
  });

  test("uses stretched sheet rows for single records and split sheet rows for multiple records", () => {
    render(
      <div>
        <CandidateGroupCell
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          getRowState={() => "idle"}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          records={[createInvoiceRecord("single-invoice", "INV-SINGLE-001")]}
          scrollPaneId="invoice"
          scrollTestId="sheet-single"
          showWorkflowActions
          zoneId="open"
        />
        <CandidateGroupCell
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          getRowState={() => "idle"}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          records={[
            createInvoiceRecord("multi-invoice-1", "INV-MULTI-001"),
            createInvoiceRecord("multi-invoice-2", "INV-MULTI-002"),
          ]}
          scrollPaneId="invoice"
          scrollTestId="sheet-multi"
          showWorkflowActions
          zoneId="open"
        />
      </div>,
    );

    const singleCell = screen.getByTestId("sheet-single");
    const multiCell = screen.getByTestId("sheet-multi");
    const singleRow = within(singleCell).getAllByRole("row")[0];
    const multiRows = within(multiCell).getAllByRole("row");

    expect(singleCell).toHaveClass("candidate-group-cell-sheet-single");
    expect(singleRow).toHaveClass("record-card-sheet-row-stretched");
    expect(multiCell).toHaveClass("candidate-group-cell-sheet-multi");
    expect(multiRows[0]).toHaveClass("record-card-sheet-row-split");
    expect(multiRows[1]).toHaveClass("record-card-sheet-row-split");
  });

  test("keeps selected related and highlighted rows compatible with sheet state classes", () => {
    render(
      <div>
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted={false}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-selected", "INV-STATE-001")}
          rowState="selected"
          showWorkflowActions
          zoneId="open"
        />
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted={false}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-related", "INV-STATE-002")}
          rowState="related"
          showWorkflowActions
          zoneId="open"
        />
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-highlight", "INV-STATE-003")}
          rowState="idle"
          showWorkflowActions
          zoneId="open"
        />
      </div>,
    );

    const selectedRow = screen.getByRole("row", { name: /INV-STATE-001/ });
    const relatedRow = screen.getByRole("row", { name: /INV-STATE-002/ });
    const highlightedRow = screen.getByRole("row", { name: /INV-STATE-003/ });

    expect(selectedRow).toHaveClass("record-card-sheet-selected");
    expect(relatedRow).toHaveClass("record-card-sheet-related");
    expect(highlightedRow).toHaveClass("record-card-sheet-highlighted");
  });

  test("renders blank cells when a candidate group is missing bank and invoice records", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");
    const emptyCells = within(groupRow).getAllByText("-");

    expect(within(groupRow).getByText("孙悦")).toBeInTheDocument();
    expect(emptyCells).toHaveLength(2);
  });

  test("shows aggregated OA attachment invoice diagnostics on the invoice pane title", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const invoicePane = within(openZone).getByTestId("pane-invoice");
    const groupRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");
    const diagnostics = within(invoicePane).getByRole("button", { name: "进销项发票附件统计：OA附件 1，已解析 0，已导入 2" });

    expect(diagnostics).toHaveTextContent("进销项发票");
    expect(within(invoicePane).getByText("OA里的发票附件数量")).toBeInTheDocument();
    expect(within(invoicePane).getByText("已解析的OA发票数量")).toBeInTheDocument();
    expect(within(invoicePane).getByText("已导入的发票数量")).toBeInTheDocument();
    expect(within(groupRow).queryByRole("button", { name: /附件统计/ })).not.toBeInTheDocument();
  });

  test("syncs pane header and candidate blocks from a single bottom scrollbar", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const headerScroll = await screen.findByTestId("pane-scroll-head-open-bank");
    const footerScroll = screen.getByTestId("pane-scrollbar-open-bank");
    const groupScroll = screen.getByTestId("candidate-scroll-open-case:CASE-202603-101-bank");

    fireEvent.scroll(footerScroll, { target: { scrollLeft: 96 } });

    expect(headerScroll.scrollLeft).toBe(96);
    expect(groupScroll.scrollLeft).toBe(96);
  });

  test("toggles bank and invoice group sorting in open and paired zones", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const pairedZone = await screen.findByTestId("zone-paired");
    const openBankPane = within(openZone).getByTestId("pane-bank");
    const pairedInvoicePane = within(pairedZone).getByTestId("pane-invoice");

    fireEvent.click(within(openBankPane).getByRole("button", { name: "银行流水按时间降序" }));

    const openDescOrder = getZoneGroupOrder(openZone);
    expect(openDescOrder.indexOf("candidate-group-open-case:CASE-202604-101")).toBeLessThan(
      openDescOrder.indexOf("candidate-group-open-case:CASE-202603-101"),
    );
    expect(openDescOrder.indexOf("candidate-group-open-row:oa-o-202603-002")).toBeGreaterThan(
      openDescOrder.indexOf("candidate-group-open-case:CASE-202603-101"),
    );

    fireEvent.click(within(openBankPane).getByRole("button", { name: "银行流水按时间升序" }));

    const openAscOrder = getZoneGroupOrder(openZone);
    expect(openAscOrder.indexOf("candidate-group-open-case:CASE-202603-101")).toBeLessThan(
      openAscOrder.indexOf("candidate-group-open-case:CASE-202604-101"),
    );

    fireEvent.click(within(pairedInvoicePane).getByRole("button", { name: "进销项发票按时间降序" }));

    const pairedDescOrder = getZoneGroupOrder(pairedZone);
    expect(pairedDescOrder.indexOf("candidate-group-paired-case:CASE-202604-001")).toBeLessThan(
      pairedDescOrder.indexOf("candidate-group-paired-case:CASE-202603-001"),
    );

    fireEvent.click(within(pairedInvoicePane).getByRole("button", { name: "进销项发票按时间升序" }));

    const pairedAscOrder = getZoneGroupOrder(pairedZone);
    expect(pairedAscOrder.indexOf("candidate-group-paired-case:CASE-202603-001")).toBeLessThan(
      pairedAscOrder.indexOf("candidate-group-paired-case:CASE-202604-001"),
    );
  });
});
