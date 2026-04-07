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

export function isOaEmbeddedMode(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  return params.get("embedded") === "oa" || isEmbeddedInFrame();
}
