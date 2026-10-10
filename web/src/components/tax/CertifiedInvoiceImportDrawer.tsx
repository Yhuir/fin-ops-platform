import { AlertDialog, Button, Checkbox, Input, Label, TextField } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import FileDropzone from "../common/FileDropzone";
import { FinanceTable, FinanceTableHeader, FinanceTableColumn, FinanceTableBody, FinanceTableRow, FinanceTableCell, FinanceTablePagination } from "../common/FinanceTable";
import { useSession } from "../../contexts/SessionContext";
import { useTaxCertifiedImport } from "../../features/tax/useTaxCertifiedImport";
import type { TaxCertifiedImportBatch } from "../../features/tax/types";

export default function CertifiedInvoiceImportDrawer({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const session = useSession();
  const importedBy = session.status === "authenticated" ? session.session.user.username : "";
  const state = useTaxCertifiedImport(importedBy, onImported);
  const [confirmation, setConfirmation] = useState<TaxCertifiedImportBatch | "discard" | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const wasPending = useRef(false);
  useEffect(() => { if (wasPending.current && !state.pending) contentRef.current?.focus(); wasPending.current = state.pending; }, [state.pending]);
  const rows = useMemo(() => state.preview?.files.flatMap(file => file.rows) ?? [], [state.preview]);
  const [issuePage, setIssuePage] = useState(1);
  useEffect(() => setIssuePage(1), [state.preview?.sessionId]);
  const visibleIssues = rows.slice((issuePage - 1) * 50, issuePage * 50);
  function close() { if (!state.hasSubmission && (state.files.length || state.preview)) setConfirmation("discard"); else onClose(); }
  const summary = state.preview?.summary;
  return <><AppDrawer open isDismissable title="导入认证记录" width="min(900px, 100vw)" onClose={close}
    footer={<div className="tax-import-actions">
      {state.error && state.files.length > 0 && !state.hasSubmission ? <Button variant="secondary" isDisabled={state.pending} onPress={() => state.analyze()}>重试分析</Button> : null}
      <Button variant="primary" isPending={state.busy} isDisabled={state.pending || !state.canConfirm} onPress={state.confirm}>{state.jobId ? "查询导入结果" : state.hasSubmission ? "重试提交" : "确认导入"}</Button>
    </div>}>
    <div ref={contentRef} tabIndex={-1} className="tax-certification-drawer-content">
      <FileDropzone accept=".xlsx" disabled={state.busy || state.hasSubmission} label="选择认证文件" multiple onFiles={state.selectFiles} />
      {state.files.map((file, index) => <span key={`${file.name}-${index}`}>{file.name}</span>)}
      {state.error ? <div role="alert">{state.error}</div> : null}
      {state.needsMetadata ? <div className="tax-export-fields">
        {state.metadataFields.includes("month") ? <TextField isDisabled={state.busy || state.hasSubmission} value={state.metadata.month} onBlur={() => { void state.analyze(); }} onChange={month => state.updateMetadata({ ...state.metadata, month })}><Label>所属期</Label><Input type="month" /></TextField> : null}
        {state.metadataFields.includes("buyer_tax_no") ? <TextField isDisabled={state.busy || state.hasSubmission} value={state.metadata.buyerTaxNo} onBlur={() => { void state.analyze(); }} onChange={buyerTaxNo => state.updateMetadata({ ...state.metadata, buyerTaxNo })}><Label>买方税号</Label><Input /></TextField> : null}
        <p role="status">文件所需信息可在此补充或修改，填写完成后自动分析。</p>
      </div> : null}
      {state.completed ? <div role="status">{state.completed}</div> : null}
      {state.analyzing ? <div role="status">正在分析文件…</div> : state.busy ? <div role="status">正在导入，请稍候…</div> : null}
      {summary ? <section aria-label="认证文件统计">
        <h3>认证文件统计</h3>
        <div className="tax-import-actions">{[...new Set(state.preview!.files.map(file => file.month).filter(Boolean))].map(month => <span key={month}>所属期 {month}</span>)}</div>
        <dl className="tax-import-statistics">{[
          ["文件内发票", summary.sourceCount], ["本次专票", summary.recognizedCount],
          ["新增认证", summary.newCount], ["重复跳过", summary.duplicateCount], ["补关联", summary.relinkCount],
          ["非专票忽略", summary.ignoredCount], ["无效记录", summary.invalidCount], ["待更正", summary.conflictCount],
          ["已匹配发票", summary.matchedInvoiceCount], ["未匹配发票", summary.outsideInvoicesCount],
        ].map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count} 张</dd></div>)}</dl>
        {summary.outsideInvoicesCount > 0 ? <p>未匹配发票将保存为待核对记录，不计入主列表已认证发票。</p> : null}
        {summary.duplicateCount > 0 ? <p>文件数量按来源记录统计，重复记录仅处理一次。</p> : null}
        {summary.recognizedCount === 0 ? <p role="status">没有可导入的专票认证记录。</p> : null}
        {summary.blockingCount > 0 ? <p role="alert">有 {summary.blockingCount} 条记录无法确认，请处理以下异常后重新选择文件。</p> : null}
        {state.unresolvedConflicts ? <p role="alert">请确认冲突记录的更正。</p> : null}
        {rows.length > 0 ? <section aria-label="需处理的记录">
          <ul className="tax-import-issues">{visibleIssues.map((row, index) => <li key={`${row.sourceFileName}-${row.sourceRowNumber}-${index}`}>
            <strong>{row.digitalInvoiceNo || row.invoiceNo || `${row.sourceFileName} 第 ${row.sourceRowNumber} 行`}</strong>
            <span>{row.errorMessage || "认证记录与已有记录不同"}</span>
            {row.correctionChanges?.map(change => <span key={change.field}>{change.label}：{change.previous ?? "未提供"} → {change.incoming ?? "未提供"}</span>)}
            {row.dedupeStatus === "conflict" && !row.blocking && row.uniqueKey !== null ? <Checkbox aria-label={`更正 ${row.digitalInvoiceNo || row.invoiceNo}`} isDisabled={state.pending || state.hasSubmission} isSelected={state.corrections.includes(row.uniqueKey)} onChange={selected => state.setCorrections(current => selected ? [...current, row.uniqueKey!] : current.filter(key => key !== row.uniqueKey))}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>更正</Checkbox.Content></Checkbox> : null}
          </li>)}</ul>
          {rows.length > 50 ? <FinanceTablePagination page={issuePage} pageSize={50} total={rows.length} isDisabled={state.pending} onPageChange={setIssuePage} /> : null}
        </section> : null}
      </section> : null}
      <Button variant="ghost" aria-expanded={state.historyOpen} onPress={() => state.setHistoryOpen(!state.historyOpen)}>历史批次</Button>
      {state.historyOpen ? <section aria-label="导入批次">
        {state.batchError ? <div role="alert">{state.batchError}<Button variant="ghost" onPress={state.loadBatches}>重试批次</Button></div> : null}
        <Button size="sm" variant="ghost" isDisabled={state.pending || state.historyLoading} onPress={state.loadBatches}>刷新批次</Button>
        {state.historyLoading ? <div role="status">加载批次…</div> : null}<div className="tax-import-batches">{state.batches.map(batch => <div key={batch.id} className="tax-import-batch"><div><strong>{batch.months.join("、")}</strong><div>{batch.created_at} · {batch.persisted_record_count} 条</div></div>
          {batch.status === "revoked" ? <span>已撤销</span> : <Button size="sm" variant="danger-soft" isDisabled={state.pending || state.hasSubmission} onPress={() => setConfirmation(batch)}>撤销</Button>}</div>)}</div>
      <FinanceTablePagination page={state.historyPaging.batches_page} pageSize={state.historyPaging.page_size} total={state.historyPaging.batches_total} isDisabled={state.historyLoading || state.pending} onPageChange={page => state.setHistoryQuery(current => ({ ...current, batches_page: page }))} />
      </section> : null}
      {state.historyOpen && state.historyPaging.records_total > 0 ? <section aria-label="待核对记录"><h3>待核对记录</h3><FinanceTable ariaLabel="待核对认证记录" minWidth={600} footer={<FinanceTablePagination page={state.historyPaging.records_page} pageSize={state.historyPaging.page_size} total={state.historyPaging.records_total} isDisabled={state.historyLoading || state.pending} onPageChange={page => state.setHistoryQuery(current => ({ ...current, records_page: page }))} />}><FinanceTableHeader><FinanceTableColumn isRowHeader>发票号码</FinanceTableColumn><FinanceTableColumn>销方名称</FinanceTableColumn><FinanceTableColumn>状态</FinanceTableColumn></FinanceTableHeader><FinanceTableBody>{state.records.map(record => <FinanceTableRow id={record.id} key={record.id}><FinanceTableCell columnRole="identity">{record.digital_invoice_no || record.invoice_no || "—"}</FinanceTableCell><FinanceTableCell columnRole="account">{record.seller_name || "—"}</FinanceTableCell><FinanceTableCell columnRole="status">待核对</FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable></section> : null}
    </div>
  </AppDrawer>
    <AlertDialog.Backdrop isOpen={confirmation !== null} onOpenChange={open => { if (!open && !state.pending) setConfirmation(null); }}><AlertDialog.Container size="sm"><AlertDialog.Dialog>
      <AlertDialog.Header><AlertDialog.Heading>{confirmation === "discard" ? "放弃本次导入？" : "撤销此批次？"}</AlertDialog.Heading></AlertDialog.Header>
      {confirmation !== "discard" ? <AlertDialog.Body>撤销该批次的认证记录，发票将重新计算认证状态。</AlertDialog.Body> : null}
      <AlertDialog.Footer><Button variant="secondary" isDisabled={state.pending} onPress={() => setConfirmation(null)}>取消</Button><Button variant="danger" isPending={state.pending} onPress={async () => { if (confirmation === "discard") onClose(); else if (confirmation) await state.revoke(confirmation); setConfirmation(null); }}>{confirmation === "discard" ? "放弃导入" : "确认撤销"}</Button></AlertDialog.Footer>
    </AlertDialog.Dialog></AlertDialog.Container></AlertDialog.Backdrop>
  </>;
}
