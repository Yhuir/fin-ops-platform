import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import InvoiceCountSegments from "../components/common/InvoiceCountSegments";

afterEach(cleanup);
test("keeps owner counts and mounted tabs during loading, updates on success, and distinguishes error from zero", async () => {
  const onChange = vi.fn();
  const props = { label: "数量", unit: "张" as const, selectedKey: "all", onChange };
  const initial = [{ key: "all", label: "全部", count: 432 }, { key: "paid", label: "已收款", count: 0 }];
  const { rerender } = render(<InvoiceCountSegments {...props} options={initial} />);
  const all = screen.getByRole("tab", { name: "全部 432 张" });
  rerender(<InvoiceCountSegments {...props} options={initial} pending />);
  expect(screen.getByRole("tab", { name: "全部 432 张" })).toBe(all);
  expect(all.closest('[aria-busy]')).toHaveAttribute("aria-busy", "true");
  await userEvent.click(screen.getByRole("tab", { name: "已收款 0 张" }));
  expect(onChange).toHaveBeenCalledWith("paid");
  rerender(<InvoiceCountSegments {...props} options={[{ ...initial[0], count: 56 }, initial[1]]} />);
  expect(screen.getByRole("tab", { name: "全部 56 张" })).toBe(all);
  rerender(<InvoiceCountSegments {...props} options={initial} invalid />);
  expect(screen.getByRole("tab", { name: "全部 — 张" })).toBe(all);
  expect(all.closest('[aria-busy]')).toHaveAttribute("aria-busy", "false");
});

test("first loading is unknown rather than a fabricated zero", () => {
  render(<InvoiceCountSegments label="首次加载" unit="笔" selectedKey="all" pending options={[{ key: "all", label: "全部" }]} onChange={() => undefined} />);
  expect(screen.getByRole("tab", { name: "全部 — 笔" })).toBeVisible();
  expect(screen.queryByRole("tab", { name: "全部 0 笔" })).not.toBeInTheDocument();
});
