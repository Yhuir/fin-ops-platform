import { apiUrl } from "../app/runtime";
import { readOATokenCookie } from "./authToken";

type ApiErrorPayload = {
  error?: unknown;
  code?: unknown;
  message?: unknown;
};

export type ApiRequestJsonOptions = {
  defaultErrorMessage?: string;
};

export class ApiClientError extends Error {
  status: number;
  code: string;
  payload: unknown;
  responseText: string;
  url: string;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      payload?: unknown;
      responseText?: string;
      url: string;
    },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = options.status;
    this.code = options.code ?? "";
    this.payload = options.payload;
    this.responseText = options.responseText ?? "";
    this.url = options.url;
  }
}

export function looksLikeHtmlResponse(rawText: string, contentType = "") {
  const trimmedText = rawText.trim();
  return (
    /^<!doctype\s+html/i.test(trimmedText)
    || /^<html[\s>]/i.test(trimmedText)
    || contentType.toLowerCase().includes("text/html")
  );
}

function withApiHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

export function buildApiRequestInit(init: RequestInit = {}): RequestInit {
  return {
    ...init,
    headers: withApiHeaders(init.headers),
    credentials: init.credentials ?? "include",
  };
}

function stringField(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function errorMessageFromPayload(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object") {
    const directMessage = stringField((payload as ApiErrorPayload).message);
    if (directMessage) {
      return directMessage;
    }
    const errorValue = (payload as ApiErrorPayload).error;
    if (errorValue && typeof errorValue === "object") {
      const nestedMessage = stringField((errorValue as ApiErrorPayload).message);
      if (nestedMessage) {
        return nestedMessage;
      }
    }
    const errorCode = stringField(errorValue);
    if (errorCode) {
      return errorCode;
    }
  }
  return fallback;
}

function errorCodeFromPayload(payload: unknown) {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const errorValue = (payload as ApiErrorPayload).error;
  if (typeof errorValue === "string" && errorValue.trim()) {
    return errorValue.trim();
  }
  if (errorValue && typeof errorValue === "object") {
    const nestedCode = stringField((errorValue as ApiErrorPayload).code);
    if (nestedCode) {
      return nestedCode;
    }
  }
  return stringField((payload as ApiErrorPayload).code);
}

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(apiUrl(url), buildApiRequestInit(init));
}

export async function apiFetchResolved(resolvedUrl: string, init: RequestInit = {}): Promise<Response> {
  return fetch(resolvedUrl, buildApiRequestInit(init));
}

export async function apiRequestJson<T>(
  url: string,
  init: RequestInit = {},
  options: ApiRequestJsonOptions = {},
): Promise<T> {
  const resolvedUrl = apiUrl(url);
  const response = await fetch(resolvedUrl, buildApiRequestInit(init));
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  const contentType = response.headers?.get?.("Content-Type") ?? "";

  if (trimmedText && looksLikeHtmlResponse(trimmedText, contentType)) {
    throw new ApiClientError(
      `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务和代理路径已正常配置。`,
      {
        status: response.status,
        responseText: rawText,
        url: resolvedUrl,
      },
    );
  }

  let payload = {} as T;
  if (trimmedText) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch {
      throw new ApiClientError(
        contentType ? `接口 ${url} 返回的不是合法 JSON：${contentType}` : `接口 ${url} 返回的不是合法 JSON。`,
        {
          status: response.status,
          responseText: rawText,
          url: resolvedUrl,
        },
      );
    }
  }

  if (!response.ok) {
    const fallbackMessage = options.defaultErrorMessage ?? (trimmedText || "request failed");
    const message = errorMessageFromPayload(payload, fallbackMessage);
    throw new ApiClientError(message, {
      status: response.status,
      code: errorCodeFromPayload(payload),
      payload,
      responseText: rawText,
      url: resolvedUrl,
    });
  }

  return payload;
}
