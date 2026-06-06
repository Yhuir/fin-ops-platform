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
});
