import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import CostStatisticsProjectCostScopeDrawer from "../components/cost-statistics/CostStatisticsProjectCostScopeDrawer";

const scope = { version: 1, selected_tag_codes: ["material"], can_save: true, available_tags: [
  { code: "material", label: "材料款", path: ["采购", "材料款"], status: "active", direction: "expense", can_select: true },
  { code: "internal_transfer", label: "内部往来款", path: ["内部往来款"], status: "active", direction: "any", can_select: true },
  { code: "refund", label: "付错退款", path: ["付错退款"], status: "active", direction: "income", can_select: false },
] };
const base = { open: true, scope, selected: scope.selected_tag_codes, loading: false, saving: false, canSave: true,
  unconfirmed: false, error: null, onClose: vi.fn(), onReload: vi.fn(), onChange: vi.fn(), onSave: vi.fn() };

test("shows all tags, allows an empty draft, and keeps income disabled", async () => {
  const onChange = vi.fn(), onSave = vi.fn();
  render(<CostStatisticsProjectCostScopeDrawer {...base} onChange={onChange} onSave={onSave} />);
  const user = userEvent.setup();
  expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  expect(screen.getByRole("checkbox", { name: /付错退款/ })).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: "材料款" }));
  expect(onChange).toHaveBeenCalledWith([]); expect(onSave).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "保存范围" }));
  expect(onSave).toHaveBeenCalledOnce();
  await user.type(screen.getByRole("textbox", { name: "搜索流水标签" }), "内部");
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
});

test("read-only and unknown save result keep choices visible but prevent another write", async () => {
  const { rerender } = render(<CostStatisticsProjectCostScopeDrawer {...base} canSave={false} />);
  expect(screen.getByRole("button", { name: "保存范围" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "材料款" })).toBeChecked();
  rerender(<CostStatisticsProjectCostScopeDrawer {...base} unconfirmed error="保存结果待核实" />);
  await userEvent.click(screen.getByRole("button", { name: "核实保存结果" }));
  expect(base.onReload).toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "保存范围" })).toBeDisabled();
});

test("loading, failed loading and search empty state remain actionable", async () => {
  const { rerender } = render(<CostStatisticsProjectCostScopeDrawer {...base} scope={null} loading />);
  expect(screen.getByRole("status")).toHaveTextContent("正在加载");
  rerender(<CostStatisticsProjectCostScopeDrawer {...base} scope={null} error="加载失败" />);
  expect(screen.getByRole("alert")).toHaveTextContent("加载失败");
  expect(screen.getByRole("button", { name: "保存范围" })).toBeDisabled();
  rerender(<CostStatisticsProjectCostScopeDrawer {...base} />);
  await userEvent.type(screen.getByRole("textbox", { name: "搜索流水标签" }), "不存在的标签");
  expect(screen.getByText("没有匹配的标签")).toBeVisible();
});
