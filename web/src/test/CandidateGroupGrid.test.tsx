import { fireEvent, screen, within } from "@testing-library/react";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

describe("Workbench candidate grouping layout", () => {
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
});
