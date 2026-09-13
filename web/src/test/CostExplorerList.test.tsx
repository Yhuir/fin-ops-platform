import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import CostExplorerList from "../components/cost-statistics/CostExplorerList";

type Row = {
  id: string;
  name: string;
};

const rows: Row[] = [
  { id: "short", name: "云南溯源科技" },
  { id: "long-a", name: "玉溪卷烟厂就地技术改造项目低压配电柜综合采购及安装工程" },
  { id: "long-b", name: "昭通卷烟厂二零二五年至二零二八年度能源集中监控系统维护项目" },
];

function renderList(onSelect = vi.fn()) {
  const rendered = render(
    <CostExplorerList<Row>
      count={rows.length}
      emptyLabel="暂无项目"
      getKey={(row) => row.id}
      getPrimaryText={(row) => row.name}
      isActive={(row) => row.id === "short"}
      items={rows}
      onSelect={onSelect}
      renderSecondary={() => "1 类费用"}
      title="项目名"
    />,
  );
  return { ...rendered, onSelect };
}

test("renders complete project names without disclosure controls", () => {
  const { container } = renderList();

  for (const row of rows) {
    expect(screen.getByText(row.name, { selector: "strong" })).toBeVisible();
  }
  expect(screen.queryByText("展开")).not.toBeInTheDocument();
  expect(screen.queryByText("折叠")).not.toBeInTheDocument();
  expect(container.querySelector(".cost-explorer-item-disclosure")).toBeNull();
});

test("uses the HeroUI listbox selection model", async () => {
  const user = userEvent.setup();
  const { onSelect } = renderList();
  const item = screen.getByRole("option", { name: `选择项目名 ${rows[1].name}` });

  await user.click(item);

  expect(onSelect).toHaveBeenCalledWith(rows[1]);
  expect(screen.getByRole("option", { name: `选择项目名 ${rows[0].name}` })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("keeps keyboard selection accessible", async () => {
  const user = userEvent.setup();
  const { onSelect } = renderList();
  const item = screen.getByRole("option", { name: `选择项目名 ${rows[2].name}` });

  act(() => item.focus());
  await user.keyboard("{Enter}");

  expect(onSelect).toHaveBeenCalledWith(rows[2]);
});


test("preserves both amounts and counts and distinguishes loading from empty", () => {
  const props = { title: "主标签", count: 1, items: rows.slice(0, 1), emptyLabel: "没有标签", getKey: (row: Row) => row.id, getPrimaryText: (row: Row) => row.name, isActive: () => false, onSelect: vi.fn(), renderSecondary: () => "2 个子标签", renderMeta: () => <><span>支 120.00</span><span>收 80.00</span></> };
  const { rerender } = render(<CostExplorerList {...props} />);
  expect(screen.getByText("2 个子标签")).toBeVisible();
  expect(screen.getByText("支 120.00")).toBeVisible();
  expect(screen.getByText("收 80.00")).toBeVisible();
  rerender(<CostExplorerList {...props} items={[]} loading />);
  expect(screen.queryByText("没有标签")).not.toBeInTheDocument();
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  rerender(<CostExplorerList {...props} count={0} items={[]} />);
  expect(screen.getByText("没有标签")).toBeVisible();
});


test("activates the already selected item when returning to an ancestor", async () => {
  const user = userEvent.setup();
  const { onSelect } = renderList();
  await user.click(screen.getByRole("option", { name: `选择项目名 ${rows[0].name}` }));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(onSelect).toHaveBeenCalledWith(rows[0]);
});
