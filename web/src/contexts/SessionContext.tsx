import { createContext, startTransition, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchSessionMe, SessionApiError, type SessionPayload } from "../features/session/api";

const SESSION_BOOTSTRAP_TIMEOUT_RETRY_LIMIT = 2;
const SESSION_BOOTSTRAP_RETRY_DELAY_MS = 1_000;

export type SessionState =
  | { status: "loading" }
  | { status: "authenticated"; session: SessionPayload }
  | { status: "forbidden"; session: SessionPayload }
  | { status: "expired"; message: string }
  | { status: "error"; message: string };

export type SessionContextValue = SessionState & {
  refresh: () => void;
};

export const SessionContext = createContext<SessionContextValue | null>(null);

function normalizeSessionFailure(error: unknown): Extract<SessionState, { status: "expired" | "error" }> {
  if (error instanceof SessionApiError) {
    if (error.status === 401) {
      return {
        status: "expired",
        message: error.message || "请返回 OA 系统重新登录后再进入财务运营平台。",
      };
    }
    return {
      status: "error",
      message: error.message || "会话校验失败，请稍后重试。",
    };
  }
  return {
    status: "error",
    message: "会话校验失败，请稍后重试。",
  };
}

function shouldRetrySessionBootstrap(error: unknown, attempt: number) {
  return (
    error instanceof SessionApiError
    && error.status === 0
    && error.code === "request_timeout"
    && attempt <= SESSION_BOOTSTRAP_TIMEOUT_RETRY_LIMIT
  );
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let activeController: AbortController | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    startTransition(() => {
      setState({ status: "loading" });
    });

    const loadSession = () => {
      attempt += 1;
      const controller = new AbortController();
      activeController = controller;

      fetchSessionMe(controller.signal)
        .then((session) => {
          if (cancelled) {
            return;
          }
          startTransition(() => {
            setState(session.allowed ? { status: "authenticated", session } : { status: "forbidden", session });
          });
        })
        .catch((error: unknown) => {
          if (cancelled || (error instanceof DOMException && error.name === "AbortError")) {
            return;
          }
          if (shouldRetrySessionBootstrap(error, attempt)) {
            retryTimer = setTimeout(loadSession, SESSION_BOOTSTRAP_RETRY_DELAY_MS);
            return;
          }
          startTransition(() => {
            setState(normalizeSessionFailure(error));
          });
        });
    };

    loadSession();

    return () => {
      cancelled = true;
      activeController?.abort();
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
      }
    };
  }, [reloadKey]);

  const value = useMemo<SessionContextValue>(
    () => ({
      ...state,
      refresh: () => {
        setReloadKey((value) => value + 1);
      },
    }),
    [state],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used within SessionProvider.");
  }
  return context;
}

export function useSessionPermissions() {
  const session = useSession();
  return sessionPermissionsFromContext(session);
}

export function useOptionalSessionPermissions() {
  const session = useContext(SessionContext);
  if (session === null) {
    return {
      accessTier: "denied",
      canAccessApp: false,
      canMutateData: false,
      canAdminAccess: false,
    } as const;
  }
  return sessionPermissionsFromContext(session);
}

function sessionPermissionsFromContext(session: SessionContextValue) {
  const authenticatedSession = session.status === "authenticated" ? session.session : null;
  return {
    accessTier: authenticatedSession?.accessTier ?? "denied",
    canAccessApp: authenticatedSession?.canAccessApp ?? false,
    canMutateData: authenticatedSession?.canMutateData ?? false,
    canAdminAccess: authenticatedSession?.canAdminAccess ?? false,
  } as const;
}
