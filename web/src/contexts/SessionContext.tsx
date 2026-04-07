import { createContext, startTransition, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchSessionMe, SessionApiError, type SessionPayload } from "../features/session/api";

type SessionState =
  | { status: "loading" }
  | { status: "authenticated"; session: SessionPayload }
  | { status: "forbidden"; session: SessionPayload }
  | { status: "expired"; message: string }
  | { status: "error"; message: string };

type SessionContextValue = SessionState & {
  refresh: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

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

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    startTransition(() => {
      setState({ status: "loading" });
    });

    fetchSessionMe(controller.signal)
      .then((session) => {
        startTransition(() => {
          setState(session.allowed ? { status: "authenticated", session } : { status: "forbidden", session });
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        startTransition(() => {
          setState(normalizeSessionFailure(error));
        });
      });

    return () => {
      controller.abort();
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
