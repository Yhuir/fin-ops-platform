import { Accordion, AlertDialog, Button, Checkbox, Input, Label, TextField } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import FileDropzone from "../common/FileDropzone";
import { FinanceTable, FinanceTableHeader, FinanceTableColumn, FinanceTableBody, FinanceTableRow, FinanceTableCell, FinanceStatusTag, FinanceTablePagination } from "../common/FinanceTable";
import { useSession } from "../../contexts/SessionContext";
import { useTaxCertifiedImport } from "../../features/tax/useTaxCertifiedImport";
import type { TaxCertifiedImportBatch } from "../../features/tax/types";

export default function CertifiedInvoiceImportDrawer({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const session = useSession();
  const importedBy = session.status === "authenticated" ? session.session.user.username : "";
  const state = useTaxCertifiedImport(importedBy, onImported);
  const [confirmation, setConfirmation] = useState<TaxCertifiedImportBatch | "discard" | null>(null);
  const [month, setMonth] = useState("");
  const [buyerTaxNo, setBuyerTaxNo] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);
  const wasPending = useRef(false);
  useEffect(() => { if (wasPending.current && !state.pending) contentRef.current?.focus(); wasPending.current = state.pending; }, [state.pending]);
  const rows = useMemo(() => state.preview?.files.flatMap(file => file.rows).filter(row => row.rowStatus !== "ignored" && (row.rowStatus === "invalid" || row.dedupeStatus === "conflict" || row.matchStatus === "outside_invoices" || row.matchStatus === "ambiguous")) ?? [], [state.preview]);
  const [previewPage, setPreviewPage] = useState(1);
  useEffect(() => setPreviewPage(1), [state.preview?.sessionId]);
  const visibleRows = rows.slice((previewPage - 1) * 50, previewPage * 50);
  function close() { if (state.files.length || state.preview) setConfirmation("discard"); else onClose(); }
  return <><AppDrawer open isDismissable title="导入认证记录" width="min(900px, 100vw)" onClose={close} closeDisabled={state.pending}
    footer={<div className="tax-import-actions"><Button variant="secondary" isDisabled={state.pending || !state.files.length || Boolean(state.jobId)} onPress={() => state.recognize({ month, buyerTaxNo })}>识别</Button>
      <Button variant="primary" isPending={state.pending} isDisabled={state.pending || !state.canConfirm} onPress={state.confirm}>{state.jobId ? "查询导入结果" : "确认导入"}</Button></div>}>
    <div ref={contentRef} tabIndex={-1} className="tax-certification-drawer-content">
      <FileDropzone accept=".xlsx" disabled={state.pending || Boolean(state.jobId)} label="选择认证文件" multiple onFiles={files => { setMonth(""); setBuyerTaxNo(""); state.selectFiles(files); }} />
      {state.files.map(file => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}
      {state.error ? <div role="alert">{state.error}</div> : null}
      {state.needsMetadata ? <div className="tax-export-fields"><TextField isDisabled={state.pending || Boolean(state.jobId)} value={month} onChange={value => { setMonth(value); state.invalidatePreview(); }}><Label>所属期</Label><Input type="month" /></TextField><TextField isDisabled={state.pending || Boolean(state.jobId)} value={buyerTaxNo} onChange={value => { setBuyerTaxNo(value); state.invalidatePreview(); }}><Label>买方税号</Label><Input /></TextField></div> : null}
      {state.unresolvedConflicts ? <div role="alert">请确认冲突记录的更正</div> : null}
      {state.completed ? <div role="status">{state.completed}</div> : null}
      {state.pending ? <div role="status">处理中…</div> : null}
      {state.preview ? <section aria-label="识别结果"><div className="tax-import-actions"><strong>识别 {state.preview.summary.recognizedCount} 条</strong>
        <span>非专票 {state.preview.summary.ignoredCount} 条</span><span>重复 {state.preview.summary.duplicateCount} 条</span><span>冲突 {state.preview.summary.conflictCount} 条</span><span>无效 {state.preview.summary.invalidCount} 条</span></div>
        {rows.length > 0 ? <FinanceTable ariaLabel="认证文件异常" minWidth={700} footer={<FinanceTablePagination page={previewPage} pageSize={50} total={rows.length} isDisabled={state.pending} onPageChange={setPreviewPage} />}><FinanceTableHeader>
          <FinanceTableColumn isRowHeader>发票号码</FinanceTableColumn><FinanceTableColumn>销方名称</FinanceTableColumn><FinanceTableColumn>状态</FinanceTableColumn><FinanceTableColumn>异常 / 更正</FinanceTableColumn>
        </FinanceTableHeader><FinanceTableBody>{visibleRows.map(row => <FinanceTableRow key={row.id} id={row.id}>
          <FinanceTableCell columnRole="identity">{row.digitalInvoiceNo || row.invoiceNo || "—"}</FinanceTableCell>
          <FinanceTableCell columnRole="account">{row.sellerName || "—"}</FinanceTableCell>
          <FinanceTableCell columnRole="status"><FinanceStatusTag tone={row.rowStatus === "invalid" ? "danger" : row.dedupeStatus === "conflict" ? "warning" : "neutral"}>{row.rowStatus === "invalid" ? "无效" : row.dedupeStatus === "conflict" ? "冲突" : row.dedupeStatus === "duplicate" ? "重复" : "新记录"}</FinanceStatusTag></FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.dedupeStatus === "conflict" && row.uniqueKey !== null ? <Checkbox aria-label={`更正 ${row.digitalInvoiceNo || row.invoiceNo}`} isDisabled={state.pending || Boolean(state.jobId)} isSelected={state.corrections.includes(row.uniqueKey!)} onChange={selected => state.setCorrections(current => selected ? [...current, row.uniqueKey!] : current.filter(key => key !== row.uniqueKey))}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>更正</Checkbox.Content></Checkbox> : row.errorMessage || (row.matchStatus === "outside_invoices" ? "未关联发票" : row.matchStatus === "ambiguous" ? "关联不明确" : "—")}</FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody></FinanceTable> : null}
      </section> : null}
      <Accordion defaultExpandedKeys={["batches"]}><Accordion.Item id="batches"><Accordion.Heading><Accordion.Trigger>导入批次<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel>
        {state.batchError ? <div role="alert">{state.batchError}<Button variant="ghost" onPress={state.loadBatches}>重试批次</Button></div> : null}
        <Button size="sm" variant="ghost" isDisabled={state.pending || state.historyLoading} onPress={state.loadBatches}>刷新批次</Button>
        {state.historyLoading ? <div role="status">加载批次…</div> : null}<div className="tax-import-batches">{state.batches.map(batch => <div key={batch.id} className="tax-import-batch"><div><strong>{batch.months.join("、")}</strong><div>{batch.created_at} · {batch.persisted_record_count} 条</div></div>
          {batch.status === "revoked" ? <span>已撤销</span> : <Button size="sm" variant="danger-soft" isDisabled={state.pending} onPress={() => setConfirmation(batch)}>撤销</Button>}</div>)}</div>
      <FinanceTablePagination page={state.historyPaging.batches_page} pageSize={state.historyPaging.page_size} total={state.historyPaging.batches_total} isDisabled={state.historyLoading || state.pending} onPageChange={page => state.setHistoryQuery(current => ({ ...current, batches_page: page }))} />
      </Accordion.Panel></Accordion.Item></Accordion>
      {state.historyPaging.records_total > 0 ? <section aria-label="待核对记录"><h3>待核对记录</h3><FinanceTable ariaLabel="待核对认证记录" minWidth={600} footer={<FinanceTablePagination page={state.historyPaging.records_page} pageSize={state.historyPaging.page_size} total={state.historyPaging.records_total} isDisabled={state.historyLoading || state.pending} onPageChange={page => state.setHistoryQuery(current => ({ ...current, records_page: page }))} />}><FinanceTableHeader><FinanceTableColumn isRowHeader>发票号码</FinanceTableColumn><FinanceTableColumn>销方名称</FinanceTableColumn><FinanceTableColumn>状态</FinanceTableColumn></FinanceTableHeader><FinanceTableBody>{state.records.map(record => <FinanceTableRow id={record.id} key={record.id}><FinanceTableCell columnRole="identity">{record.digital_invoice_no || record.invoice_no || "—"}</FinanceTableCell><FinanceTableCell columnRole="account">{record.seller_name || "—"}</FinanceTableCell><FinanceTableCell columnRole="status">待核对</FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable></section> : null}
    </div>
  </AppDrawer>
    <AlertDialog.Backdrop isOpen={confirmation !== null} onOpenChange={open => { if (!open && !state.pending) setConfirmation(null); }}><AlertDialog.Container size="sm"><AlertDialog.Dialog>
      <AlertDialog.Header><AlertDialog.Heading>{confirmation === "discard" ? "放弃本次导入？" : "撤销此批次？"}</AlertDialog.Heading></AlertDialog.Header>
      {confirmation !== "discard" ? <AlertDialog.Body>撤销该批次的认证记录，发票将重新计算认证状态。</AlertDialog.Body> : null}
      <AlertDialog.Footer><Button variant="secondary" isDisabled={state.pending} onPress={() => setConfirmation(null)}>取消</Button><Button variant="danger" isPending={state.pending} onPress={async () => { if (confirmation === "discard") onClose(); else if (confirmation) await state.revoke(confirmation); setConfirmation(null); }}>{confirmation === "discard" ? "放弃导入" : "确认撤销"}</Button></AlertDialog.Footer>
    </AlertDialog.Dialog></AlertDialog.Container></AlertDialog.Backdrop>
  </>;
}
