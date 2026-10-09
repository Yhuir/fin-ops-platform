import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { usePaymentStatusRules, type PaymentStatusRulesPayload } from "../features/inputInvoiceUsage/usePaymentStatusRules";

const payload = (): PaymentStatusRulesPayload => ({ version: 4, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [
  { id: "p1", statusCode: "custom_p1", label: "付款一", description: "", enabled: true, conditions: { hasBank: true } },
  { id: "u1", statusCode: "custom_u1", label: "未付一", description: "", enabled: true, conditions: { hasBank: false } },
  { id: "p2", statusCode: "custom_p2", label: "付款二", description: "", enabled: false, conditions: { hasBank: true } },
  { id: "u2", statusCode: "custom_u2", label: "未付二", description: "", enabled: true, conditions: { hasBank: false } },
] });

describe("grouped payment rule drafts", () => {
  test("reorders by stable ID within a group, rejects cross-group moves and restores a no-op", async () => {
    const loadRules = vi.fn().mockResolvedValue(payload());
    const { result } = renderHook(() => usePaymentStatusRules({ open: true, loadRules, saveRules: vi.fn() }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rules.map(rule => rule.id)).toEqual(["p1", "p2", "u1", "u2"]);
    expect(result.current.dirty).toBe(false);
    act(() => result.current.reorder("p2", "p1"));
    expect(result.current.rules.map(rule => rule.id)).toEqual(["p2", "p1", "u1", "u2"]);
    expect(result.current.rules[0].enabled).toBe(false);
    act(() => { result.current.reorder("p2", "u2"); result.current.reorder("missing", "p1"); });
    expect(result.current.rules.map(rule => rule.id)).toEqual(["p2", "p1", "u1", "u2"]);
    act(() => result.current.reorder("p2", "p1"));
    expect(result.current.dirty).toBe(false);
    await act(() => result.current.save());
    expect(result.current.feedback).toBe("");
    act(() => { result.current.reorder("u2", "u1"); result.current.restore(); });
    expect(result.current.rules.map(rule => rule.id)).toEqual(["p1", "p2", "u1", "u2"]);
  });

  test("an explicit group change appends at the target group end and preserves identity", async () => {
    const loadRules = vi.fn().mockResolvedValue(payload());
    const { result } = renderHook(() => usePaymentStatusRules({ open: true, loadRules, saveRules: vi.fn() }));
    await waitFor(() => expect(result.current.payload).not.toBeNull());
    act(() => result.current.condition(0, { hasBank: false, paymentComparison: undefined }));
    expect(result.current.rules.map(rule => rule.id)).toEqual(["p2", "u1", "u2", "p1"]);
    expect(result.current.rules[3].statusCode).toBe("custom_p1");
    act(() => result.current.add(true, "custom_p2"));
    expect(result.current.rules.map(rule => rule.conditions?.hasBank)).toEqual([true, true, false, false, false]);
    expect(result.current.rules[1].statusCode).toBe("custom_p2");
  });

  test("unchanged retries reuse the submission key, edited payloads get a new key and double-clicks submit once", async () => {
    const loadRules = vi.fn().mockResolvedValue(payload());
    const saveRules = vi.fn().mockRejectedValueOnce(new Error("网络超时")).mockRejectedValueOnce(new Error("网络超时"))
      .mockImplementation(request => Promise.resolve({ ...payload(), version: 5, rules: request.rules }));
    const { result } = renderHook(() => usePaymentStatusRules({ open: true, loadRules, saveRules }));
    await waitFor(() => expect(result.current.payload).not.toBeNull());
    act(() => result.current.reorder("p2", "p1"));
    await act(() => result.current.save());
    expect(result.current.error).toBe("网络超时");
    await act(() => result.current.save());
    expect(saveRules.mock.calls[1][0]).toEqual(saveRules.mock.calls[0][0]);
    act(() => result.current.update(0, { label: "修改后的付款二" }));
    await act(async () => { await Promise.all([result.current.save(), result.current.save()]); });
    expect(saveRules).toHaveBeenCalledTimes(3);
    expect(saveRules.mock.calls[2][0].idempotencyKey).not.toBe(saveRules.mock.calls[0][0].idempotencyKey);
    expect(result.current.dirty).toBe(false);
    expect(result.current.rules[0].label).toBe("修改后的付款二");
  });

  test("read-only drafts cannot reorder or submit", async () => {
    const loadRules = vi.fn().mockResolvedValue({ ...payload(), permissions: { canSave: false } });
    const saveRules = vi.fn();
    const { result } = renderHook(() => usePaymentStatusRules({ open: true, loadRules, saveRules }));
    await waitFor(() => expect(result.current.payload).not.toBeNull());
    act(() => result.current.reorder("p2", "p1"));
    await act(() => result.current.save());
    expect(result.current.rules[0].id).toBe("p1");
    expect(saveRules).not.toHaveBeenCalled();
  });
});
