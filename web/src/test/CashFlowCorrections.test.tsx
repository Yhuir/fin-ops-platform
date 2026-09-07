import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CashFlowCorrections, mergeCashCorrectionVersions, type CashFlowCorrectionValue } from "../components/cash/CashFlowCorrections";
import { type CashItem, type CashSettlement } from "../components/cash/CashItems.types";
import { cashRequest, CashRequestError } from "../features/cash/api";
import { CashProvider } from "../features/cash/hooks";

vi.mock("../features/cash/api", async importOriginal => ({ ...await importOriginal<typeof import("../features/cash/api")>(), cashRequest: vi.fn() }));
const request = vi.mocked(cashRequest);
const loan = { id: "loan-1", version: 3, type: "loan", original_amount: "100.00", content: "真实借款", origin_flow_id: "flow-1", origin_mode: "created" } as CashItem;
const child = { id: "expense-1", version: 5, type: "expense", original_amount: "50.00", content: "真实差旅费用", related_obligation_id: loan.id } as CashItem;
const settlement: CashSettlement = { id: "settlement-1", version: 2, kind: "ticket_offset", occurred_on: "2026-09-05", amount: "20.00", remark: "原票抵说明",
  item_id: loan.id, item_version: 3, item_content: loan.content, source_item_id: "ticket-1", source_item_version: 6,
  source_item_content: "真实票据", flow_id: null, flow_version: null, flow_source_kind: null, task: null };
function page<T>(rows: T[], number = 1, total = rows.length) { return { rows, pagination: { page: number, page_size: 20, total } }; }
async function select(label: string, option: string) {
  const user = userEvent.setup();
  await user.click(screen.getByLabelText(label));
  await user.click(await screen.findByRole("option", { name: option }));
}
function setup(mode: "edit" | "delete" = "delete") {
  const onChange = vi.fn<(value: CashFlowCorrectionValue) => void>(); const onValidityChange = vi.fn();
  const tree = render(<CashProvider><CashFlowCorrections flowId="flow-1" mode={mode} onChange={onChange} onValidityChange={onValidityChange} /></CashProvider>);
  return { ...tree, onChange, onValidityChange, latest: () => onChange.mock.calls.at(-1)![0] };
}
beforeEach(() => {
  request.mockReset();
  request.mockImplementation(async path => {
    const url = new URL(path, "http://synthetic.test");
    if (url.pathname === "/items" && url.searchParams.has("origin_flow_id")) return page([loan]);
    if (url.pathname === "/items" && url.searchParams.has("related_obligation_id")) return page([child]);
    if (url.pathname === "/settlements") return page([settlement]);
    if (url.pathname === "/flows") return page([{ id: "flow-2", version: 8, occurred_on: "2026-09-01", content: "正确现金来源", amount: "100.00", kind: "payment", task: { occurrence_id: "occurrence-1", occurrence_version: 4 } }]);
    throw new Error(`Unexpected test request: ${path}`);
  });
});
afterEach(cleanup);

