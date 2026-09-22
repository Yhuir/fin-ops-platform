import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@heroui/react";
import { Link } from "react-router-dom";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../common/FinanceTable";
import { disposeImportJob, fetchImportJobDetail, fetchImportJobs, type ImportJobDetail, type ImportJobPage } from "../../features/imports/jobOperations";

const statusLabels: Record<string, string> = { failed: "失败待处理", needs_review: "需要复核", pending: "排队中", processing: "执行中", awaiting_confirmation: "待确认", canceled: "已放弃", succeeded: "已完成" };
const typeLabels: Record<string, string> = { imports_invoices: "发票导入", imports_bank_transactions: "银行流水导入", imports_etc_invoices: "ETC 发票导入", etc_tickets: "ETC 票据", tax_offset: "已认证发票导入", settings: "OA 导入", import_unknown: "归属待核实" };
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "请求失败，请刷新核实。";

export default function ImportJobDiagnostics({ refreshToken, onHandled }: { refreshToken: unknown; onHandled: () => Promise<void> }) {
  const [page, setPage] = useState(1);
  const [list, setList] = useState<ImportJobPage | null>(null);
  const [listError, setListError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ImportJobDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [reason, setReason] = useState("not_needed");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [success, setSuccess] = useState("");
  const listRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const submitting = useRef(false);

  const loadList = useCallback(async () => {
    listRequest.current?.abort();
    const request = new AbortController(); listRequest.current = request;
    setLoading(true);
    try {
      const result = await fetchImportJobs(page, request.signal);
      if (request.signal.aborted) return;
      if (!result.rows.length && page > 1) { setPage(Math.max(1, Math.ceil(result.pagination.total / 20))); return; }
      setList(result); setListError("");
    } catch (error) { if (!request.signal.aborted) setListError(errorMessage(error)); }
    finally { if (listRequest.current === request) setLoading(false); }
  }, [page]);
  useEffect(() => { void loadList(); return () => listRequest.current?.abort(); }, [loadList, refreshToken]);
  useEffect(() => () => detailRequest.current?.abort(), []);

  async function loadDetail(id: string, filePage = 1) {
    detailRequest.current?.abort();
    const request = new AbortController(); detailRequest.current = request;
    setDetailLoading(true); setDetailError("");
    try {
      const result = await fetchImportJobDetail(id, filePage, request.signal);
      if (request.signal.aborted) return;
      setDetail(result); setUncertain(false);
      if (result.job.disposition) setSuccess("本次任务已结束处理；原执行结果和历史记录保留。");
      return result;
    } catch (error) { if (!request.signal.aborted) setDetailError(errorMessage(error)); }
    finally { if (detailRequest.current === request) setDetailLoading(false); }
  }
  async function handleDispose() {
    if (!detail || submitting.current || uncertain) return;
    const action = detail.job.allowed_actions?.[0];
    if (!action) return;
    submitting.current = true; setBusy(true); setDetailError("");
    listRequest.current?.abort(); detailRequest.current?.abort();
    try {
      const result = await disposeImportJob(detail.job, action, reason, note);
      setDetail({ ...detail, job: { ...detail.job, status: result.status, version: result.version,
        disposition: result.disposition, allowed_actions: [], continue_route: null } });
      setSuccess("本次任务已结束处理；原执行结果和历史记录保留。");
      await Promise.all([loadList(), onHandled()]);
    } catch (error) {
      // A lost HTTP response is not proof of a failed transaction. Read before allowing another command.
      setUncertain(true);
      const result = await loadDetail(detail.job.job_id);
      if (result?.job.disposition) await Promise.all([loadList(), onHandled()]);
      else setDetailError(`${errorMessage(error)}${result ? " 当前结果已重新核实。" : " 结果尚未核实，请先刷新详情。"}`);
    } finally { submitting.current = false; setBusy(false); }
  }
  const job = detail?.job;
  return <section aria-label="导入任务诊断" id="import-job-diagnostics">
    <div className="app-health-section__header"><h3>导入任务诊断</h3><Button variant="secondary" onPress={() => void loadList()} isDisabled={loading}>刷新任务</Button></div>
    {listError && <p role="alert">{success ? "处理已成功，但任务列表刷新失败。" : ""}{listError}</p>}
    {loading && <p role="status">正在读取任务…</p>}
    {list && <>
      <FinanceTable ariaLabel="待处理导入任务" minWidth={640}>
        <FinanceTableHeader><FinanceTableColumn isRowHeader>导入类型</FinanceTableColumn><FinanceTableColumn>文件</FinanceTableColumn><FinanceTableColumn>创建人</FinanceTableColumn><FinanceTableColumn>状态</FinanceTableColumn><FinanceTableColumn>更新时间</FinanceTableColumn><FinanceTableColumn>操作</FinanceTableColumn></FinanceTableHeader>
        <FinanceTableBody>{list.rows.map(row => <FinanceTableRow key={row.job_id} id={row.job_id}>
          <FinanceTableCell columnRole="description">{row.affected_domains.map(d => typeLabels[d]).join("、")}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.file_name || "无文件摘要"}{row.file_count ? `（${row.file_count} 个）` : ""}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.created_by || "未记录"}</FinanceTableCell><FinanceTableCell columnRole="description">{statusLabels[row.status]}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{new Date(row.updated_at).toLocaleString("zh-CN")}</FinanceTableCell>
          <FinanceTableCell columnRole="description"><Button variant="secondary" onPress={() => { setSelected(row.job_id); setDetail(null); setSuccess(""); setNote(""); setReason("not_needed"); setUncertain(false); void loadDetail(row.job_id); }}>查看详情</Button></FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>
      {!list.rows.length && <p>无待处理导入任务</p>}
      <div className="app-health-section__header"><span>共 {list.pagination.total} 条 · 第 {page} 页</span>
        <Button variant="secondary" isDisabled={page === 1 || loading} onPress={() => setPage(page - 1)}>上一页任务</Button>
        <Button variant="secondary" isDisabled={!list.pagination.has_more || loading} onPress={() => setPage(page + 1)}>下一页任务</Button></div>
    </>}
    <AppDrawer open={selected !== null} title="导入任务详情" width={680} closeDisabled={busy} onClose={() => { detailRequest.current?.abort(); setSelected(null); setDetail(null); }}>
      {detailLoading && <p role="status">正在读取详情…</p>}
      {detailError && <p role="alert">{detailError}</p>}
      {success && <p role="status">{success}</p>}
      <Button variant="secondary" isDisabled={busy || detailLoading} onPress={() => selected && void loadDetail(selected)}>刷新详情</Button>
      {job && <div className="import-job-detail">
        <p>创建人：{job.created_by || "未记录"} · 状态：{job.disposition && job.status === "failed" ? "失败（已结束处理）" : statusLabels[job.status]}</p>
        <p>任务编号：{job.job_id}</p>
        <h4>历史失败原因</h4><p>{job.error_code === "review_required" ? "当时所选文件需要复核，未通过确认。具体原因请结合下方当前预览核实。" : job.last_error || "未记录失败原因。"}</p>
        <h4>当前文件与导入证据</h4>
        <p>以下为当前记录，不代表当时的完整状态。相同身份已存在，也不等于原任务已成功。</p>
        {detail.files.length === 0 && <p>没有可读取的文件明细；尚不能确认后续是否完成。请由创建人核实原文件。</p>}
        {detail.files.map(file => <div key={file.file_id}>
          <strong>{file.file_name || "未记录文件名"}</strong><p>文件状态：{file.status}；错误：{file.error_count ?? "未记录"}；疑似重复：{file.suspected_duplicate_count ?? "未记录"}</p>
          {file.message && <p>{file.message}</p>}
          <p>批次明细 {file.row_count} 条；批次记录引用 {file.linked_count} 条；当前发票强身份匹配 {file.identity_match_count} 条。</p>
          {!file.preview_batch_id && <p>无当前预览批次。</p>}
        </div>)}
        <div><Button variant="secondary" isDisabled={detailLoading || busy || detail.file_pagination.page === 1} onPress={() => void loadDetail(job.job_id, detail.file_pagination.page - 1)}>上一页文件</Button>
          <Button variant="secondary" isDisabled={detailLoading || busy || !detail.file_pagination.has_more} onPress={() => void loadDetail(job.job_id, detail.file_pagination.page + 1)}>下一页文件</Button></div>
        {job.disposition ? <p>处理人：{job.disposition.actor_name}（{job.disposition.actor_account}）；原因：{job.disposition.reason === "completed_elsewhere" ? "已另行完成" : "不再继续导入"}；说明：{job.disposition.note || "无"}</p> : <>
          {job.continue_route ? <Link to={`${job.continue_route}?import_job=${encodeURIComponent(`import:${job.job_id}`)}`}>继续查看导入预览</Link> : <p>仍需导入时，请任务创建人进入原导入页面处理；管理员不会代替他人确认导入。</p>}
          {!!job.allowed_actions?.length && <>
            <p>{job.allowed_actions[0] === "discard" ? "放弃将结束本次预览，并关闭提醒。" : "结束处理将关闭这条提醒，保留失败历史；之后不能重试此任务。如需导入，请新建导入。"}</p>
            <label>处理原因<select aria-label="处理原因" value={reason} disabled={busy} onChange={e => setReason(e.target.value)}><option value="not_needed">不再继续导入</option><option value="completed_elsewhere">已另行完成</option></select></label>
            <label>补充说明（选填）<textarea aria-label="补充说明（选填）" value={note} maxLength={500} disabled={busy} onChange={e => setNote(e.target.value)} /></label>
            <Button onPress={() => void handleDispose()} isDisabled={busy || uncertain || detailLoading || !!detailError}>{busy ? "正在处理…" : job.allowed_actions[0] === "discard" ? "放弃预览并结束处理" : "结束处理并关闭提醒"}</Button>
          </>}
        </>}
      </div>}
    </AppDrawer>
  </section>;
}
