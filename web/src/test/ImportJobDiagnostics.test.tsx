import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ImportJobDiagnostics from "../components/imports/ImportJobDiagnostics";
import * as backgroundApi from "../features/backgroundJobs/api";
import * as api from "../features/imports/jobOperations";
vi.mock("../features/imports/jobOperations");
vi.mock("../features/backgroundJobs/api");
vi.mock("../components/imports/ImportWorkflowPage", () => ({ default: ({ taskId, mode }: { taskId: string; mode: string }) => <div>共享预览 {taskId} {mode}</div> }));
const job: api.ImportOperationJob = { job_id: "job-1", import_type: "file_import.confirm", session_id: "session-1", created_by: "other-user", status: "failed", stage: "commit", version: 4, updated_at: "2026-09-22T04:00:00Z", affected_domains: ["imports_invoices"], error_code: "review_required", disposition: null, allowed_actions: ["close"] };
const list = { rows: [job], pagination: { page: 1, page_size: 20, total: 1, has_more: false } };
const detail: api.ImportJobDetail = { job, files: [], file_pagination: { page: 1, page_size: 20, total: 0, has_more: false } };
const disposition: api.ImportDisposition = { action: "close", reason: "not_needed", note: "", actor_account: "005", actor_name: "管理员", handled_at: "2026-09-22" };
function mount() { const onHandled = vi.fn().mockResolvedValue(undefined); render(<MemoryRouter><ImportJobDiagnostics refreshToken={1} onHandled={onHandled} /></MemoryRouter>); return onHandled; }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.fetchImportJobs).mockResolvedValue(list); vi.mocked(api.fetchImportJobDetail).mockResolvedValue(detail); });
test("reads another owner's details with shared preview and closes with exact version then refreshes", async () => {
  const user = userEvent.setup(); const refreshed = mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  expect(await screen.findByText(/没有可读取的文件明细/)).toBeVisible();
  expect(screen.getByRole("button", { name: "查看发票导入预览" })).toBeEnabled();
  vi.mocked(api.disposeImportJob).mockResolvedValue({ disposition, status: "failed", version: 5, idempotent_replay: false });
  vi.mocked(api.fetchImportJobs).mockResolvedValue({ ...list, rows: [], pagination: { ...list.pagination, total: 0 } });
  await user.click(screen.getByRole("button", { name: "结束处理并关闭提醒" }));
  expect(await screen.findByText("本次任务已结束处理；原执行结果和历史记录保留。")).toBeVisible();
  expect(api.disposeImportJob).toHaveBeenCalledWith(job, "close", "not_needed", "");
  expect(refreshed).toHaveBeenCalledOnce();
  expect(await screen.findByText("无待处理导入任务")).toBeVisible();
  expect(screen.queryByRole("button", { name: "结束处理并关闭提醒" })).not.toBeInTheDocument();
});
test("lost mutation response is verified by GET and not resubmitted", async () => {
  const user = userEvent.setup(); mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  await screen.findByRole("button", { name: "结束处理并关闭提醒" });
  vi.mocked(api.disposeImportJob).mockRejectedValue(new Error("连接中断"));
  vi.mocked(api.fetchImportJobDetail).mockResolvedValue({ ...detail, job: { ...job, disposition, allowed_actions: [] } });
  await user.click(screen.getByRole("button", { name: "结束处理并关闭提醒" }));
  expect(await screen.findByText("本次任务已结束处理；原执行结果和历史记录保留。")).toBeVisible();
  expect(api.disposeImportJob).toHaveBeenCalledOnce();
  expect(api.fetchImportJobDetail).toHaveBeenCalledTimes(2);
});
test("unverified result disables submit until detail can be read", async () => {
  const user = userEvent.setup(); mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  await screen.findByRole("button", { name: "结束处理并关闭提醒" });
  vi.mocked(api.disposeImportJob).mockRejectedValue(new Error("超时"));
  vi.mocked(api.fetchImportJobDetail).mockRejectedValue(new Error("离线"));
  await user.click(screen.getByRole("button", { name: "结束处理并关闭提醒" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("结果尚未核实");
  expect(screen.getByRole("button", { name: "结束处理并关闭提醒" })).toBeDisabled();
  vi.mocked(api.fetchImportJobDetail).mockResolvedValue(detail);
  await user.click(screen.getByRole("button", { name: "刷新详情" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "结束处理并关闭提醒" })).toBeEnabled());
});
test("list error is visible and can be refreshed; stale list response is ignored", async () => {
  let finish!: (value: api.ImportJobPage) => void;
  vi.mocked(api.fetchImportJobs).mockRejectedValueOnce(new Error("列表不可用"));
  const user = userEvent.setup(); mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("列表不可用");
  await user.click(screen.getByRole("button", { name: "刷新任务" }));
  await screen.findByRole("button", { name: "查看详情" });
  vi.mocked(api.fetchImportJobs).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  await user.click(screen.getByRole("button", { name: "刷新任务" }));
  await user.click(screen.getByRole("button", { name: "查看详情" }));
  await screen.findByRole("button", { name: "结束处理并关闭提醒" });
  vi.mocked(api.disposeImportJob).mockResolvedValue({ disposition, status: "failed", version: 5, idempotent_replay: false });
  vi.mocked(api.fetchImportJobs).mockResolvedValue({ ...list, rows: [], pagination: { ...list.pagination, total: 0 } });
  await user.click(screen.getByRole("button", { name: "结束处理并关闭提醒" }));
  await screen.findByText("无待处理导入任务"); finish(list);
  await waitFor(() => expect(screen.queryByRole("button", { name: "查看详情" })).not.toBeInTheDocument());
});

test("opens the same preview for another creator without navigating through a page ACL", async () => {
  const user = userEvent.setup(); mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  await user.click(await screen.findByRole("button", { name: "查看发票导入预览" }));
  expect(await screen.findByText("共享预览 import:job-1 invoice")).toBeVisible();
});
test("retry refreshes task state and preserves access after it becomes awaiting confirmation", async () => {
  const user = userEvent.setup(); mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  vi.mocked(backgroundApi.retryBackgroundJobById).mockResolvedValue(undefined);
  vi.mocked(api.fetchImportJobDetail).mockResolvedValue({ ...detail, job: { ...job, status: "awaiting_confirmation", version: 6, allowed_actions: [] } });
  await user.click(await screen.findByRole("button", { name: "重新预览" }));
  await waitFor(() => expect(backgroundApi.retryBackgroundJobById).toHaveBeenCalledWith("import:job-1"));
  expect(await screen.findByRole("button", { name: "查看发票导入预览" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "重新预览" })).not.toBeInTheDocument();
});
test("filters the shared queue on the server before pagination", async () => {
  render(<MemoryRouter><ImportJobDiagnostics refreshToken={1} onHandled={async () => {}} domain="imports_invoices" /></MemoryRouter>);
  await screen.findByRole("button", { name: "查看详情" });
  expect(api.fetchImportJobs).toHaveBeenCalledWith(1, expect.any(AbortSignal), "imports_invoices");
});

test("a lower-version detail response cannot revive a disposed task", async () => {
  const user = userEvent.setup(); mount();
  await user.click(await screen.findByRole("button", { name: "查看详情" }));
  vi.mocked(api.disposeImportJob).mockResolvedValue({ disposition, status: "failed", version: 5, idempotent_replay: false });
  await user.click(await screen.findByRole("button", { name: "结束处理并关闭提醒" }));
  await screen.findByText("本次任务已结束处理；原执行结果和历史记录保留。");
  vi.mocked(api.fetchImportJobDetail).mockResolvedValue(detail);
  await user.click(screen.getByRole("button", { name: "刷新详情" }));
  await waitFor(() => expect(api.fetchImportJobDetail).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("button", { name: "结束处理并关闭提醒" })).not.toBeInTheDocument();
  expect(screen.getByText(/处理人：管理员/)).toBeVisible();
});
