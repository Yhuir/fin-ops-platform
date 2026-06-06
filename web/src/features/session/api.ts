import { ApiClientError, apiRequestJson } from "../apiClient";

export { readOATokenCookie } from "../authToken";

export const SESSION_BOOTSTRAP_TIMEOUT_MS = 10_000;

export type SessionAccessTier = "denied" | "read_export_only" | "full_access" | "admin";

export type SessionUser = {
  userId: string;
  username: string;
  nickname: string;
  displayName: string;
  deptId?: string | null;
  deptName?: string | null;
  avatar?: string | null;
};

export type SessionPayload = {
  user: SessionUser;
  roles: string[];
  permissions: string[];
  allowed: boolean;
  accessTier: SessionAccessTier;
  canAccessApp: boolean;
  canMutateData: boolean;
  canAdminAccess: boolean;
};

type ApiSessionPayload = {
  user: {
    user_id: string;
    username: string;
    nickname?: string | null;
    display_name?: string | null;
    dept_id?: string | null;
    dept_name?: string | null;
    avatar?: string | null;
  };
  roles?: string[];
  permissions?: string[];
  allowed?: boolean;
  access_tier?: SessionAccessTier;
  can_access_app?: boolean;
  can_mutate_data?: boolean;
  can_admin_access?: boolean;
};

type ApiErrorPayload = {
  error?: string;
  message?: string;
};

export class SessionApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "SessionApiError";
    this.status = status;
    this.code = code;
  }
}

function normalizeString(value: string | null | undefined, fallback = "") {
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : fallback;
}

function normalizeArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item ?? "").trim())
    .filter((item, index, list) => item.length > 0 && list.indexOf(item) === index);
}

export async function fetchSessionMe(signal?: AbortSignal): Promise<SessionPayload> {
  let payload: ApiSessionPayload | null = null;
  try {
    payload = await apiRequestJson<ApiSessionPayload>("/api/session/me", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      signal,
    }, {
      timeoutMs: SESSION_BOOTSTRAP_TIMEOUT_MS,
      timeoutMessage: "OA 会话校验超时，请检查网络或稍后重试。",
    });
  } catch (error) {
    if (error instanceof ApiClientError) {
      const errorPayload = error.payload as ApiErrorPayload | null;
      throw new SessionApiError(
        normalizeString(errorPayload?.message, normalizeString(error.message, "会话校验失败，请稍后重试。")),
        error.status,
        typeof errorPayload?.error === "string" ? errorPayload.error : error.code,
      );
    }
    throw error;
  }

  const sessionPayload = payload as ApiSessionPayload | null;
  if (!sessionPayload?.user) {
    throw new SessionApiError("会话信息缺少当前用户。", 200);
  }

  return {
    user: {
      userId: normalizeString(sessionPayload.user.user_id),
      username: normalizeString(sessionPayload.user.username),
      nickname: normalizeString(sessionPayload.user.nickname),
      displayName: normalizeString(
        sessionPayload.user.display_name,
        normalizeString(sessionPayload.user.nickname, normalizeString(sessionPayload.user.username)),
      ),
      deptId: normalizeString(sessionPayload.user.dept_id) || null,
      deptName: normalizeString(sessionPayload.user.dept_name) || null,
      avatar: normalizeString(sessionPayload.user.avatar) || null,
    },
    roles: normalizeArray(sessionPayload.roles),
    permissions: normalizeArray(sessionPayload.permissions),
    allowed: Boolean(sessionPayload.allowed),
    accessTier: (sessionPayload.access_tier ?? "denied") as SessionAccessTier,
    canAccessApp: Boolean(sessionPayload.can_access_app ?? sessionPayload.allowed),
    canMutateData: Boolean(sessionPayload.can_mutate_data),
    canAdminAccess: Boolean(sessionPayload.can_admin_access),
  };
}
