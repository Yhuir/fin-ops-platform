import { beforeEach, describe, expect, it, vi } from "vitest";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";

import { createWorkbenchDirectCommitVisibilityRecorder } from "../../e2e/fixtures/operationLatency";

vi.mock("node:fs/promises", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs/promises")>();
  const mocked = { ...actual, mkdir: vi.fn(), readFile: vi.fn(), rename: vi.fn(), writeFile: vi.fn() };
  return { ...mocked, default: mocked };
});

function completed(mode: "isolated" | "production_smoke", count: number) {
  const recorder = createWorkbenchDirectCommitVisibilityRecorder(mode, count);
  for (let i = 0; i < count; i += 1) {
    const sample = recorder.startAtMutationReceipt({
      sample_id: `sample-${i}`, batch_id: "private-batch", transaction_ids: ["private-transaction"],
      business_identity: "private-business", exact_scope: "2026-09",
    });
    sample.markCanonicalReadVisible(); sample.markDomVisible(); sample.complete();
  }
  return recorder;
}

// Vite serves import.meta.url over HTTP in jsdom; preserve its path while
// substituting only the Node file-URL conversion. Filesystem I/O stays mocked.
vi.mock("node:url", () => {
  const fileURLToPath = (url: URL) => url.pathname;
  return { fileURLToPath, default: { fileURLToPath } };
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(readFile).mockRejectedValue(Object.assign(new Error("missing"), { code: "ENOENT" }));
});

describe("direct commit latency evidence storage", () => {
  it("creates the output directory and atomically writes redacted isolated evidence", async () => {
    await completed("isolated", 100).writeReport();
    expect(mkdir).toHaveBeenCalledWith(expect.stringMatching(/\/outputs$/), { recursive: true });
    expect(writeFile).toHaveBeenCalledWith(
      expect.stringMatching(/\/outputs\/workbench-direct-commit-visibility-p99.json\.\d+\.tmp$/),
      expect.any(String), { mode: 0o600 },
    );
    const [temporary, json] = vi.mocked(writeFile).mock.calls[0];
    const report = JSON.parse(String(json));
    expect(report.isolated.sample_count).toBe(100);
    expect(report.isolated.pass).toBe(true);
    expect(report.isolated.production_p99_claim).toBe(false);
    expect(String(json)).not.toContain("private-transaction");
    expect(rename).toHaveBeenCalledWith(temporary, expect.stringMatching(/\/outputs\/workbench-direct-commit-visibility-p99.json$/));
  });

  it("does not let a production smoke replace missing isolated evidence", async () => {
    await expect(completed("production_smoke", 1).writeReport()).rejects.toThrow("cannot replace missing or failed isolated p99 evidence");
    expect(writeFile).not.toHaveBeenCalled();
  });

  it("retains the existing isolated run when adding a production smoke", async () => {
    const isolated = { evidence_environment: "isolated_prod_equivalent_direct_canonical_get", sample_count: 100, pass: true };
    vi.mocked(readFile).mockResolvedValue(JSON.stringify({ isolated }));
    await completed("production_smoke", 1).writeReport();
    const report = JSON.parse(String(vi.mocked(writeFile).mock.calls[0][1]));
    expect(report.isolated).toEqual(isolated);
    expect(report.production_smoke.sample_count).toBe(1);
    expect(report.production_smoke.production_p99_claim).toBe(false);
  });

  it("surfaces storage errors instead of discarding existing evidence", async () => {
    vi.mocked(readFile).mockRejectedValue(Object.assign(new Error("denied"), { code: "EACCES" }));
    await expect(completed("isolated", 100).writeReport()).rejects.toThrow("denied");
    expect(writeFile).not.toHaveBeenCalled();
  });
});
