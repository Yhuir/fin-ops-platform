function normalizeBasePath(value: string | undefined): string {
  const trimmed = String(value ?? "/").trim();
  if (trimmed.length === 0 || trimmed === "/") {
    return "/";
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return withLeadingSlash.endsWith("/") ? withLeadingSlash : `${withLeadingSlash}/`;
}

function isEmbeddedInFrame(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

export const APP_BASE_PATH = normalizeBasePath(import.meta.env.VITE_APP_BASE_PATH);
export const API_BASE_PATH = normalizeBasePath(
  import.meta.env.VITE_API_BASE_PATH ?? (APP_BASE_PATH === "/fin-ops/" ? "/fin-ops-api/" : "/"),
);

export function apiUrl(path: string): string {
  const trimmed = String(path).trim();
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  if (API_BASE_PATH === "/") {
    return withLeadingSlash;
  }
  return `${API_BASE_PATH.slice(0, -1)}${withLeadingSlash}`;
}

export function isOaEmbeddedMode(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  return params.get("embedded") === "oa" || isEmbeddedInFrame();
}
