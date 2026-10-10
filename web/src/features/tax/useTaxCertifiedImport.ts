import { ApiClientError } from "../apiClient";
import { useCallback, useEffect, useRef, useState } from "react";
import { confirmTaxCertifiedImport, fetchTaxCertifiedImportBatches, fetchTaxCertifiedImportJob, previewTaxCertifiedImport, revokeTaxCertifiedImportBatch, taxCertifiedImportConfirmedFromJob } from "./api";
import type { TaxCertifiedImportBatch, TaxCertifiedImportRecord, TaxImportHistoryQuery, TaxCertifiedImportConfirmedResult, TaxCertifiedImportPreviewResult, TaxImportCorrection } from "./types";

type Metadata = { month: string; buyerTaxNo: string };
type Submission = { sessionId: string; corrections: TaxImportCorrection[]; jobId: string | null };

function readSubmission(key: string): Submission | null {
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;
  const value = JSON.parse(raw) as Submission;
  if (!value || typeof value.sessionId !== "string" || !value.sessionId || (value.jobId !== null && typeof value.jobId !== "string")
    || !Array.isArray(value.corrections) || value.corrections.some(item => !item || typeof item.unique_key !== "string" || !Number.isSafeInteger(item.expected_version) || item.expected_version < 1)) {
    throw new Error("导入恢复信息无效，请通过后台任务记录核对结果。");
  }
  return value;
}

function pollDelay(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { window.clearTimeout(timer); reject(signal.reason); };
    const timer = window.setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 1000);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

