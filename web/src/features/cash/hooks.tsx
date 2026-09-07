import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cashRequest, cashQueryString, CashRequestError, type CashQueryParams } from "./api";

type CashScope = { revision: number; refresh: () => void; deny: () => void; saved: () => void };
const CashContext = createContext<CashScope | null>(null);

/** Only mounted inside the cash route; no persistent storage or global event bus. */
export function CashProvider({ children }: { children: ReactNode }) {
  const [revision, setRevision] = useState(0);
  const [denied, setDenied] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const deny = useCallback(() => setDenied(true), []);
  const saved = useCallback(() => { setSavedNotice(true); setRevision(value => value + 1); }, []);
  const value = useMemo(() => ({ revision, refresh, deny, saved }), [revision, refresh, deny, saved]);
  return <CashContext.Provider value={value}>{denied
    ? <p role="alert" className="cash-notice">现金账权限已失效，页面数据已清除。请重新登录或联系 005 账号确认权限。</p>
    : <>{savedNotice && <div className="cash-save-notice" role="status">操作已保存。若下方重新读取失败，请刷新查看，不必重复提交。<button type="button" aria-label="关闭保存提示" onClick={() => setSavedNotice(false)}>关闭</button></div>}{children}</>}</CashContext.Provider>;
}

export function useCashScope(): CashScope {
  const value = useContext(CashContext);
  if (!value) throw new Error("CashProvider is required.");
  return value;
}

export function useCashQuery<T>(path: string | null,
  params?: CashQueryParams, revision?: number) {
  const scope = useCashScope();
  const [localRevision, setLocalRevision] = useState(0);
  const [state, setState] = useState<{ key: string; data: T | null; loading: boolean; error: CashRequestError | null }>({ key: "", data: null, loading: true, error: null });
  let url: string | null = null;
  let inputError: CashRequestError | null = null;
  try {
    const query = cashQueryString(params);
    url = path === null ? null : `${path}${query ? `?${query}` : ""}`;
  } catch (error) {
    if (!(error instanceof CashRequestError)) throw error;
    inputError = error;
  }
  const errorMessage = inputError?.message;
  const key = `${url}:${errorMessage ?? ""}:${revision ?? scope.revision}:${localRevision}`;
  useEffect(() => {
    if (errorMessage) { setState({ key, data: null, loading: false, error: new CashRequestError(400, "cash_filter_limit", errorMessage) }); return; }
    if (url === null) { setState({ key, data: null, loading: false, error: null }); return; }
    const controller = new AbortController();
    setState({ key, data: null, loading: true, error: null });
    void cashRequest<T>(url, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ key, data, loading: false, error: null });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      if (!(error instanceof CashRequestError)) throw error;
      if (error.status === 401 || error.status === 403) scope.deny();
      setState({ key, data: null, loading: false, error });
    });
    return () => controller.abort();
  }, [url, key, scope.deny, errorMessage]);
  const reload = useCallback(() => setLocalRevision(value => value + 1), []);
  return { ...(state.key === key ? state : { data: null, loading: url !== null, error: null }), reload };
}

export function useCashMutation() {
  const scope = useCashScope();
  const controller = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<CashRequestError | null>(null);
  useEffect(() => () => { controller.current?.abort(); }, []);
  const clearError = useCallback(() => setError(null), []);
  const run = useCallback(async <T,>(path: string, body: unknown, method = "POST"): Promise<T | null> => {
    if (controller.current) return null;
    const active = new AbortController();
    controller.current = active;
    setBusy(true); setError(null);
    try {
      const result = await cashRequest<T>(path, { method, body, signal: active.signal });
      if (active.signal.aborted) return null;
      scope.saved();
      return result;
    } catch (failure) {
      if (active.signal.aborted) return null;
      if (!(failure instanceof CashRequestError)) throw failure;
      if (failure.status === 401 || failure.status === 403) scope.deny();
      setError(failure);
      return null;
    } finally {
      controller.current = null;
      if (!active.signal.aborted) setBusy(false);
    }
  }, [scope.saved, scope.deny]);
  return { run, busy, error, clearError };
}
