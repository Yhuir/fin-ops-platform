import { fireEvent, screen, within } from "@testing-library/react";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

describe("Workbench candidate grouping layout", () => {
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

  test("renders blank cells when a candidate group is missing bank and invoice records", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");
    const emptyCells = within(groupRow).getAllByText("当前栏暂无候选");

    expect(within(groupRow).getByText("孙悦")).toBeInTheDocument();
    expect(emptyCells).toHaveLength(2);
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
