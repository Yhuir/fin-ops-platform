import { describe, expect, test } from "vitest";

import { resolveWorkbenchWriteGate } from "../features/workbench/writeGate";

const writableInput = {
  canMutateData: true,
  mutationsBlocked: false,
  directReadAvailable: true,
  oaSyncReachable: true,
  oaSyncStatus: "synced",
  oaDirtyScopes: [],
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
    [{ directReadAvailable: false }, "direct_read_unavailable", "关联台读取失败"],
    [{ oaSyncReachable: false }, "oa_status_unavailable", "OA 同步状态读取失败"],
    [{ oaSyncStatus: "refreshing" }, "oa_syncing", "OA 正在同步，完成后将自动恢复关联操作"],
  ] as const)("returns the first blocking reason for %o", (overrides, reason, message) => {
    expect(resolveWorkbenchWriteGate({ ...writableInput, ...overrides })).toMatchObject({
      allowed: false,
      reason,
      message: expect.stringContaining(message),
    });
  });

  test("keeps permission failures ahead of system and OA states", () => {
    expect(resolveWorkbenchWriteGate({
      ...writableInput,
      canMutateData: false,
      mutationsBlocked: true,
      directReadAvailable: false,
      oaSyncReachable: false,
      oaSyncStatus: "refreshing",
    }).reason).toBe("read_only");
  });

  test.each([
    [null, []],
    ["", []],
    ["unknown", []],
    ["error", []],
    ["refreshing", []],
    ["idle", []],
    ["synced", ["all"]],
  ] as const)("blocks writes unless reachable OA is explicitly synced with no dirty scopes: %s %o", (oaSyncStatus, oaDirtyScopes) => {
    expect(resolveWorkbenchWriteGate({
      ...writableInput,
      oaSyncStatus,
      oaDirtyScopes,
    })).toMatchObject({
      allowed: false,
      reason: "oa_syncing",
    });
  });

  test("accepts normalized synced status only when no scope is dirty", () => {
    expect(resolveWorkbenchWriteGate({
      ...writableInput,
      oaSyncStatus: " SYNCED ",
    }).allowed).toBe(true);
  });
});
