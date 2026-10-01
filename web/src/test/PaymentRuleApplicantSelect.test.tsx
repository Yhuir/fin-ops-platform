import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";
import PaymentRuleApplicantSelect from "../components/inputInvoiceUsage/PaymentRuleApplicantSelect";
import type { PaymentRuleApplicantOption } from "../features/inputInvoiceUsage/types";

const options: PaymentRuleApplicantOption[] = [
  { userId: "1", name: "黄 亮", account: "HUANG", enabled: true, matchName: "黄亮" },
  { userId: "2", name: "黄亮", account: "HUANG_OLD", enabled: false, matchName: "黄亮" },
  { userId: "3", name: "李四", account: "LI", enabled: false, matchName: "李四" },
];
function Harness() {
  const [names, setNames] = useState(["黄亮", "目录外人员"]);
  return <PaymentRuleApplicantSelect label="申请人条件" options={options} names={names} onChange={setNames} />;
}

describe("payment rule account choices", () => {
  test("filtered disabled account toggles its name group without dropping directory-external conditions", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByLabelText("申请人条件"));
    const search = screen.getByRole("searchbox", { name: "搜索申请人姓名或账号" });
    await user.type(search, "huang_old");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    await user.click(screen.getByRole("option", { name: "黄亮 HUANG_OLD" }));
    await user.clear(search);
    await waitFor(() => expect(screen.getByRole("option", { name: "黄 亮 HUANG" })).toHaveAttribute("aria-selected", "false"));
    await user.click(screen.getByRole("option", { name: "李四 LI" }));
    await user.keyboard("{Escape}");
    expect(screen.getByLabelText("申请人条件")).toHaveTextContent("目录外人员、李四");
    expect(screen.getByText("目录外人员（不在 OA 目录）")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "移除" }));
    expect(screen.getByLabelText("申请人条件")).toHaveTextContent("李四");
  });

  test("status refresh preserves the selected name and exposes read-only status", async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    const { rerender } = render(<PaymentRuleApplicantSelect label="申请人条件" options={options} names={["黄亮"]} onChange={change} />);
    rerender(<PaymentRuleApplicantSelect label="申请人条件" options={options.map((option) => ({ ...option, enabled: false }))} names={["黄亮"]} onChange={change} />);
    await user.click(screen.getByLabelText("申请人条件"));
    expect(screen.getAllByRole("img", { name: "账号已停用" })).toHaveLength(3);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "黄 亮 HUANG" })).toHaveAttribute("aria-selected", "true");
    expect(change).not.toHaveBeenCalled();
    await user.type(screen.getByRole("searchbox"), "不存在");
    expect(await screen.findByText("没有匹配的用户")).toBeInTheDocument();
  });
});
