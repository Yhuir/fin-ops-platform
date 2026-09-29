import { useEffect, useState } from 'react';

export function useSourceDetail<T, R>(open: boolean, target: T | null, load: (target: T, signal?: AbortSignal) => Promise<R>) {
  const [result, setResult] = useState<{ target: T; load: typeof load; detail?: R; error?: string } | null>(null);
  useEffect(() => {
    setResult(null);
    if (!open || target === null) return;
    const controller = new AbortController();
    load(target, controller.signal).then(detail => {
      if (!controller.signal.aborted) setResult({ target, load, detail });
    }).catch(reason => {
      if (!controller.signal.aborted) setResult({ target, load, error: reason instanceof Error ? reason.message : '详情加载失败' });
    });
    return () => controller.abort();
  }, [open, target, load]);
  const current = open && result?.target === target && result?.load === load ? result : null;
  return { detail: current?.detail ?? null, error: current?.error ?? null,
    loading: open && target !== null && current === null };
}
