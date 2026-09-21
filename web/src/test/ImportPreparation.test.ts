import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchBackgroundJob } from "../features/backgroundJobs/api";
import { waitForImportCompletion, waitForImportPreparation } from "../features/imports/preparation";

vi.mock("../features/backgroundJobs/api", async (original) => ({
  ...await original<typeof import("../features/backgroundJobs/api")>(),
  fetchBackgroundJob: vi.fn(),
}));

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe("durable import preparation", () => {
  test("polls the accepted task until a versioned preview is ready", async () => {
    vi.useFakeTimers();
    vi.mocked(fetchBackgroundJob).mockResolvedValue({ jobId: "import:one", status: "awaiting_confirmation", version: 3 } as never);
    const pending = waitForImportPreparation({ job: { job_id: "import:one", status: "queued" } });
    await vi.advanceTimersByTimeAsync(300);
    expect(await pending).toMatchObject({ jobId: "import:one", version: 3, status: "awaiting_confirmation" });
    expect(fetchBackgroundJob).toHaveBeenCalledTimes(1);
    expect(fetchBackgroundJob).toHaveBeenCalledWith("import:one");
  });

  test("surfaces a durable failure without reporting upload as imported", async () => {
    await expect(waitForImportPreparation({ job: { job_id: "import:one", status: "failed", error: "原件无法读取" } }))
      .rejects.toThrow("原件无法读取");
    expect(fetchBackgroundJob).not.toHaveBeenCalled();
  });

  test("a polling connection error does not repeat the upload or confirmation", async () => {
    vi.useFakeTimers();
    vi.mocked(fetchBackgroundJob).mockRejectedValue(new Error("连接中断"));
    const pending = waitForImportPreparation({ job: { job_id: "import:one", status: "running" } });
    const assertion = expect(pending).rejects.toThrow("连接中断");
    await vi.advanceTimersByTimeAsync(300);
    await assertion;
    expect(fetchBackgroundJob).toHaveBeenCalledTimes(1);
  });

  test("keeps no-change completion distinct from awaiting confirmation", async () => {
    const result = await waitForImportPreparation({ job: { job_id: "import:one", status: "succeeded", result_summary: { outcome: "no_changes" } } });
    expect(result.status).toBe("succeeded");
    expect(result.resultSummary.outcome).toBe("no_changes");
  });

  test("preserves partial commit results for the caller to display failed rows", async () => {
    const result = await waitForImportCompletion({ job: { job_id: "import:one", status: "partial_success", result_summary: { outcome: "partial_success", failed: [{ row_id: "bad" }] } } });
    expect(result.status).toBe("partial_success");
    expect(result.resultSummary.failed).toHaveLength(1);
    await expect(waitForImportCompletion({ job: { job_id: "import:two", status: "failed", error: "全部来源校验失败" } })).rejects.toThrow("全部来源校验失败");
  });

  test("rejects missing task identity", async () => {
    await expect(waitForImportPreparation({ job: {} })).rejects.toThrow("缺少任务编号");
  });

  test("rejects an unknown task state instead of displaying queued", async () => {
    await expect(waitForImportPreparation({ job: { job_id: "import:one", status: "unrecognized" } }))
      .rejects.toThrow("未知状态");
  });
});
