import { describe, expect, test } from "vitest";

import { resolveWorkbenchWriteGate } from "../features/workbench/writeGate";

const writableInput = {
  canMutateData: true,
  mutationsBlocked: false,
  oaSyncWriteBlocked: false,
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
  ] as const)("returns the first blocking reason for %o", (overrides, reason, message) => {
    expect(resolveWorkbenchWriteGate({ ...writableInput, ...overrides })).toMatchObject({
      allowed: false,
      reason,
      message: expect.stringContaining(message),
    });
  });

  test("keeps permission failures ahead of system and OA sync failures", () => {
    expect(resolveWorkbenchWriteGate({
      ...writableInput,
      canMutateData: false,
      mutationsBlocked: true,
      oaSyncWriteBlocked: true,
    }).reason).toBe("read_only");
  });
});
