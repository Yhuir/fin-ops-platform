import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import InvoiceUsageClassification, { type InvoiceUsageClassificationData } from "../components/inputInvoiceUsage/InvoiceUsageClassification";

const data: InvoiceUsageClassificationData = {
  all: { id: "all", label: "全部发票", count: 30 },
  used: { id: "used", label: "已使用", count: 20 },
  unused: { id: "unused", label: "待使用", count: 10 },
  groups: [{
    id: "paid", label: "已付款", count: 20, tone: "paid",
    children: Array.from({ length: 10 }, (_, index) => ({ id: `category-${index}`, label: `分类 ${index + 1}`, count: 2 })),
  }, {
    id: "unpaid", label: "未付款", count: 0, tone: "unpaid", children: [],
  }],
};

describe("invoice usage classification", () => {
  test("keeps all dynamic categories inside their parent and selects by stable identity", async () => {
    const onSelect = vi.fn();
    render(<InvoiceUsageClassification data={data} selectedId="category-9" onSelect={onSelect} />);
    const paid = screen.getByRole("group", { name: "已付款" });
    expect(within(paid).getAllByRole("button")).toHaveLength(11);
    expect(within(paid).getByRole("button", { name: "分类 10 2 张" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "待使用 10 张" }));
    expect(onSelect).toHaveBeenCalledWith("unused");
    expect(screen.getByRole("button", { name: "未付款 0 张" })).toBeEnabled();
  });

  test("refresh retains known counts; failure shows unknown rather than false zero", () => {
    const { rerender } = render(<InvoiceUsageClassification data={data} selectedId="all" pending onSelect={vi.fn()} />);
    expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "全部发票 30 张" })).toBeEnabled();
    rerender(<InvoiceUsageClassification data={data} selectedId="all" invalid onSelect={vi.fn()} />);
    expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("button", { name: "全部发票 — 张" })).toBeDisabled();
  });

  test("rename and removal follow the new configuration without keeping stale buttons", () => {
    const { rerender } = render(<InvoiceUsageClassification data={data} selectedId="category-0" onSelect={vi.fn()} />);
    const renamed = { ...data, groups: [{ ...data.groups[0], children: [{ id: "category-0", label: "现金往来", count: 20 }] }] };
    rerender(<InvoiceUsageClassification data={renamed} selectedId="category-0" onSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: "现金往来 20 张" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "分类 10 2 张" })).not.toBeInTheDocument();
  });
});
