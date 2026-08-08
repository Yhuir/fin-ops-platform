import { describe, expect, test } from "vitest";

import { resolveWorkbenchWriteGate } from "../features/workbench/writeGate";

const writableInput = {
  canMutateData: true,
  mutationsBlocked: false,
  oaSyncWriteBlocked: false,
  readModelStatus: "fresh",
  readModelVersion: "generation-1",
};

describe("resolveWorkbenchWriteGate", () => {
  test("allows writes only when every Workbench safety dependency is ready", () => {
    expect(resolveWorkbenchWriteGate(writableInput)).toEqual({
      allowed: true,
      reason: null,
      message: null,
    });
  });

  test.each([
    [{ canMutateData: false }, "read_only", "当前账号仅支持查看和导出"],
    [{ mutationsBlocked: true }, "system_unavailable", "登录已失效或系统不可用"],
    [{ oaSyncWriteBlocked: true }, "oa_syncing", "OA 正在同步，完成后将自动恢复关联操作"],
    [{ readModelStatus: "refreshing" }, "read_model_not_fresh", "关联台正在刷新"],
    [{ readModelStatus: "stale" }, "read_model_not_fresh", "关联台数据已过期"],
    [{ readModelVersion: null }, "read_model_version_missing", "关联台最新数据尚未就绪"],
  ] as const)("returns the first blocking reason for %o", (overrides, reason, message) => {
    expect(resolveWorkbenchWriteGate({ ...writableInput, ...overrides })).toMatchObject({
      allowed: false,
      reason,
      message: expect.stringContaining(message),
    });
  });

  test("keeps permission and system failures ahead of transient OA/read-model states", () => {
    expect(resolveWorkbenchWriteGate({
      ...writableInput,
      canMutateData: false,
      mutationsBlocked: true,
      oaSyncWriteBlocked: true,
      readModelStatus: "refreshing",
      readModelVersion: null,
    }).reason).toBe("read_only");
  });
});
