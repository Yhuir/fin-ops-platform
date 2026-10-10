import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { fetchBankFlowRuleBatchDetail } from "./api";
import { isAbortLikeError } from "./viewModel";
import type { BankFlowRuleBatch, BankFlowRuleBatchDetail, BankFlowRuleBatchStatusBucket } from "./types";

/** Expansion and detail requests belong to this result scope; selection belongs to the page. */
export function useBatchExpansion({ batches, bucket, enabled, scopeKey, snapshotVersion }: {
  batches: BankFlowRuleBatch[];
  bucket: BankFlowRuleBatchStatusBucket;
  enabled: boolean;
  scopeKey: string;
  snapshotVersion: number;
}) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [mountedIds, setMountedIds] = useState<Set<string>>(() => new Set());
  const [details, setDetails] = useState<Record<string, BankFlowRuleBatchDetail>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadingIds, setLoadingIds] = useState<Set<string>>(() => new Set());
  const requests = useRef(new Map<string, AbortController>());
  const currentScope = useRef(scopeKey);
  const generation = useRef(0);

  const invalidate = useCallback(() => {
    generation.current += 1;
    requests.current.forEach((controller) => controller.abort());
    requests.current.clear();
    setLoadingIds(new Set());
    setDetails({});
    setErrors({});
  }, []);

  const reset = useCallback(() => {
    invalidate();
    setExpandedIds(new Set());
    setMountedIds(new Set());
  }, [invalidate]);

  useLayoutEffect(() => {
    const scopeChanged = currentScope.current !== scopeKey;
    currentScope.current = scopeKey;
    invalidate();
    const validIds = new Set(batches.map((batch) => batch.batchId));
    setExpandedIds((current) => scopeChanged ? new Set() : new Set([...current].filter((id) => validIds.has(id))));
    setMountedIds((current) => scopeChanged ? new Set() : new Set([...current].filter((id) => validIds.has(id))));
    // A new accepted list response invalidates summaries and details together.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey, snapshotVersion, invalidate]);

  useEffect(() => {
    if (!enabled) {
      requests.current.forEach((controller) => controller.abort());
      requests.current.clear();
      setLoadingIds((current) => current.size ? new Set() : current);
      return;
    }
    const requestGeneration = generation.current;
    expandedIds.forEach((batchId) => {
      if (details[batchId] || errors[batchId] || requests.current.has(batchId)) return;
      const batch = batches.find((item) => item.batchId === batchId);
      if (!batch) return;
      const controller = new AbortController();
      requests.current.set(batchId, controller);
      setLoadingIds((current) => new Set([...current, batchId]));
      const isCurrent = () => !controller.signal.aborted
        && requestGeneration === generation.current
        && requests.current.get(batchId) === controller;
      fetchBankFlowRuleBatchDetail(batchId, batch.scopeMonth, bucket === "unsubmitted" ? "candidate" : "formal", controller.signal)
        .then((detail) => {
          if (isCurrent()) setDetails((current) => ({ ...current, [batchId]: detail }));
        })
        .catch((caught: unknown) => {
          if (isCurrent() && !isAbortLikeError(caught)) {
            setErrors((current) => ({ ...current, [batchId]: caught instanceof Error ? caught.message : "批次明细加载失败" }));
          }
        })
        .finally(() => {
          if (requests.current.get(batchId) !== controller) return;
          requests.current.delete(batchId);
          setLoadingIds((current) => {
            const next = new Set(current);
            next.delete(batchId);
            return next;
          });
        });
    });
  }, [batches, bucket, details, enabled, errors, expandedIds, snapshotVersion]);

  useEffect(() => () => {
    generation.current += 1;
    requests.current.forEach((controller) => controller.abort());
    requests.current.clear();
  }, []);

  const cancelRequest = useCallback((batchId: string) => {
    requests.current.get(batchId)?.abort();
    requests.current.delete(batchId);
    setLoadingIds((current) => {
      const next = new Set(current);
      next.delete(batchId);
      return next;
    });
  }, []);

  const toggle = useCallback((batchId: string) => {
    if (expandedIds.has(batchId)) {
      cancelRequest(batchId);
      setExpandedIds((current) => { const next = new Set(current); next.delete(batchId); return next; });
    } else {
      setMountedIds((current) => new Set([...current, batchId]));
      setExpandedIds((current) => new Set([...current, batchId]));
    }
  }, [cancelRequest, expandedIds]);

  const collapseAll = useCallback(() => {
    expandedIds.forEach(cancelRequest);
    setExpandedIds(new Set());
  }, [cancelRequest, expandedIds]);

  const onExited = useCallback((batchId: string) => {
    setMountedIds((current) => { const next = new Set(current); next.delete(batchId); return next; });
  }, []);

  const retry = useCallback((batchId: string) => {
    setErrors((current) => { const next = { ...current }; delete next[batchId]; return next; });
  }, []);

  return { expandedIds, mountedIds, details, errors, loadingIds, toggle, collapseAll, onExited, invalidate, reset, retry };
}
