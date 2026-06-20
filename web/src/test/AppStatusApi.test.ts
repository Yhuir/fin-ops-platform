import { describe, expect, test } from "vitest";

import { mapAppStatusOverview } from "../features/appStatus/api";

describe("app status API mapper", () => {
  test("rejects malformed critical overall fields instead of defaulting to green", () => {
    const mapped = mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "mystery",
        color: "green",
        reason: "bad payload",
        blocks_mutations: false,
      },
      domains: [],
      background_tasks: [],
      alerts: [],
    });

    expect(mapped).toBeNull();
  });

  test("rejects malformed domain and task critical fields", () => {
    expect(mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "后台任务处理中",
        blocks_mutations: false,
      },
      domains: [{ key: "bank_details", label: "银行明细", route: "/bank-details", level: "unknown", status: "ready", reason: "ok" }],
      background_tasks: [],
      alerts: [],
    })).toBeNull();

    expect(mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "后台任务处理中",
        blocks_mutations: false,
      },
      domains: [],
      background_tasks: [{ job_id: "job_1", type: "x", status: "", label: "任务", route: "/operations/app-health" }],
      alerts: [],
    })).toBeNull();
  });

  test("rejects malformed domain status and task status", () => {
    expect(mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "数据正在同步",
        blocks_mutations: false,
      },
      domains: [{ key: "bank_details", label: "银行明细", route: "/bank-details", level: "busy", status: "almost_ready", reason: "bad" }],
      background_tasks: [],
      alerts: [],
    })).toBeNull();

    expect(mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "后台任务处理中",
        blocks_mutations: false,
      },
      domains: [],
      background_tasks: [{ job_id: "job_1", type: "x", status: "teleporting", label: "任务", route: "/operations/app-health" }],
      alerts: [],
    })).toBeNull();
  });

  test("maps write safety as the mutation gate separately from overall level", () => {
    const mapped = mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "blocked",
        color: "red",
        reason: "银行明细不可用",
        blocks_mutations: true,
        write_safety: {
          status: "ready",
          reason: "写操作可用",
          blocks_mutations: false,
          blockers: [],
        },
      },
      domains: [],
      background_tasks: [],
      alerts: [],
    });

    expect(mapped?.overall.level).toBe("blocked");
    expect(mapped?.overall.blocksMutations).toBe(false);
    expect(mapped?.overall.writeSafety).toEqual({
      status: "ready",
      reason: "写操作可用",
      blocksMutations: false,
      blockers: [],
    });
  });

  test("maps read model scope diagnostics for app status domains", () => {
    const mapped = mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "成本统计局部分片需要重试",
        blocks_mutations: false,
      },
      domains: [
        {
          key: "cost_statistics",
          label: "成本统计",
          route: "/cost-statistics",
          level: "busy",
          status: "failed",
          reason: "成本统计局部分片需要重试",
          details: ["active:2026-05: projection failed"],
          read_models: ["cost_statistics"],
          read_model_scopes: [
            {
              read_model_key: "cost_statistics",
              scope_type: "cost_statistics",
              scope_key: "active:all",
              status: "fresh",
              updated_at: "2026-06-04T10:03:00+08:00",
            },
            {
              read_model_key: "cost_statistics",
              scope_type: "cost_statistics",
              scope_key: "active:2026-05",
              status: "failed",
              last_error: "projection failed",
              updated_at: "2026-06-04T10:05:00+08:00",
            },
          ],
          workers: ["cost-tax"],
          job_ids: [],
          updated_at: "2026-06-04T10:05:00+08:00",
        },
      ],
      background_tasks: [],
      alerts: [],
    });

    expect(mapped?.domains[0].readModelScopes).toEqual([
      {
        readModelKey: "cost_statistics",
        scopeType: "cost_statistics",
        scopeKey: "active:all",
        status: "fresh",
        lastError: "",
        updatedAt: "2026-06-04T10:03:00+08:00",
      },
      {
        readModelKey: "cost_statistics",
        scopeType: "cost_statistics",
        scopeKey: "active:2026-05",
        status: "failed",
        lastError: "projection failed",
        updatedAt: "2026-06-04T10:05:00+08:00",
      },
    ]);
  });

  test("maps runtime summary counts from snake_case app status payload", () => {
    const mapped = mapAppStatusOverview({
      version: 1,
      generated_at: "2026-06-04T10:00:00+08:00",
      overall: {
        level: "busy",
        color: "yellow",
        reason: "Read model 正在刷新",
        blocks_mutations: false,
      },
      runtime_summary: {
        read_models: {
          total: 4,
          fresh: 1,
          refreshing: 1,
          stale: 0,
          missing: 1,
          failed: 1,
          unavailable: 0,
          issue_count: 3,
          scope_issue_count: 1,
        },
        workers: {
          total: 4,
          required: 3,
          ready: 1,
          idle: 1,
          working: 1,
          stale: 1,
          missing: 1,
          mismatched: 0,
          unavailable: 0,
          issue_count: 2,
        },
        queue: {
          event_type_count: 3,
          pending: 2,
          processing: 1,
          failed: 3,
          backlog: 6,
        },
      },
      domains: [],
      background_tasks: [],
      alerts: [],
    });

    expect(mapped?.runtimeSummary.readModels).toEqual({
      total: 4,
      fresh: 1,
      ready: 0,
      idle: 0,
      working: 0,
      refreshing: 1,
      stale: 0,
      missing: 1,
      failed: 1,
      unavailable: 0,
      mismatched: 0,
      required: 0,
      issueCount: 3,
      scopeIssueCount: 1,
    });
    expect(mapped?.runtimeSummary.workers).toMatchObject({
      total: 4,
      required: 3,
      ready: 1,
      working: 1,
      stale: 1,
      missing: 1,
      issueCount: 2,
    });
    expect(mapped?.runtimeSummary.queue).toEqual({
      eventTypeCount: 3,
      pending: 2,
      processing: 1,
      failed: 3,
      backlog: 6,
    });
  });
});
