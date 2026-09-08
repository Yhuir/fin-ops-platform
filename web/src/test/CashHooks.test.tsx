import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { CashProvider, useCashMutation, useCashQuery } from "../features/cash/hooks";
import { apiFetch } from "../features/apiClient";
import type { CashQueryParams } from "../features/cash/api";

vi.mock("../features/apiClient", () => ({ apiFetch: vi.fn() }));
const fetcher = vi.mocked(apiFetch);
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
function Probe({ keyword = "one" }: { keyword?: string }) {
  const query = useCashQuery<{ value: string }>("/items", { keyword });
  const mutation = useCashMutation();
  return <><span>{query.data?.value}</span><span>{query.loading ? "读取中" : "已读取"}</span>
    {query.error && <p role="alert">{query.error.message}</p>}
    <button onClick={query.reload}>刷新</button><button disabled={mutation.busy} onClick={() => void mutation.run("/flows", { id: "stable" })}>保存</button>
  </>;
}
function QueryProbe({ params }: { params: CashQueryParams }) {
  const query = useCashQuery<{ value: string }>("/flows", params);
  return <><span>{query.data?.value}</span><span>{query.loading ? "读取中" : "已读取"}</span>{query.error && <p role="alert">{query.error.message}</p>}<button onClick={query.reload}>刷新筛选</button></>;
}
afterEach(() => vi.clearAllMocks());
describe("cash scope lifecycle", () => {
  test("serializes multi-value and null filters as one JSON key, omitting unrestricted arrays", async () => {
    fetcher.mockResolvedValueOnce(response({ value: "filtered" }));
    render(<CashProvider><QueryProbe params={{ account_ids: ["account-a", "account-b"], project_ids: ["项目甲", null], category_ids: [], kinds: ["receipt", "payment"], page: 2 }} /></CashProvider>);
    await screen.findByText("filtered");
    expect(fetcher).toHaveBeenCalledTimes(1);
    const params = new URL(fetcher.mock.calls[0][0], "http://test").searchParams;
    expect(params.getAll("account_ids")).toEqual(['["account-a","account-b"]']);
    expect(JSON.parse(params.get("project_ids")!)).toEqual(["项目甲", null]);
    expect(params.has("category_ids")).toBe(false);
    expect(params.get("kinds")).toBe('["receipt","payment"]');
    expect(params.get("page")).toBe("2");
    expect(fetcher.mock.calls[0][1]?.cache).toBe("no-store");
  });

  test.each([
    { params: { account_ids: Array.from({ length: 51 }, (_, i) => `account-${i}`) }, message: /每列最多选择/ },
    { params: { account_ids: Array.from({ length: 50 }, (_, i) => `a-${i}`), category_ids: Array.from({ length: 50 }, (_, i) => `c-${i}`), kinds: ["receipt"] }, message: /全部条件最多选择/ },
    { params: { project_ids: Array.from({ length: 20 }, (_, i) => `${i}${"长".repeat(40)}`) }, message: /筛选条件过长/ },
  ])("invalid filter limits are shown locally without issuing HTTP ($message)", async ({ params, message }) => {
    render(<CashProvider><QueryProbe params={params} /></CashProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByText("已读取")).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("刷新筛选"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(fetcher).not.toHaveBeenCalled();
  });

  test("an over-limit change aborts the prior query and recovers after conditions are cleared", async () => {
    let pending!: (value: Response) => void;
    fetcher.mockImplementationOnce(() => new Promise(resolve => { pending = resolve; })).mockResolvedValueOnce(response({ value: "recovered" }));
    const view = render(<CashProvider><QueryProbe params={{ project_ids: ["old-project"] }} /></CashProvider>);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    view.rerender(<CashProvider><QueryProbe params={{ project_ids: Array.from({ length: 51 }, (_, i) => `project-${i}`) }} /></CashProvider>);
    await screen.findByRole("alert");
    expect((fetcher.mock.calls[0][1]?.signal as AbortSignal).aborted).toBe(true);
    await act(async () => pending(response({ value: "obsolete" })));
    expect(screen.queryByText("obsolete")).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    view.rerender(<CashProvider><QueryProbe params={{ project_ids: [] }} /></CashProvider>);
    await screen.findByText("recovered");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.at(-1)![0]).toBe("/api/cash/flows");
  });

  test("discards previous response when a newer filter is selected", async () => {
    let first!: (value: Response) => void;
    fetcher.mockImplementationOnce(() => new Promise(resolve => { first = resolve; })).mockResolvedValueOnce(response({ value: "new" }));
    const view = render(<CashProvider><Probe /></CashProvider>);
    view.rerender(<CashProvider><Probe keyword="two" /></CashProvider>);
    await screen.findByText("new");
    await act(async () => first(response({ value: "old" })));
    expect(screen.queryByText("old")).not.toBeInTheDocument();
    expect((fetcher.mock.calls[0][1]?.signal as AbortSignal).aborted).toBe(true);
  });
  test("clears all sensitive children and cancels pending requests after permission denial", async () => {
    fetcher.mockResolvedValueOnce(response({ value: "private cash" })).mockResolvedValueOnce(response({ error: "cash_access_denied", message: "denied" }, 403));
    render(<CashProvider><Probe /></CashProvider>);
    await screen.findByText("private cash"); fireEvent.click(screen.getByText("刷新"));
    await screen.findByText(/页面数据已清除/);
    expect(screen.queryByText("private cash")).not.toBeInTheDocument(); expect(screen.queryByText("保存")).not.toBeInTheDocument();
  });
  test("a successful mutation invalidates only local cash queries; no global event or storage writes", async () => {
    const event = vi.spyOn(window, "dispatchEvent"); const storage = vi.spyOn(Storage.prototype, "setItem");
    fetcher.mockResolvedValueOnce(response({ value: "before" })).mockResolvedValueOnce(response({ saved: true })).mockResolvedValueOnce(response({ value: "after" }));
    render(<CashProvider><Probe /></CashProvider>);
    await screen.findByText("before"); fireEvent.click(screen.getByText("保存")); await screen.findByText("after");
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(["/api/cash/items?keyword=one", "/api/cash/flows", "/api/cash/items?keyword=one"]);
    expect(event).not.toHaveBeenCalled(); expect(storage).not.toHaveBeenCalled(); event.mockRestore(); storage.mockRestore();
  });
  test("prevents duplicate in-flight mutation and aborts on unmount", async () => {
    fetcher.mockResolvedValueOnce(response({ value: "loaded" })).mockImplementationOnce((_path, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
    const view = render(<CashProvider><Probe /></CashProvider>); await screen.findByText("loaded");
    fireEvent.click(screen.getByText("保存")); fireEvent.click(screen.getByText("保存"));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2)); view.unmount();
    expect((fetcher.mock.calls[1][1]?.signal as AbortSignal).aborted).toBe(true);
  });
});
