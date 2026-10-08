import { ApiClientError } from "../apiClient";
import { useCallback, useEffect, useRef, useState } from "react";
import { confirmTaxCertifiedImport, fetchTaxCertifiedImportBatches, fetchTaxCertifiedImportJob, previewTaxCertifiedImport, revokeTaxCertifiedImportBatch, taxCertifiedImportConfirmedFromJob } from "./api";
import type { TaxCertifiedImportBatch, TaxCertifiedImportRecord, TaxImportHistoryQuery, TaxCertifiedImportConfirmedResult, TaxCertifiedImportPreviewResult } from "./types";

export function useTaxCertifiedImport(importedBy: string, onImported: (result?: TaxCertifiedImportConfirmedResult) => void) {
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<TaxCertifiedImportPreviewResult | null>(null);
  const [corrections, setCorrections] = useState<string[]>([]);
  const [batches, setBatches] = useState<TaxCertifiedImportBatch[]>([]);
  const [records, setRecords] = useState<TaxCertifiedImportRecord[]>([]);
  const [historyQuery, setHistoryQuery] = useState<TaxImportHistoryQuery>({ records_page: 1, batches_page: 1, page_size: 20 });
  const [historyPaging, setHistoryPaging] = useState({ records_page: 1, batches_page: 1, page_size: 20, records_total: 0, batches_total: 0 });
  const [historyLoading, setHistoryLoading] = useState(true);
  const historyController = useRef<AbortController | null>(null);
  const [needsMetadata, setNeedsMetadata] = useState(false);
  const [batchError, setBatchError] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const loadBatches = useCallback(async () => {
    historyController.current?.abort();
    const controller = new AbortController(); historyController.current = controller;
    setBatchError(""); setHistoryLoading(true);
    try {
      const result = await fetchTaxCertifiedImportBatches(historyQuery, controller.signal);
      if (!controller.signal.aborted && mounted.current) { setBatches(result.batches); setRecords(result.records); setHistoryPaging(result); }
    } catch (reason) { if (!controller.signal.aborted && mounted.current) setBatchError(reason instanceof Error ? reason.message : "批次加载失败"); }
    finally { if (!controller.signal.aborted && mounted.current) setHistoryLoading(false); }
  }, [historyQuery]);
  useEffect(() => { void loadBatches(); return () => historyController.current?.abort(); }, [loadBatches]);
  function selectFiles(next: File[]) {
    if (next.some(file => !/\.xlsx$/i.test(file.name))) { setError("仅支持 .xlsx"); return; }
    setFiles(next); setPreview(null); setCorrections([]); setError(""); setCompleted(""); setJobId(null); setNeedsMetadata(false);
  }
  function invalidatePreview() { setPreview(null); setCorrections([]); setError(""); }
  const correctionKeys = new Set(corrections);
  const unresolvedConflicts = preview?.files.some(file => file.rows.some(row => row.dedupeStatus === "conflict" && (row.uniqueKey === null || row.expectedVersion === null || !correctionKeys.has(row.uniqueKey)))) ?? false;
  const canConfirm = Boolean(preview && preview.summary.recognizedCount > 0 && preview.summary.blockingCount === 0 && !unresolvedConflicts);
  async function recognize(metadata: { month: string; buyerTaxNo: string }) {
    setPending(true); setError(""); setPreview(null); setCorrections([]);
    try { const result = await previewTaxCertifiedImport({ importedBy, files, ...metadata }); if (mounted.current) { setPreview(result); setNeedsMetadata(result.files.some(file => file.rows.some(row => !row.month || !row.buyerTaxNo))); } }
    catch (reason) { if (mounted.current) { const message = reason instanceof Error ? reason.message : "识别失败"; setError(message); } }
    finally { if (mounted.current) setPending(false); }
  }
  async function confirm() {
    if (!preview || !canConfirm) return;
    setPending(true); setError("");
    try {
      let confirmed: TaxCertifiedImportConfirmedResult | null = null;
      let pendingId = jobId;
      if (!pendingId) {
        const result = await confirmTaxCertifiedImport(preview.sessionId, preview.files.flatMap(file => file.rows)
          .filter(row => row.uniqueKey !== null && correctionKeys.has(row.uniqueKey) && row.expectedVersion !== null)
          .map(row => ({ unique_key: row.uniqueKey!, expected_version: row.expectedVersion! })));
        pendingId = result.importJob.importJobId; setJobId(pendingId);
      }
      for (let attempt = 0; !confirmed && pendingId && attempt < 120; attempt += 1) {
        if (!mounted.current) return;
        const job = await fetchTaxCertifiedImportJob(pendingId);
        if (job.status === "failed") { setJobId(null); setPreview(null); setCorrections([]); throw new Error(`${job.lastError || "导入失败"}，请重新识别`); }
        if (job.status === "succeeded") {
          confirmed = taxCertifiedImportConfirmedFromJob(job);
          if (!confirmed) throw new Error("导入任务缺少批次结果");
          break;
        }
        await new Promise(resolve => window.setTimeout(resolve, 1000));
      }
      if (!confirmed) throw new Error("导入任务仍在处理，请重新查询");
      if (!mounted.current) return;
      setCompleted(`已导入 ${confirmed.persistedRecordCount} 条`); setPreview(null); setFiles([]); setJobId(null); setCorrections([]);
      onImported(confirmed); await loadBatches();
    } catch (reason) {
      if (mounted.current) {
        if (reason instanceof ApiClientError && [400, 409].includes(reason.status)) {
          setPreview(null); setCorrections([]); setJobId(null); setError(`${reason.message}，请重新识别`);
        } else setError(reason instanceof Error ? reason.message : "导入失败");
      }
    }
    finally { if (mounted.current) setPending(false); }
  }
  async function revoke(batch: TaxCertifiedImportBatch) {
    setPending(true); setError(""); setCompleted("");
    try { await revokeTaxCertifiedImportBatch(batch.id, batch.version); onImported(); setCompleted("已撤销"); await loadBatches(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "撤销失败"); }
    finally { setPending(false); }
  }
  return { canConfirm, unresolvedConflicts, invalidatePreview, historyQuery, setHistoryQuery, historyPaging, historyLoading, records, needsMetadata, files, preview, corrections, setCorrections, batches, batchError, loadBatches, pending, error, completed, jobId, selectFiles, recognize, confirm, revoke };
}
