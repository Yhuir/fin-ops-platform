import { apiFetch } from "../apiClient";

export class CashRequestError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "CashRequestError";
  }
}

export type CashQueryParams = Record<string, string | number | boolean | null | undefined | readonly (string | null)[]>;

export function cashQueryString(params: CashQueryParams = {}): string {
  const query = new URLSearchParams();
  let selected = 0;
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      if (!value.length) continue;
      selected += value.length;
      if (value.length > 50 || selected > 100) throw new CashRequestError(400, "cash_filter_limit", "每列最多选择 50 项，全部条件最多选择 100 项。查看全部请清空限制。");
      query.set(key, JSON.stringify(value));
    } else if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const encoded = query.toString();
  if (encoded.length > 6000) throw new CashRequestError(400, "cash_filter_limit", "筛选条件过长，请减少选择项或清空限制后查看全部。");
  return encoded;
}

/** Check the complete next query before replacing an already applied filter. */
export function cashQueryError(params: CashQueryParams): string | null {
  try { cashQueryString(params); return null; }
  catch (error) {
    if (error instanceof CashRequestError && error.code === "cash_filter_limit") return error.message;
    throw error;
  }
}

/** Cash has one HTTP boundary. Never retry through the ordinary financial API. */
export async function cashRequest<T>(path: string, options: {
  method?: string; body?: unknown; signal?: AbortSignal;
} = {}): Promise<T> {
  if (!/^\/[a-z][a-z0-9/-]*(?:\?[^#]*)?$/.test(path)) {
    throw new CashRequestError(0, "cash_invalid_path", "现金请求地址不正确。");
  }
  if (new TextEncoder().encode(path.split("?")[1] ?? "").length > 6000) {
    throw new CashRequestError(400, "cash_filter_limit", "筛选条件过长，请减少选择项。");
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15_000);
  try {
    const response = await apiFetch(`/api/cash${path}`, {
      method: options.method ?? "GET", signal: controller.signal, cache: "no-store",
      headers: options.body === undefined ? { Accept: "application/json" } : {
        Accept: "application/json", "Content-Type": "application/json",
      },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
    });
    if (response.status === 401 || response.status === 403) {
      throw new CashRequestError(response.status, "cash_access_denied", "现金账已不可用，请重新确认登录及页面权限。");
    }
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new CashRequestError(response.status, "cash_invalid_response", "现金服务返回格式不正确，请联系管理员。");
    }
    let payload: unknown;
    try { payload = await response.json(); }
    catch { throw new CashRequestError(response.status, "cash_invalid_response", "现金服务返回的 JSON 不完整。"); }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new CashRequestError(response.status, "cash_invalid_response", "现金服务返回结构不正确。");
    }
    if (!response.ok) {
      const error = payload as { error?: unknown; message?: unknown };
      if (typeof error.error !== "string" || typeof error.message !== "string") {
        throw new CashRequestError(response.status, "cash_invalid_response", "现金服务错误响应不完整。");
      }
      throw new CashRequestError(response.status, error.error, error.message);
    }
    return payload as T;
  } catch (error) {
    if (timedOut) throw new CashRequestError(0, "cash_timeout", "请求超时。保存结果可能已生效，请先刷新核对，再使用原表单重试。");
    if (error instanceof CashRequestError || controller.signal.aborted) throw error;
    throw new CashRequestError(0, "cash_network_error", "无法连接现金服务。保存结果可能已生效，请先刷新核对。");
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}
