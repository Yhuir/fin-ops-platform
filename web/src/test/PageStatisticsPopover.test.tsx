import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PageStatisticsPopover from "../components/common/PageStatisticsPopover";

describe("PageStatisticsPopover", () => {
  test("formats full counts, preserves zero, and opens details", async () => {
    const user = userEvent.setup();
    render(
      <PageStatisticsPopover
        ariaLabel="银行明细数据统计"
        coreItems={[
          { label: "流水", value: 10000, unit: "笔" },
          { label: "收入", value: 0, unit: "笔", tone: "income" },
        ]}
        detailItems={[{ label: "未分类流水", value: 2800, unit: "笔", tone: "warning" }]}
      />,
    );

    expect(screen.getByText("10,000")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "银行明细数据统计" }));
    expect(await screen.findByText("未分类流水")).toBeInTheDocument();
    expect(screen.getByText("2,800")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByText("未分类流水")).not.toBeInTheDocument();
  });

  test("shows a dash for unavailable counts instead of a false zero", () => {
    render(
      <PageStatisticsPopover
        ariaLabel="数据统计"
        coreItems={[{ label: "流水", value: null, unit: "笔" }]}
        detailItems={[]}
      />,
    );

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("笔")).not.toBeInTheDocument();
  });

  test("rejects negative and fractional values at the shared display boundary", () => {
    render(
      <PageStatisticsPopover
        ariaLabel="数据统计"
        coreItems={[
          { label: "流水", value: -1, unit: "笔" },
          { label: "发票", value: 1.5, unit: "张" },
        ]}
        detailItems={[]}
      />,
    );

    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.queryByText("笔")).not.toBeInTheDocument();
    expect(screen.queryByText("张")).not.toBeInTheDocument();
  });

  test("renders a first-load skeleton", () => {
    render(
      <PageStatisticsPopover
        ariaLabel="数据统计"
        coreItems={[]}
        detailItems={[]}
        loading
      />,
    );

    expect(screen.getByRole("status", { name: "数据统计加载中" })).toBeInTheDocument();
  });
});
