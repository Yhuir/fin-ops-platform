import { useEffect, useState } from "react";
import { fetchTaxCertifications } from "./api";
import type { TaxCertificationQuery, TaxCertificationResult } from "./types";

export function useTaxCertifications(query: TaxCertificationQuery, active: boolean, activationGeneration: number) {
  const [result, setResult] = useState<TaxCertificationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true); setError("");
    fetchTaxCertifications(query, controller.signal).then(value => {
      if (!controller.signal.aborted) setResult(value);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "加载失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, active, activationGeneration, revision]);
  return { result, loading, error, refresh: () => setRevision(value => value + 1) };
}
