import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { CashProvider, useCashMutation, useCashQuery } from "../features/cash/hooks";
import { apiFetch } from "../features/apiClient";

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
afterEach(() => vi.clearAllMocks());
describe("cash scope lifecycle", () => {
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
