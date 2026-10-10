import { act, cleanup, render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fetchBankFlowRuleBatchDetail } from "../features/bankFlowRuleBatches/api";
import BatchExpansion from "../features/bankFlowRuleBatches/BatchExpansion";
import { useBatchExpansion } from "../features/bankFlowRuleBatches/useBatchExpansion";
import type { BankFlowRuleBatch, BankFlowRuleBatchDetail } from "../features/bankFlowRuleBatches/types";

vi.mock("../features/bankFlowRuleBatches/api", () => ({ fetchBankFlowRuleBatchDetail: vi.fn() }));
const fetchDetail = vi.mocked(fetchBankFlowRuleBatchDetail);
function batch(batchId: string): BankFlowRuleBatch {
  return { batchId, batchType: "fee", batchLabel: "手续费", scopeMonth: "2026-05", accountKey: "ccb:8106",
    bankName: "建设银行", accountLast4: "8106", status: "draft", statusBucket: "unsubmitted",
    rowCount: 1, totalAmount: "8.80", tagCounts: {}, directionCounts: {}, canSubmit: true, canWithdraw: false,
    submittedBy: "", submittedAt: null, withdrawnBy: "", withdrawnAt: null,
    conflictReason: "", blockedReason: "", version: null };
}
const batches = [batch("A"), batch("B")];
const detail = (id: string): BankFlowRuleBatchDetail => ({ batch: batch(id), rows: [], tagCounts: {}, directionCounts: {} });
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => { resolve = yes; });
  return { promise, resolve };
}
const defaults = { batches, bucket: "unsubmitted" as const, enabled: true, scopeKey: "all:unsubmitted:1", snapshotVersion: 1 };
beforeEach(() => fetchDetail.mockReset());
afterEach(cleanup);

