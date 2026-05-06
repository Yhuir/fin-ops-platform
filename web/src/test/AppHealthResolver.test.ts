import { describe, expect, it } from "vitest";

import { resolveAppHealthStatus } from "../features/appHealth/resolveAppHealthStatus";
import type { AppHealthSources } from "../features/appHealth/types";

const baseSources: AppHealthSources = {
  session: "authenticated",
  backgroundJobs: "idle",
  importProgress: "idle",
  oaSync: "idle",
  workbench: "ready",
};

describe("resolveAppHealthStatus", () => {
  it("returns green when every source is healthy", () => {
    expect(resolveAppHealthStatus(baseSources)).toMatchObject({
      level: "ok",
      reason: "系统状态正常",
      blocksMutations: false,
    });
  });

  it("returns yellow while a background task is running", () => {
    expect(resolveAppHealthStatus({ ...baseSources, backgroundJobs: "running" })).toMatchObject({
      level: "busy",
      reason: "后台任务处理中",
      blocksMutations: false,
    });
  });

  it("returns yellow when OA has changes that are not in the workbench read model", () => {
    expect(resolveAppHealthStatus({ ...baseSources, oaSync: "dirty", workbench: "stale" })).toMatchObject({
      level: "busy",
      reason: "关联台待刷新",
      blocksMutations: false,
    });
  });

  it("returns red and blocks writes when the session is expired", () => {
    expect(resolveAppHealthStatus({ ...baseSources, session: "expired" })).toMatchObject({
      level: "blocked",
      reason: "登录已失效",
      blocksMutations: true,
    });
  });

  it("preserves the workbench error message for blocked status", () => {
    expect(resolveAppHealthStatus({ ...baseSources, workbench: "error" }, "OA 连接失败")).toMatchObject({
      level: "blocked",
      reason: "OA 连接失败",
      blocksMutations: true,
    });
  });
});
