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

export function readOATokenCookie(cookieSource = typeof document !== "undefined" ? document.cookie : ""): string | null {
  const target = "Admin-Token=";
  const parts = cookieSource.split(";").map((item) => item.trim());
  for (const part of parts) {
    if (part.startsWith(target)) {
      const token = decodeURIComponent(part.slice(target.length)).trim();
      return token.length > 0 ? token : null;
    }
  }
  return null;
}

export async function fetchSessionMe(signal?: AbortSignal): Promise<SessionPayload> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  const token = readOATokenCookie();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch("/api/session/me", {
    method: "GET",
    headers,
    credentials: "include",
    signal,
  });

  const rawText = await response.text();
  let payload: ApiSessionPayload | ApiErrorPayload | null = null;
  if (rawText.trim().length > 0) {
    try {
      payload = JSON.parse(rawText) as ApiSessionPayload | ApiErrorPayload;
    } catch {
      throw new SessionApiError("会话校验返回了无效数据。", response.status);
    }
  }

  if (!response.ok) {
    const errorPayload = payload as ApiErrorPayload | null;
    throw new SessionApiError(
      normalizeString(errorPayload?.message, "会话校验失败，请稍后重试。"),
      response.status,
      errorPayload?.error,
    );
  }

  const sessionPayload = payload as ApiSessionPayload | null;
  if (!sessionPayload?.user) {
    throw new SessionApiError("会话信息缺少当前用户。", response.status);
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
  };
}
