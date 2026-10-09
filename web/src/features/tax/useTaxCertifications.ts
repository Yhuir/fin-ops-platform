import { useEffect, useState } from "react";
import { fetchTaxCertifications } from "./api";
import type { TaxCertificationQuery, TaxCertificationResult } from "./types";

type QueryState = { query: TaxCertificationQuery | null; result: TaxCertificationResult | null; loading: boolean; error: string };

export function useTaxCertifications(query: TaxCertificationQuery, active: boolean, activationGeneration: number) {
  const [state, setState] = useState<QueryState>({ query: null, result: null, loading: true, error: "" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState(previous => ({ query, result: previous.query === query ? previous.result : null, loading: true, error: "" }));
    fetchTaxCertifications(query, controller.signal).then(result => {
      if (!controller.signal.aborted) setState({ query, result, loading: false, error: "" });
    }).catch(reason => {
      if (!controller.signal.aborted) setState({ query, result: null, loading: false, error: reason instanceof Error ? reason.message : "加载失败" });
    });
    return () => controller.abort();
  }, [query, active, activationGeneration, revision]);
  const current = state.query === query;
  return { result: current ? state.result : null, loading: !current || state.loading, error: current ? state.error : "", refresh: () => setRevision(value => value + 1) };
}
