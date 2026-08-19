import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import CostExplorerList from "../components/cost-statistics/CostExplorerList";

type Row = {
  id: string;
  name: string;
};

const resizeObservers: MockResizeObserver[] = [];

class MockResizeObserver implements ResizeObserver {
  readonly callback: ResizeObserverCallback;
  readonly observedElements = new Set<Element>();

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    resizeObservers.push(this);
  }

  disconnect = vi.fn();
  observe = vi.fn((element: Element) => {
    this.observedElements.add(element);
  });
  unobserve = vi.fn();
}

const rows: Row[] = [
  { id: "short", name: "云南溯源科技" },
  { id: "long-a", name: "玉溪卷烟厂就地技术改造项目低压配电柜综合采购及安装工程" },
  { id: "long-b", name: "昭通卷烟厂二零二五年至二零二八年度能源集中监控系统维护项目" },
];

function setLabelWidth(text: string, clientWidth: number, scrollWidth: number) {
  const label = screen.getByText(text, { selector: "strong" });
  Object.defineProperties(label, {
    clientWidth: { configurable: true, value: clientWidth },
    scrollWidth: { configurable: true, value: scrollWidth },
  });
}

async function measureOverflow() {
  const listObserver = resizeObservers.find((observer) =>
    [...observer.observedElements].some((element) => element.classList.contains("cost-explorer-list")));
  await act(async () => {
    listObserver?.callback([], listObserver);
  });
}

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
      renderSecondary={() => "1 条归集 / 1 类费用"}
      title="项目名"
    />,
  );

  setLabelWidth(rows[0].name, 180, 120);
  setLabelWidth(rows[1].name, 180, 420);
  setLabelWidth(rows[2].name, 180, 390);
  return { ...rendered, onSelect };
}

beforeEach(() => {
  resizeObservers.length = 0;
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    callback(performance.now());
    return 1;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
});

test("only overflowed labels expose a fixed-height HeroUI disclosure", async () => {
  const user = userEvent.setup();
  const { container, onSelect } = renderList();
  await measureOverflow();

  const disclosures = screen.getAllByRole("button", { name: "展开项目名完整内容" });
  expect(disclosures).toHaveLength(2);
  const firstDisclosure = disclosures[0];
  expect(container.querySelector("button button")).toBeNull();

  await user.click(firstDisclosure);
  const dialog = await screen.findByRole("dialog", { name: "项目名完整内容" });
  expect(dialog).toHaveTextContent(rows[1].name);
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "折叠项目名完整内容" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "折叠项目名完整内容" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "项目名完整内容" })).not.toBeInTheDocument());

  await user.click(screen.getByRole("button", { name: `选择项目名 ${rows[1].name}` }));
  expect(onSelect).toHaveBeenCalledWith(rows[1]);
});

test("keeps at most one full-text popover open and dismisses it with Escape", async () => {
  const user = userEvent.setup();
  renderList();
  await measureOverflow();
  const [firstDisclosure, secondDisclosure] = screen.getAllByRole("button", {
    name: "展开项目名完整内容",
  });

  await user.click(firstDisclosure);
  expect(await screen.findByRole("dialog", { name: "项目名完整内容" })).toHaveTextContent(rows[1].name);

  await user.click(secondDisclosure);
  const dialog = await screen.findByRole("dialog", { name: "项目名完整内容" });
  expect(dialog).toHaveTextContent(rows[2].name);
  expect(dialog).not.toHaveTextContent(rows[1].name);

  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "项目名完整内容" })).not.toBeInTheDocument());
});

test("removes the disclosure and closes its popover when the label stops overflowing", async () => {
  const user = userEvent.setup();
  renderList();
  await measureOverflow();

  await user.click(screen.getAllByRole("button", { name: "展开项目名完整内容" })[0]);
  expect(await screen.findByRole("dialog", { name: "项目名完整内容" })).toBeInTheDocument();

  setLabelWidth(rows[1].name, 460, 420);
  await measureOverflow();

  await waitFor(() => {
    expect(screen.getAllByRole("button", { name: "展开项目名完整内容" })).toHaveLength(1);
    expect(screen.queryByRole("dialog", { name: "项目名完整内容" })).not.toBeInTheDocument();
  });
});
