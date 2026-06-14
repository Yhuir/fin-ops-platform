import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type GlobalOperationOverlayState =
  | {
    phase: "loading";
    title: string;
    message: string;
  }
  | {
    phase: "error";
    title: string;
    message: string;
  };

type GlobalOperationHelpers = {
  setMessage: (message: string) => void;
};

type GlobalOperationOptions<T> = {
  title?: string;
  loadingMessage: string;
  action: (helpers: GlobalOperationHelpers) => Promise<T> | T;
  errorTitle?: string;
  errorMessage?: (error: unknown) => string;
};

export type GlobalOperationOutcome<T> =
  | {
    status: "success";
    value: T;
  }
  | {
    status: "error";
    error: unknown;
  };

type GlobalOperationOverlayContextValue = {
  isBlocking: boolean;
  runOperation: <T>(options: GlobalOperationOptions<T>) => Promise<GlobalOperationOutcome<T>>;
};

const GlobalOperationOverlayContext = createContext<GlobalOperationOverlayContextValue | null>(null);

function defaultErrorMessage(error: unknown) {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "操作失败，请稍后重试。";
}

export function GlobalOperationOverlayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GlobalOperationOverlayState | null>(null);
  const stateRef = useRef<GlobalOperationOverlayState | null>(null);
  const blockingRef = useRef(false);

  const setOverlayState = useCallback((nextState: GlobalOperationOverlayState | null) => {
    stateRef.current = nextState;
    setState(nextState);
  }, []);

  const acknowledgeError = useCallback(() => {
    blockingRef.current = false;
    setOverlayState(null);
  }, [setOverlayState]);

  const runOperation = useCallback(async <T,>({
    title = "处理中",
    loadingMessage,
    action,
    errorTitle = "操作失败",
    errorMessage = defaultErrorMessage,
  }: GlobalOperationOptions<T>): Promise<GlobalOperationOutcome<T>> => {
    if (blockingRef.current || stateRef.current) {
      const error = new Error("已有操作正在同步，请稍后再试。");
      return { status: "error", error };
    }

    blockingRef.current = true;
    setOverlayState({ phase: "loading", title, message: loadingMessage });

    const helpers: GlobalOperationHelpers = {
      setMessage: (message: string) => {
        const normalized = message.trim();
        if (!normalized) {
          return;
        }
        setOverlayState(
          stateRef.current?.phase === "loading"
            ? { ...stateRef.current, message: normalized }
            : stateRef.current,
        );
      },
    };

    try {
      const value = await action(helpers);
      blockingRef.current = false;
      setOverlayState(null);
      return { status: "success", value };
    } catch (error) {
      setOverlayState({
        phase: "error",
        title: errorTitle,
        message: errorMessage(error),
      });
      return { status: "error", error };
    }
  }, [setOverlayState]);

  const value = useMemo<GlobalOperationOverlayContextValue>(
    () => ({
      isBlocking: state !== null,
      runOperation,
    }),
    [runOperation, state],
  );

  return (
    <GlobalOperationOverlayContext.Provider value={value}>
      {children}
      {state ? (
        <div aria-label="全局操作进度" aria-modal="true" className="global-operation-overlay" role="dialog">
          <div className="global-operation-overlay__panel">
            <div className="global-operation-overlay__title">{state.title}</div>
            <div className="global-operation-overlay__body">
              {state.phase === "loading" ? (
                <span aria-hidden="true" className="global-operation-overlay__spinner" />
              ) : null}
              <span>{state.message}</span>
            </div>
            {state.phase === "error" ? (
              <div className="global-operation-overlay__actions">
                <button className="primary-button" type="button" onClick={acknowledgeError}>
                  确定
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </GlobalOperationOverlayContext.Provider>
  );
}

export function useGlobalOperationOverlay() {
  const context = useContext(GlobalOperationOverlayContext);
  if (!context) {
    throw new Error("useGlobalOperationOverlay must be used within GlobalOperationOverlayProvider");
  }
  return context;
}
