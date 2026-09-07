import { afterEach, describe, expect, test, vi } from "vitest";
import { cashRequest } from "../features/cash/api";
import { apiFetch } from "../features/apiClient";

vi.mock("../features/apiClient", () => ({ apiFetch: vi.fn() }));
const fetcher = vi.mocked(apiFetch);
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });
describe("cash-only HTTP boundary", () => {
  test("uses one authenticated boundary with no-store and exact amount strings", async () => {
    fetcher.mockResolvedValue(new Response(JSON.stringify({ flow: { id: "a", amount: "9999999999999999.99" } }), { status: 201, headers: { "content-type": "application/json" } }));
    const body = { id: "same-submission", amount: "9999999999999999.99" };
    await expect(cashRequest("/flows", { method: "POST", body })).resolves.toEqual({ flow: { id: "a", amount: body.amount } });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith("/api/cash/flows", expect.objectContaining({ method: "POST", cache: "no-store", body: JSON.stringify(body) }));
  });
  test.each(["/../bank-details", "https://example.com", "//flows", "/flows#fragment"])("rejects address escape %s before any IO", async path => {
    await expect(cashRequest(path)).rejects.toMatchObject({ code: "cash_invalid_path" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  test.each([401, 403])("denies %i even if the response is HTML", async status => {
    fetcher.mockResolvedValue(new Response("secret html", { status, headers: { "content-type": "text/html" } }));
    await expect(cashRequest("/flows")).rejects.toMatchObject({ status, code: "cash_access_denied" });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  test("never uses a second API address when the service returns HTML", async () => {
    fetcher.mockResolvedValue(new Response("<html>SPA</html>", { headers: { "content-type": "text/html" } }));
    await expect(cashRequest("/flows")).rejects.toMatchObject({ code: "cash_invalid_response" });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  test.each(["{", "null", "[]"])("rejects malformed payload %s without inventing empty data", async value => {
    fetcher.mockResolvedValue(new Response(value, { headers: { "content-type": "application/json" } }));
    await expect(cashRequest("/flows")).rejects.toMatchObject({ code: "cash_invalid_response" });
  });
  test("preserves conflict code and safe server explanation, never auto-retries a write", async () => {
    fetcher.mockResolvedValue(new Response(JSON.stringify({ error: "cash_submission_deleted", message: "原提交已被删除。" }), { status: 409, headers: { "content-type": "application/json" } }));
    await expect(cashRequest("/flows", { method: "POST", body: { id: "same" } })).rejects.toMatchObject({ status: 409, code: "cash_submission_deleted", message: "原提交已被删除。" });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  test("bounds timeout and states unknown write outcome instead of reporting failure as no-write", async () => {
    vi.useFakeTimers();
    fetcher.mockImplementation((_path, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
    const expectation = expect(cashRequest("/flows", { method: "POST", body: { id: "stable" } })).rejects.toMatchObject({ code: "cash_timeout", message: expect.stringContaining("可能已生效") });
    await vi.advanceTimersByTimeAsync(15_000); await expectation;
    expect(fetcher).toHaveBeenCalledOnce();
  });
});
