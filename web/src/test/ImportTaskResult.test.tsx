import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fetchBackgroundJob, mapBackgroundJob } from "../features/backgroundJobs/api";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import ImportTaskResult from "../components/imports/ImportTaskResult";

vi.mock("../features/backgroundJobs/api", async importOriginal => ({
  ...await importOriginal<typeof import("../features/backgroundJobs/api")>(), fetchBackgroundJob: vi.fn(),
}));
vi.mock("../features/backgroundJobs/BackgroundJobProgressProvider");
vi.mock("../components/imports/ImportJobDiagnostics", () => ({ SharedImportTasksButton: ({ label }: { label: string }) => <button>{label}</button> }));
const accepted = mapBackgroundJob({ job_id: "import:one", status: "queued", message: "已受理" });
const completed = { ...accepted, status: "succeeded" as const, message: "导入完成。" };
function feed(jobs: typeof accepted[]) {
  vi.mocked(useBackgroundJobProgress).mockReturnValue({ jobs } as ReturnType<typeof useBackgroundJobProgress>);
}
beforeEach(() => { vi.resetAllMocks(); feed([]); });

test("reads final result after task leaves the feed and stops fetching once complete", async () => {
  feed([accepted]);
  const { rerender } = render(<ImportTaskResult accepted={accepted} />);
  expect(screen.getByRole("status")).toHaveTextContent("已开始后台导入");
  expect(fetchBackgroundJob).not.toHaveBeenCalled();
  feed([]);
  vi.mocked(fetchBackgroundJob).mockResolvedValue(completed);
  rerender(<ImportTaskResult accepted={accepted} />);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("导入完成。"));
  expect(screen.getByRole("button", { name: "查看本次导入结果" })).toBeVisible();
  feed([]);
  rerender(<ImportTaskResult accepted={accepted} />);
  expect(fetchBackgroundJob).toHaveBeenCalledTimes(1);
});

test("shows partial success as attention and retains explicit result-read errors", async () => {
  const user = userEvent.setup();
  vi.mocked(fetchBackgroundJob).mockRejectedValueOnce(new Error("结果暂时不可读"));
  render(<ImportTaskResult accepted={accepted} embedded />);
  expect(await screen.findByRole("alert")).toHaveTextContent("结果暂时不可读");
  vi.mocked(fetchBackgroundJob).mockResolvedValue({ ...accepted, status: "partial_success", message: "部分导入完成，1 项失败" });
  await user.click(screen.getByRole("button", { name: "重新读取结果" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("部分导入完成，1 项失败"));
  expect(screen.queryByRole("button", { name: "查看本次导入结果" })).not.toBeInTheDocument();
});

test("unmount cancels a result read without reporting a false success", () => {
  vi.mocked(fetchBackgroundJob).mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<ImportTaskResult accepted={accepted} />);
  const signal = vi.mocked(fetchBackgroundJob).mock.calls[0][1];
  unmount();
  expect(signal?.aborted).toBe(true);
});
