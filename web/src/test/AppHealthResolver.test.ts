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

  it("uses the primary running job label for yellow background job reasons", () => {
    expect(resolveAppHealthStatus({ ...baseSources, backgroundJobs: "running" }, {
      primaryRunning: {
        jobId: "job-import",
        type: "file_import",
        label: "导入发票",
        shortLabel: "导入 发票 2/5",
        status: "running",
      },
    })).toMatchObject({
      level: "busy",
      reason: "正在执行后台任务：导入 发票 2/5",
    });
  });

  it("uses failed import attention before OA synced details", () => {
    expect(resolveAppHealthStatus({ ...baseSources, backgroundJobs: "attention" }, {
      primaryAttention: {
        jobId: "job-failed",
        type: "file_import",
        label: "导入发票",
        shortLabel: "导入发票失败",
        status: "failed",
      },
      attentionCount: 1,
      fallbackReason: "OA 已同步",
    })).toMatchObject({
      level: "busy",
      reason: "有 1 个失败导入任务需要确认",
    });
  });

  it("uses partial success attention before OA synced details", () => {
    expect(resolveAppHealthStatus({ ...baseSources, backgroundJobs: "attention" }, {
      primaryAttention: {
        jobId: "job-partial",
        type: "file_import",
        label: "导入发票",
        shortLabel: "导入发票部分完成",
        status: "partial_success",
      },
      attentionCount: 1,
      fallbackReason: "OA 已同步",
    })).toMatchObject({
      level: "busy",
      reason: "有 1 个部分完成任务需要确认",
    });
  });

  it("keeps running background jobs ahead of attention reasons", () => {
    expect(resolveAppHealthStatus({ ...baseSources, backgroundJobs: "running" }, {
      primaryRunning: {
        jobId: "job-running",
        type: "file_import",
        label: "导入流水",
        shortLabel: "导入 流水 1/3",
        status: "running",
      },
      primaryAttention: {
        jobId: "job-failed",
        type: "file_import",
        label: "导入发票",
        shortLabel: "导入发票失败",
        status: "failed",
      },
      attentionCount: 1,
    })).toMatchObject({
      level: "busy",
      reason: "正在执行后台任务：导入 流水 1/3",
    });
  });

  it("uses matching running months before OA synced details", () => {
    expect(resolveAppHealthStatus({ ...baseSources, workbench: "stale" }, {
      matchingRunningMonths: ["2026-03"],
      fallbackReason: "OA 已同步",
    })).toMatchObject({
      level: "busy",
      reason: "正在生成关联台候选：2026-03",
    });
  });

  it("uses dirty workbench months before OA synced details", () => {
    expect(resolveAppHealthStatus({ ...baseSources, oaSync: "dirty", workbench: "stale" }, {
      matchingDirtyMonths: ["2026-04"],
      fallbackReason: "OA 已同步",
    })).toMatchObject({
      level: "busy",
      reason: "关联台待刷新：2026-04",
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
