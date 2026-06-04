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
});