describe("cash flow source corrections", () => {
  it("starts without inferred actions, collects keep-independent without writing, and can cancel it", async () => {
    const result = setup();
    await screen.findByRole("button", { name: "更正来源" });
    expect(result.latest().source_corrections).toEqual([]);
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "更正来源" }));
    await waitFor(() => expect(result.onValidityChange).toHaveBeenLastCalledWith(false));
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请明确选择");
    await select("来源处理方式", "保留真实事项，解除错误来源");
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    await waitFor(() => expect(result.latest().source_corrections).toEqual([{ action: "keep_independent", item_id: loan.id, expected_version: 3 }]));
    expect(result.latest().expected_related_versions.items).toEqual([{ id: loan.id, version: 3 }]);
    expect(result.onValidityChange).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "取消此纠错" }));
    await waitFor(() => expect(result.latest().source_corrections).toEqual([]));
    expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it("requires an explicit replacement flow and preserves its task version", async () => {
    const result = setup();
    fireEvent.click(await screen.findByRole("button", { name: "更正来源" }));
    await select("来源处理方式", "改绑另一笔正确现金");
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("选择正确来源");
    fireEvent.click(screen.getByRole("button", { name: "选择正确流水" }));
    fireEvent.click(await screen.findByRole("button", { name: /正确现金来源/ }));
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    await waitFor(() => expect(result.latest().source_corrections).toEqual([{ action: "rebind_flow", item_id: loan.id, expected_version: 3, new_flow_id: "flow-2", expected_new_flow_version: 8 }]));
    expect(result.latest().expected_related_versions.occurrences).toEqual([{ id: "occurrence-1", version: 4 }]);
    expect(result.latest().expected_related_versions.flows).toEqual([{ id: "flow-2", version: 8 }]);
  });

  it("offers amount correction only in edit mode and rejects invalid money", async () => {
    const result = setup("edit");
    fireEvent.click(await screen.findByRole("button", { name: "更正来源" }));
    await select("来源处理方式", "更正来源事项金额");
    fireEvent.change(screen.getByLabelText("正确原始金额"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("金额必须大于零");
    fireEvent.change(screen.getByLabelText("正确原始金额"), { target: { value: "80.1" } });
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    await waitFor(() => expect(result.latest().source_corrections).toEqual([{ action: "correct_amount", item_id: loan.id, expected_version: 3, original_amount: "80.10" }]));
  });

  it("never offers amount correction while deleting the source", async () => {
    setup("delete");
    fireEvent.click(await screen.findByRole("button", { name: "更正来源" }));
    await userEvent.setup().click(screen.getByLabelText("来源处理方式"));
    expect(await screen.findByRole("option", { name: "改绑另一笔正确现金" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "更正来源事项金额" })).not.toBeInTheDocument();
  });

  it("rejects an unchanged settlement edit instead of sending redundant fields", async () => {
    const result = setup();
    fireEvent.click(await screen.findByRole("button", { name: "后续处理与引用" }));
    fireEvent.click(await screen.findByRole("button", { name: "更正此处理" }));
    await select("处理记录纠错方式", "更正真实处理");
    fireEvent.click(screen.getByRole("button", { name: "采用处理纠错" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("尚未修改");
    expect(result.latest().settlement_changes).toEqual([]);
    expect(result.onValidityChange).toHaveBeenLastCalledWith(false);
  });

  it("turns actual ticket offset into ticket use with exact old object versions", async () => {
    const result = setup();
    fireEvent.click(await screen.findByRole("button", { name: "后续处理与引用" }));
    fireEvent.click(await screen.findByRole("button", { name: "更正此处理" }));
    await select("处理记录纠错方式", "更正真实处理");
    await select("更正后处理类型", "票据使用");
    fireEvent.click(screen.getByRole("button", { name: "采用处理纠错" }));
    await waitFor(() => expect(result.latest().settlement_changes).toEqual([{ id: settlement.id, expected_version: 2, action: "update", fields: { kind: "ticket_use", item_id: null } }]));
    expect(result.latest().expected_related_versions.items).toEqual([{ id: loan.id, version: 3 }, { id: "ticket-1", version: 6 }]);
  });

  it("collects explicit settlement removal and child-reference detach without deleting either now", async () => {
    const result = setup();
    fireEvent.click(await screen.findByRole("button", { name: "后续处理与引用" }));
    fireEvent.click(await screen.findByRole("button", { name: "更正此处理" }));
    await select("处理记录纠错方式", "移除误录的处理 / 分配");
    fireEvent.click(screen.getByRole("button", { name: "采用处理纠错" }));
    fireEvent.click(screen.getByRole("tab", { name: "子事项引用" }));
    fireEvent.click(await screen.findByRole("button", { name: "更正引用" }));
    await select("引用处理方式", "解除错误引用，保留真实子事项");
    fireEvent.click(screen.getByRole("button", { name: "采用引用纠错" }));
    await waitFor(() => expect(result.latest().item_reference_changes).toEqual([{ item_id: child.id, expected_version: 5, related_obligation_id: null }]));
    expect(result.latest().settlement_changes).toEqual([{ id: settlement.id, expected_version: 2, action: "remove" }]);
    expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it("reads later source pages on demand instead of treating a 20-row preview as complete", async () => {
    request.mockImplementation(async path => {
      const query = new URL(path, "http://synthetic.test").searchParams;
      return query.get("page") === "2" ? page([{ ...loan, id: "loan-21", content: "第二页事项" }], 2, 21) : page([loan], 1, 21);
    });
    setup();
    await screen.findByRole("button", { name: "更正来源" });
    fireEvent.click(screen.getByRole("button", { name: /下一页/ }));
    expect(await screen.findByText(/第二页事项/)).toBeInTheDocument();
    expect(request.mock.calls.some(([path]) => path.includes("origin_flow_id=flow-1") && path.includes("page=2"))).toBe(true);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("shows load failure without fake empty success and retries only reads", async () => {
    request.mockRejectedValueOnce(new CashRequestError(503, "cash_storage_unavailable", "现金服务暂不可用"));
    setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("现金服务暂不可用");
    expect(screen.queryByText("本笔现金没有来源事项。")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取关联" }));
    expect(await screen.findByRole("button", { name: "更正来源" })).toBeInTheDocument();
  });

  it("resets corrections when moving to another flow and aborts old reads", async () => {
    const result = setup();
    fireEvent.click(await screen.findByRole("button", { name: "更正来源" }));
    await select("来源处理方式", "删除误录事项，保留真实其他现金");
    fireEvent.click(screen.getByRole("button", { name: "采用来源纠错" }));
    await screen.findByRole("region", { name: "待提交纠错" });
    const signal = request.mock.calls[0][1]?.signal;
    result.rerender(<CashProvider><CashFlowCorrections flowId="flow-2" mode="delete" onChange={result.onChange} /></CashProvider>);
    await waitFor(() => expect(result.latest().source_corrections).toEqual([]));
    expect(signal?.aborted).toBe(true);
  });

  it("deduplicates matching versions and refuses mixed snapshots", () => {
    const first = { items: [{ id: "a", version: 1 }], flows: [], occurrences: [] };
    expect(mergeCashCorrectionVersions([first, first])).toEqual(first);
    expect(() => mergeCashCorrectionVersions([first, { ...first, items: [{ id: "a", version: 2 }] }])).toThrow("发生变化");
  });
});