export function useTaxCertifiedImport(importedBy: string, onImported: (result?: TaxCertifiedImportConfirmedResult) => void) {
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<TaxCertifiedImportPreviewResult | null>(null);
  const [corrections, setCorrections] = useState<string[]>([]);
  const [metadata, setMetadata] = useState<Metadata>({ month: "", buyerTaxNo: "" });
  const [missingMetadata, setMissingMetadata] = useState<string[]>([]);
  const [metadataFields, setMetadataFields] = useState<string[]>([]);
  const [batches, setBatches] = useState<TaxCertifiedImportBatch[]>([]);
  const [records, setRecords] = useState<TaxCertifiedImportRecord[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState<TaxImportHistoryQuery>({ records_page: 1, batches_page: 1, page_size: 20 });
  const [historyPaging, setHistoryPaging] = useState({ records_page: 1, batches_page: 1, page_size: 20, records_total: 0, batches_total: 0 });
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyController = useRef<AbortController | null>(null);
  const analysisController = useRef<AbortController | null>(null);
  const submitController = useRef<AbortController | null>(null);
  const [batchError, setBatchError] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState("");
  const [submission, setSubmission] = useState<Submission | null>(null);
  const submissionRef = useRef<Submission | null>(null);
  const mounted = useRef(true);
  const importedCallback = useRef(onImported); importedCallback.current = onImported;
  const historyOpenRef = useRef(historyOpen); historyOpenRef.current = historyOpen;
  const storageKey = `tax-certified-import:${importedBy}`;
  const loadBatches = useCallback(async () => {
    historyController.current?.abort();
    const controller = new AbortController(); historyController.current = controller;
    setBatchError(""); setHistoryLoading(true);
    try {
      const result = await fetchTaxCertifiedImportBatches(historyQuery, controller.signal);
      if (!controller.signal.aborted) { setBatches(result.batches); setRecords(result.records); setHistoryPaging(result); }
    } catch (reason) { if (!controller.signal.aborted) setBatchError(reason instanceof Error ? reason.message : "批次加载失败"); }
    finally { if (!controller.signal.aborted) setHistoryLoading(false); }
  }, [historyQuery]);
  useEffect(() => { if (historyOpen) void loadBatches(); return () => historyController.current?.abort(); }, [historyOpen, loadBatches]);

  function saveSubmission(value: Submission | null) {
    if (value) sessionStorage.setItem(storageKey, JSON.stringify(value)); else sessionStorage.removeItem(storageKey);
    submissionRef.current = value; setSubmission(value);
  }

  async function runSubmission(initial: Submission) {
    if (submitController.current && !submitController.current.signal.aborted) return;
    const controller = new AbortController(); submitController.current = controller;
    setBusy(true); setError("");
    let current = initial;
    try {
      if (!current.jobId) {
        const result = await confirmTaxCertifiedImport(current.sessionId, current.corrections, controller.signal);
        if (controller.signal.aborted) return;
        current = { ...current, jobId: result.importJob.importJobId }; saveSubmission(current);
      }
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        const job = await fetchTaxCertifiedImportJob(current.jobId!, controller.signal);
        if (controller.signal.aborted) return;
        if (job.status === "failed" || job.status === "canceled") {
          saveSubmission(null); setPreview(null); setCorrections([]);
          throw new Error(`${job.lastError || (job.status === "canceled" ? "导入已取消" : "导入失败")}，请重新分析文件`);
        }
        if (job.status === "succeeded") {
          const result = taxCertifiedImportConfirmedFromJob(job);
          if (!result) throw new Error("导入任务缺少完整结果，请重试查询");
          saveSubmission(null); setPreview(null); setFiles([]); setCorrections([]); setMissingMetadata([]); setMetadataFields([]);
          setCompleted(`导入完成：新增 ${result.newRecordCount} 张，更正 ${result.correctedRecordCount} 张，补关联 ${result.linkedRecordCount} 张，重复跳过 ${result.duplicateCount} 张，待核对 ${result.unmatchedRecordCount} 张`);
          importedCallback.current(result);
          if (historyOpenRef.current) await loadBatches();
          return;
        }
        await pollDelay(controller.signal);
      }
      setError("导入任务仍在处理，可继续查询结果；无需重复导入。");
    } catch (reason) {
      if (controller.signal.aborted || !mounted.current) return;
      if (current.jobId && reason instanceof ApiClientError && reason.status === 404) {
        saveSubmission(null); setPreview(null); setCorrections([]);
        setError("导入任务不存在或当前账号不可访问，请核对历史记录后重新选择文件。");
      } else if (!current.jobId && reason instanceof ApiClientError && [400, 403, 404, 409].includes(reason.status)) {
        saveSubmission(null); setPreview(null); setCorrections([]);
        setError(`${reason.message}，请重新分析文件`);
      } else setError(reason instanceof Error ? reason.message : "暂时无法查询导入结果，请重试");
    } finally {
      if (submitController.current === controller) { submitController.current = null; if (mounted.current) setBusy(false); }
    }
  }

  useEffect(() => {
    mounted.current = true;
    try {
      const saved = readSubmission(storageKey);
      submissionRef.current = saved; setSubmission(saved);
      if (saved) void runSubmission(saved);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导入恢复失败"); }
    return () => {
      mounted.current = false; analysisController.current?.abort(); submitController.current?.abort();
    };
    // Recovery is scoped to the authenticated actor, not render-time callbacks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  async function analyzeFiles(next: File[], values: Metadata) {
    analysisController.current?.abort();
    const controller = new AbortController(); analysisController.current = controller;
    setAnalyzing(true); setError(""); setPreview(null); setCorrections([]);
    try {
      const result = await previewTaxCertifiedImport({ importedBy, files: next, ...values, signal: controller.signal });
      if (!controller.signal.aborted) {
        const missing = [...new Set(result.files.flatMap(file => file.missingMetadata))];
        setPreview(result); setMissingMetadata(missing); setMetadataFields(current => [...new Set([...current, ...missing])]);
      }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "文件分析失败"); }
    finally { if (!controller.signal.aborted) setAnalyzing(false); }
  }
  async function selectFiles(next: File[]) {
    if (submissionRef.current || busy) return;
    analysisController.current?.abort();
    setPreview(null); setCorrections([]); setCompleted(""); setMissingMetadata([]); setMetadataFields([]); setAnalyzing(false);
    if (!next.length || next.some(file => !/\.xlsx$/i.test(file.name))) { setFiles([]); setError("请选择 .xlsx 文件，仅支持 .xlsx"); return; }
    const values = { month: "", buyerTaxNo: "" }; setFiles(next); setMetadata(values);
    await analyzeFiles(next, values);
  }
  async function analyze(values: Metadata = metadata) {
    if (!files.length || submissionRef.current) return;
    setMetadata(values); await analyzeFiles(files, values);
  }
  function updateMetadata(values: Metadata) {
    setMetadata(values); setPreview(null); setCorrections([]); analysisController.current?.abort(); setAnalyzing(false);
  }
  const correctionKeys = new Set(corrections);
  const unresolvedConflicts = preview?.files.some(file => file.rows.some(row => row.dedupeStatus === "conflict" && !row.blocking
    && (row.uniqueKey === null || row.expectedVersion === null || !correctionKeys.has(row.uniqueKey)))) ?? false;
  const canConfirm = Boolean(submission || (preview && preview.summary.recognizedCount > 0 && preview.summary.blockingCount === 0 && missingMetadata.length === 0 && !unresolvedConflicts));
  async function confirm() {
    if (busy || analyzing || !canConfirm) return;
    let value = submissionRef.current;
    if (!value && preview) {
      const selected = new Map<string, TaxImportCorrection>();
      for (const file of preview.files) for (const row of file.rows) {
        if (row.uniqueKey && correctionKeys.has(row.uniqueKey) && row.expectedVersion !== null) selected.set(row.uniqueKey, { unique_key: row.uniqueKey, expected_version: row.expectedVersion });
      }
      value = { sessionId: preview.sessionId, corrections: [...selected.values()], jobId: null };
      try { saveSubmission(value); } catch { setError("无法保存导入恢复信息，请检查浏览器存储后重试。"); return; }
    }
    if (value) await runSubmission(value);
  }
  async function revoke(batch: TaxCertifiedImportBatch) {
    if (busy) return;
    setBusy(true); setError(""); setCompleted("");
    try {
      await revokeTaxCertifiedImportBatch(batch.id, batch.version);
      setPreview(null); setCorrections([]); importedCallback.current(); setCompleted("已撤销");
      await loadBatches();
      if (files.length && !submissionRef.current && mounted.current) await analyzeFiles(files, metadata);
    }
    catch (reason) { if (mounted.current) setError(reason instanceof Error ? reason.message : "撤销失败"); }
    finally { if (mounted.current) setBusy(false); }
  }
  return { canConfirm, unresolvedConflicts, historyOpen, setHistoryOpen, historyQuery, setHistoryQuery, historyPaging, historyLoading, records,
    missingMetadata, metadataFields, needsMetadata: metadataFields.length > 0, metadata, updateMetadata, files, preview, corrections, setCorrections, batches, batchError,
    loadBatches, pending: busy || analyzing, analyzing, busy, error, completed, jobId: submission?.jobId ?? null, hasSubmission: submission !== null,
    selectFiles, analyze, confirm, revoke };
}
