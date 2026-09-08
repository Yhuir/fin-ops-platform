import { afterEach, describe, expect, test, vi } from "vitest";
import { cashRequest, cashQueryError, cashQueryString } from "../features/cash/api";
import { apiFetch } from "../features/apiClient";

vi.mock("../features/apiClient", () => ({ apiFetch: vi.fn() }));
const fetcher = vi.mocked(apiFetch);
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });
describe("cash-only HTTP boundary", () => {
  test("encodes multi-value filters once, preserves null and omits unrestricted arrays", () => {
    const query = new URLSearchParams(cashQueryString({ project_ids: ["a&b", null, "项目"], kinds: [], page: 2, enabled: false }));
    expect(query.getAll("project_ids")).toEqual([JSON.stringify(["a&b", null, "项目"])]);
    expect(query.has("kinds")).toBe(false);
    expect(query.get("enabled")).toBe("false");
    expect(query.get("page")).toBe("2");
  });
  test("rejects oversized selections and encoded URI before network IO", async () => {
    expect(() => cashQueryString({ account_ids: Array.from({ length: 51 }, (_, i) => String(i)) })).toThrow(/50/);
    expect(() => cashQueryString({ keyword: "项".repeat(1000) })).toThrow(/过长/);
    await expect(cashRequest(`/flows?keyword=${"a".repeat(3493)}`)).rejects.toMatchObject({ code: "cash_filter_limit" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  test("validates complete next criteria without mutating it or swallowing unrelated errors", () => {
    const params = { account_ids: Array.from({ length: 50 }, (_, i) => String(i)), project_ids: Array.from({ length: 50 }, (_, i) => `p${i}`) };
    expect(cashQueryError(params)).toBeNull();
    expect(cashQueryError({ ...params, sources: ["manual"] })).toMatch(/全部条件最多选择 100/);
    expect(cashQueryString({ keyword: "x".repeat(3492) })).toHaveLength(3500);
    expect(cashQueryError({ keyword: "x".repeat(3492) })).toBeNull();
    expect(cashQueryError({ keyword: "x".repeat(3493) })).toMatch(/过长/);
    expect(params.account_ids).toHaveLength(50);
    const broken = { get keyword(): string { throw new Error("unexpected getter failure"); } };
    expect(() => cashQueryError(broken)).toThrow("unexpected getter failure");
    expect(fetcher).not.toHaveBeenCalled();
  });
  test("allows an exactly 3500-byte query through the existing HTTP boundary", async () => {
    fetcher.mockResolvedValue(new Response(JSON.stringify({ rows: [] }), { status: 200, headers: { "content-type": "application/json" } }));
    const path = `/flows?keyword=${"x".repeat(3492)}`;
    await expect(cashRequest(path)).resolves.toEqual({ rows: [] });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(`/api/cash${path}`, expect.objectContaining({ cache: "no-store" }));
  });
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
