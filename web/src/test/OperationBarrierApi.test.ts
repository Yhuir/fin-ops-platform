import { afterEach, describe, expect, test, vi } from "vitest";

import {
  OperationBarrierBlockedError,
  fetchOperationBarrierStatus,
  waitForOperationFreshness,
} from "../features/operationBarrier/api";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("operation barrier API", () => {
  test("posts normalized targets and maps freshness payload", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      status: "fresh",
      fresh: true,
      targets: [
        {
          read_model_key: "workbench_relation",
          scope_type: "workbench_relation",
          scope_key: "2026-02",
          status: "fresh",
          fresh: true,
          blocking: false,
          raw_status: "fresh",
          worker_status: "ready",
        },
      ],
      blocked_targets: [],
      refreshing_targets: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchOperationBarrierStatus([{ readModelKey: "workbench_relation", scopeKey: "2026-02" }]);

    expect(payload.fresh).toBe(true);
    expect(payload.targets[0]).toMatchObject({
      readModelKey: "workbench_relation",
      scopeKey: "2026-02",
      workerStatus: "ready",
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      targets: [{ read_model_key: "workbench_relation", scope_key: "2026-02" }],
    });
  });

  test("throws barrier error when backend reports blocked target", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({
      status: "blocked",
      fresh: false,
      targets: [],
      blocked_targets: [
        {
          read_model_key: "turnover_ledger",
          scope_type: "turnover_ledger",
          scope_key: "all",
          status: "blocked",
          fresh: false,
          blocking: true,
          raw_status: "failed",
          reason: "refresh outbox blocked",
          last_error: "worker failed",
        },
      ],
      refreshing_targets: [],
    })));

    try {
      await waitForOperationFreshness([{ readModelKey: "turnover_ledger", scopeKey: "all" }]);
      throw new Error("expected operation barrier to reject");
    } catch (caught) {
      expect(caught).toBeInstanceOf(OperationBarrierBlockedError);
      expect((caught as Error).message).toBe("操作同步被阻断，往来款台账仍在同步，请稍后刷新后重试。");
      expect((caught as Error).message).not.toMatch(/refresh outbox blocked|worker failed/);
    }
  });
});
