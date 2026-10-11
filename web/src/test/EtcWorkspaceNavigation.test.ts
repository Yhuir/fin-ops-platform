import { describe, expect, test } from "vitest";
import { etcImportPath, etcReturnContext, etcReturnPath } from "../features/etc/workspaceNavigation";

describe("ETC workspace route context", () => {
  test("round trips exact batch, task, bucket and server page", () => {
    const path = etcImportPath("task / & 1", "batch / & 1", "staged", 3);
    const params = new URL(path, "https://example.test").searchParams;
    expect(params.get("etc_task")).toBe("task / & 1");
    expect(etcReturnContext(params)).toEqual({ batchId: "batch / & 1", bucket: "staged", page: 3 });
    expect(new URL(etcReturnPath(params), "https://example.test").searchParams.get("batch")).toBe("batch / & 1");
  });
  test("ordinary importer has no invented batch", () => {
    expect(etcReturnContext(new URLSearchParams())).toBeNull();
    expect(etcReturnPath(new URLSearchParams())).toBe("/etc-tickets");
  });
  test.each(["batch=&bucket=staged&page=1", "batch=x&bucket=invalid&page=1", "batch=x&bucket=submitted&page=0", "batch=x&bucket=submitted&page=NaN", "batch=x&bucket=submitted&page=9007199254740992"])("rejects invalid explicit context %s", query => {
    expect(() => etcReturnContext(new URLSearchParams(query))).toThrow("ETC 批次导航参数无效。");
  });
});
