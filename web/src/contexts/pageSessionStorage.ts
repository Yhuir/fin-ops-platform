export type PageSessionRestoreState = "idle" | "restored" | "expired" | "invalid" | "unavailable";

export type PageSessionStorageKind = "memory" | "session";

export type PageSessionStoredPayload = {
  version: number;
  updatedAt: number;
  expiresAt: number;
  value: unknown;
};

const STORAGE_PREFIX = "finops:pageSession:v1";

function normalizeKeyPart(value: string) {
  return value.trim().replace(/[^a-zA-Z0-9_.:-]/g, "_") || "default";
}

export function buildPageSessionStorageKey(params: {
  userScope: string;
  pageKey: string;
  stateKey: string;
}) {
  return [
    STORAGE_PREFIX,
    normalizeKeyPart(params.userScope),
    normalizeKeyPart(params.pageKey),
    normalizeKeyPart(params.stateKey),
  ].join(":");
}

export function isStoredPayload(value: unknown): value is PageSessionStoredPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Record<string, unknown>;
  return (
    typeof payload.version === "number"
    && typeof payload.updatedAt === "number"
    && typeof payload.expiresAt === "number"
    && Object.prototype.hasOwnProperty.call(payload, "value")
  );
}

export function createStoredPayload(params: {
  version: number;
  ttlMs: number;
  value: unknown;
  now?: number;
}): PageSessionStoredPayload {
  const now = params.now ?? Date.now();
  return {
    version: params.version,
    updatedAt: now,
    expiresAt: now + params.ttlMs,
    value: params.value,
  };
}

export function safeReadSessionStorage(key: string) {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) {
      return { ok: true as const, payload: null };
    }
    return { ok: true as const, payload: JSON.parse(raw) as unknown };
  } catch {
    return { ok: false as const };
  }
}

export function safeWriteSessionStorage(key: string, payload: PageSessionStoredPayload) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

export function safeRemoveSessionStorage(key: string) {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Storage can be unavailable in embedded shells; callers already keep memory state.
  }
}

export function safeRemoveSessionStoragePrefix(prefix: string) {
  try {
    const keys: string[] = [];
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith(prefix)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => window.sessionStorage.removeItem(key));
  } catch {
    // Storage can be unavailable in embedded shells.
  }
}

export function pageSessionUserPrefix(userScope: string) {
  return `${STORAGE_PREFIX}:${normalizeKeyPart(userScope)}:`;
}