describe("batch detail expansion", () => {
  test("starts collapsed, loads independently and caches reopened batches within one scope", async () => {
    const a = pending<BankFlowRuleBatchDetail>(); const b = pending<BankFlowRuleBatchDetail>();
    fetchDetail.mockImplementation((id) => id === "A" ? a.promise : b.promise);
    const { result } = renderHook(() => useBatchExpansion(defaults));
    expect(result.current.expandedIds.size).toBe(0); expect(fetchDetail).not.toHaveBeenCalled();
    act(() => result.current.toggle("A")); act(() => result.current.toggle("B"));
    expect([...result.current.expandedIds]).toEqual(["A", "B"]);
    expect(fetchDetail).toHaveBeenCalledTimes(2);
    expect(fetchDetail).toHaveBeenCalledWith("A", "2026-05", "candidate", expect.any(AbortSignal));
    await act(async () => b.resolve(detail("B")));
    expect(result.current.details.B.batch.batchId).toBe("B"); expect(result.current.loadingIds.has("A")).toBe(true);
    await act(async () => a.resolve(detail("A")));
    act(() => result.current.toggle("A")); expect([...result.current.expandedIds]).toEqual(["B"]);
    act(() => result.current.onExited("A")); expect(result.current.mountedIds.has("A")).toBe(false);
    act(() => result.current.toggle("A")); expect(fetchDetail).toHaveBeenCalledTimes(2);
    act(() => result.current.collapseAll()); expect(result.current.expandedIds.size).toBe(0);
  });

  test("cancelled response cannot overwrite a rapid reopen of the same batch", async () => {
    const first = pending<BankFlowRuleBatchDetail>(); const second = pending<BankFlowRuleBatchDetail>();
    fetchDetail.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useBatchExpansion(defaults));
    act(() => result.current.toggle("A")); const oldSignal = fetchDetail.mock.calls[0][3]!;
    act(() => result.current.toggle("A")); expect(oldSignal.aborted).toBe(true);
    act(() => result.current.toggle("A"));
    await act(async () => second.resolve({ ...detail("A"), batch: { ...batch("A"), totalAmount: "22.00" } }));
    await act(async () => first.resolve({ ...detail("A"), batch: { ...batch("A"), totalAmount: "11.00" } }));
    expect(result.current.details.A.batch.totalAmount).toBe("22.00");
    expect(result.current.loadingIds.has("A")).toBe(false); expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  test("one detail failure stays local and retries only that batch", async () => {
    fetchDetail.mockImplementation(async (id) => { if (id === "A") throw new Error("A 明细读取失败"); return detail(id); });
    const { result } = renderHook(() => useBatchExpansion(defaults));
    act(() => result.current.toggle("A")); act(() => result.current.toggle("B"));
    await waitFor(() => expect(result.current.errors.A).toBe("A 明细读取失败"));
    expect(result.current.details.B.batch.batchId).toBe("B");
    fetchDetail.mockImplementation(async (id) => detail(id)); act(() => result.current.retry("A"));
    await waitFor(() => expect(result.current.details.A.batch.batchId).toBe("A"));
    expect(result.current.errors.A).toBeUndefined(); expect(fetchDetail.mock.calls.map(([id]) => id)).toEqual(["A", "B", "A"]);
  });

  test("accepted refresh reloads null-version candidates while scope changes clear expansion", async () => {
    fetchDetail.mockImplementation(async (id) => detail(id));
    const { result, rerender } = renderHook((props) => useBatchExpansion(props), { initialProps: defaults });
    act(() => result.current.toggle("A")); await waitFor(() => expect(result.current.details.A).toBeDefined());
    rerender({ ...defaults, snapshotVersion: 2 }); await waitFor(() => expect(fetchDetail).toHaveBeenCalledTimes(2));
    expect(result.current.expandedIds.has("A")).toBe(true);
    rerender({ ...defaults, scopeKey: "different", snapshotVersion: 3 });
    expect(result.current.expandedIds.size).toBe(0); expect(result.current.mountedIds.size).toBe(0);
    expect(result.current.details).toEqual({}); expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  test("scope replacement and unmount abort pending requests without accepting late results", async () => {
    const old = pending<BankFlowRuleBatchDetail>(); fetchDetail.mockReturnValue(old.promise);
    const { result, rerender, unmount } = renderHook((props) => useBatchExpansion(props), { initialProps: defaults });
    act(() => result.current.toggle("A")); const firstSignal = fetchDetail.mock.calls[0][3]!;
    rerender({ ...defaults, scopeKey: "different" }); expect(firstSignal.aborted).toBe(true);
    await act(async () => old.resolve(detail("A"))); expect(result.current.details).toEqual({});
    const next = pending<BankFlowRuleBatchDetail>(); fetchDetail.mockReturnValue(next.promise);
    act(() => result.current.toggle("B")); const nextSignal = fetchDetail.mock.calls[1][3]!;
    unmount(); expect(nextSignal.aborted).toBe(true); await act(async () => next.resolve(detail("B")));
  });
});

test("reduced motion shows content immediately and completes collapse without an animation", () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
  const animate = vi.spyOn(HTMLElement.prototype, "animate");
  const onExited = vi.fn();
  const subject = (expanded: boolean) => <BatchExpansion contentKey="A" expanded={expanded} id="batch-A" label="批次 A" onExited={onExited}><span>明细</span></BatchExpansion>;
  const view = render(subject(true));
  expect(view.container.firstElementChild).toHaveStyle({ height: "auto", opacity: "1" });
  expect(animate).not.toHaveBeenCalled(); expect(onExited).not.toHaveBeenCalled();
  view.rerender(subject(false));
  expect(view.container.firstElementChild).toHaveAttribute("inert");
  expect(view.container.firstElementChild).toHaveStyle({ height: "0px" });
  expect(onExited).toHaveBeenCalledTimes(1); expect(animate).not.toHaveBeenCalled();
});

test("slides to natural content after layout, follows collection growth and reverses from the visible frame", async () => {
  let contentHeight = 13; let visibleHeight = 0;
  let resized!: ResizeObserverCallback;
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resized = callback; }
    observe() {} unobserve() {} disconnect() {}
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { height: this.classList.contains("bank-flow-rule-batches-expansion__content") ? contentHeight : visibleHeight } as DOMRect;
  });
  const cancelled = vi.fn(); const animations: Array<{ onfinish: null | (() => void); cancel: () => void }> = [];
  const animate = vi.spyOn(HTMLElement.prototype, "animate").mockImplementation(() => {
    const animation = { onfinish: null as null | (() => void), cancel: cancelled }; animations.push(animation);
    return animation as unknown as Animation;
  });
  const onExited = vi.fn();
  const subject = (expanded: boolean) => <BatchExpansion contentKey="A" expanded={expanded} id="batch-A" label="批次 A" onExited={onExited}><span>明细</span></BatchExpansion>;
  const view = render(subject(true));
  expect(animate).not.toHaveBeenCalled(); // The collection is still mounting before first layout.
  contentHeight = 135;
  await act(async () => { await new Promise(requestAnimationFrame); });
  expect(animate.mock.calls[0][0]).toEqual([{ height: "0px", opacity: 0.6 }, { height: "135px", opacity: 1 }]);
  expect(animate.mock.calls[0][1]).toEqual(expect.objectContaining({ duration: 220, fill: "forwards" }));
  visibleHeight = 70; contentHeight = 180;
  act(() => resized([], {} as ResizeObserver));
  await act(async () => { await new Promise(requestAnimationFrame); });
  expect(animate.mock.calls[1][0]).toEqual([{ height: "70px", opacity: 0.6 }, { height: "180px", opacity: 1 }]);
  visibleHeight = 90; view.rerender(subject(false));
  expect(view.container.firstElementChild).toHaveAttribute("inert");
  expect(animate.mock.calls[2][0]).toEqual([{ height: "90px", opacity: 0.6 }, { height: "0px", opacity: 0.6 }]);
  expect(animate.mock.calls[2][1]).toEqual(expect.objectContaining({ duration: 170 }));
  visibleHeight = 45; view.rerender(subject(true));
  await act(async () => { await new Promise(requestAnimationFrame); });
  expect(animate.mock.calls[3][0]).toEqual([{ height: "45px", opacity: 0.6 }, { height: "180px", opacity: 1 }]);
  expect(cancelled).toHaveBeenCalledTimes(3); expect(onExited).not.toHaveBeenCalled();
  view.rerender(subject(false));
  act(() => animations.at(-1)?.onfinish?.()); expect(onExited).toHaveBeenCalledTimes(1);
});
