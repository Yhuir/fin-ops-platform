import {
  createContext,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "./SessionContext";
import {
  buildPageSessionStorageKey,
  createStoredPayload,
  isStoredPayload,
  pageSessionUserPrefix,
  type PageSessionRestoreState,
  type PageSessionStorageKind,
  type PageSessionStoredPayload,
  safeReadSessionStorage,
  safeRemoveSessionStorage,
  safeRemoveSessionStoragePrefix,
  safeWriteSessionStorage,
} from "./pageSessionStorage";

export type PageSessionOptions<T> = {
  pageKey: string;
  stateKey: string;
  version: number;
  initialValue: T;
  ttlMs: number;
  storage: PageSessionStorageKind;
  persist?: (value: T) => unknown;
  restore?: (raw: unknown) => T;
  validate?: (value: unknown) => value is T;
  debounceMs?: number;
};

export type PageSessionStateResult<T> = {
  value: T;
  setValue: Dispatch<SetStateAction<T>>;
  reset: () => void;
  restoreState: PageSessionRestoreState;
};

type ReadResult<T> = {
  value: T;
  restoreState: PageSessionRestoreState;
};

type PageSessionStateContextValue = {
  userScope: string;
  generation: number;
  memoryStore: React.MutableRefObject<Map<string, PageSessionStoredPayload>>;
  clearAllForCurrentUser: () => void;
};

const PageSessionStateContext = createContext<PageSessionStateContextValue | null>(null);

function sessionUserScope(session: ReturnType<typeof useSession>) {
  if (session.status === "authenticated" || session.status === "forbidden") {
    const user = session.session.user;
    return user.userId || user.username || "unknown-user";
  }
  return `session-${session.status}`;
}

function readStoredValue<T>(params: {
  key: string;
  options: PageSessionOptions<T>;
  memoryStore: Map<string, PageSessionStoredPayload>;
  userStorageAvailableRef: React.MutableRefObject<boolean>;
}): ReadResult<T> {
  const { key, options, memoryStore, userStorageAvailableRef } = params;
  const rawPayload = options.storage === "memory"
    ? memoryStore.get(key) ?? null
    : (() => {
      const read = safeReadSessionStorage(key);
      if (!read.ok) {
        userStorageAvailableRef.current = false;
        return memoryStore.get(key) ?? null;
      }
      return read.payload;
    })();

  if (rawPayload === null) {
    return { value: options.initialValue, restoreState: userStorageAvailableRef.current ? "idle" : "unavailable" };
  }
  if (!isStoredPayload(rawPayload)) {
    memoryStore.delete(key);
    if (options.storage === "session") {
      safeRemoveSessionStorage(key);
    }
    return { value: options.initialValue, restoreState: "invalid" };
  }
  if (rawPayload.version !== options.version) {
    memoryStore.delete(key);
    if (options.storage === "session") {
      safeRemoveSessionStorage(key);
    }
    return { value: options.initialValue, restoreState: "invalid" };
  }
  if (rawPayload.expiresAt <= Date.now()) {
    memoryStore.delete(key);
    if (options.storage === "session") {
      safeRemoveSessionStorage(key);
    }
    return { value: options.initialValue, restoreState: "expired" };
  }

  try {
    const restoredValue = options.restore ? options.restore(rawPayload.value) : rawPayload.value;
    if (options.validate && !options.validate(restoredValue)) {
      memoryStore.delete(key);
      if (options.storage === "session") {
        safeRemoveSessionStorage(key);
      }
      return { value: options.initialValue, restoreState: "invalid" };
    }
    return { value: restoredValue as T, restoreState: "restored" };
  } catch {
    memoryStore.delete(key);
    if (options.storage === "session") {
      safeRemoveSessionStorage(key);
    }
    return { value: options.initialValue, restoreState: "invalid" };
  }
}

export function PageSessionStateProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const userScope = sessionUserScope(session);
  const memoryStore = useRef(new Map<string, PageSessionStoredPayload>());
  const previousUserScope = useRef(userScope);
  const [generation, setGeneration] = useState(0);

  const clearAllForCurrentUser = useCallback(() => {
    const prefix = pageSessionUserPrefix(userScope);
    Array.from(memoryStore.current.keys()).forEach((key) => {
      if (key.startsWith(prefix)) {
        memoryStore.current.delete(key);
      }
    });
    safeRemoveSessionStoragePrefix(prefix);
    setGeneration((current) => current + 1);
  }, [userScope]);

  useEffect(() => {
    if (previousUserScope.current === userScope) {
      return;
    }
    const previousPrefix = pageSessionUserPrefix(previousUserScope.current);
    Array.from(memoryStore.current.keys()).forEach((key) => {
      if (key.startsWith(previousPrefix)) {
        memoryStore.current.delete(key);
      }
    });
    safeRemoveSessionStoragePrefix(previousPrefix);
    previousUserScope.current = userScope;
    setGeneration((current) => current + 1);
  }, [userScope]);

  useEffect(() => {
    if (session.status === "expired") {
      clearAllForCurrentUser();
    }
  }, [clearAllForCurrentUser, session.status]);

  const value = useMemo<PageSessionStateContextValue>(() => ({
    userScope,
    generation,
    memoryStore,
    clearAllForCurrentUser,
  }), [clearAllForCurrentUser, generation, userScope]);

  return (
    <PageSessionStateContext.Provider value={value}>
      {children}
    </PageSessionStateContext.Provider>
  );
}

export function usePageSessionState<T>(options: PageSessionOptions<T>): PageSessionStateResult<T> {
  const context = useContext(PageSessionStateContext);
  if (!context) {
    throw new Error("usePageSessionState must be used within PageSessionStateProvider.");
  }

  const optionsRef = useRef(options);
  optionsRef.current = options;
  const storageAvailableRef = useRef(true);
  const writeTimer = useRef<number | null>(null);
  const hasMountedRef = useRef(false);
  const key = useMemo(() => buildPageSessionStorageKey({
    userScope: context.userScope,
    pageKey: options.pageKey,
    stateKey: options.stateKey,
  }), [context.userScope, options.pageKey, options.stateKey]);
  const optionsSignature = `${options.version}:${options.ttlMs}:${options.storage}`;

  const readCurrent = useCallback(() => readStoredValue({
    key,
    options: optionsRef.current,
    memoryStore: context.memoryStore.current,
    userStorageAvailableRef: storageAvailableRef,
  }), [context.memoryStore, key]);

  const [state, setState] = useState<ReadResult<T>>(() => readCurrent());
  const valueRef = useRef(state.value);

  useEffect(() => {
    valueRef.current = state.value;
  }, [state.value]);

  const persistValue = useCallback((value: T) => {
    const currentOptions = optionsRef.current;
    const serializedValue = currentOptions.persist ? currentOptions.persist(value) : value;
    const payload = createStoredPayload({
      version: currentOptions.version,
      ttlMs: currentOptions.ttlMs,
      value: serializedValue,
    });
    context.memoryStore.current.set(key, payload);
    if (currentOptions.storage !== "session") {
      return;
    }
    const wrote = safeWriteSessionStorage(key, payload);
    if (!wrote) {
      storageAvailableRef.current = false;
    }
  }, [context.memoryStore, key]);

  const schedulePersist = useCallback((value: T) => {
    if (writeTimer.current !== null) {
      window.clearTimeout(writeTimer.current);
      writeTimer.current = null;
    }
    const debounceMs = optionsRef.current.debounceMs;
    if (debounceMs && debounceMs > 0) {
      writeTimer.current = window.setTimeout(() => {
        persistValue(value);
        writeTimer.current = null;
      }, debounceMs);
      return;
    }
    persistValue(value);
  }, [persistValue]);

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return () => {
        if (writeTimer.current !== null) {
          window.clearTimeout(writeTimer.current);
          writeTimer.current = null;
        }
      };
    }
    setState(readCurrent());
    return () => {
      if (writeTimer.current !== null) {
        window.clearTimeout(writeTimer.current);
        writeTimer.current = null;
      }
    };
  }, [context.generation, optionsSignature, readCurrent]);

  const setValue = useCallback<Dispatch<SetStateAction<T>>>((updater) => {
    const nextValue = typeof updater === "function"
      ? (updater as (current: T) => T)(valueRef.current)
      : updater;
    valueRef.current = nextValue;
    schedulePersist(nextValue);
    setState({
      value: nextValue,
      restoreState: storageAvailableRef.current ? "restored" : "unavailable",
    });
  }, [schedulePersist]);

  const reset = useCallback(() => {
    if (writeTimer.current !== null) {
      window.clearTimeout(writeTimer.current);
      writeTimer.current = null;
    }
    context.memoryStore.current.delete(key);
    const currentOptions = optionsRef.current;
    if (currentOptions.storage === "session") {
      safeRemoveSessionStorage(key);
    }
    valueRef.current = currentOptions.initialValue;
    setState({ value: currentOptions.initialValue, restoreState: "idle" });
  }, [context.memoryStore, key]);

  return {
    value: state.value,
    setValue,
    reset,
    restoreState: state.restoreState,
  };
}

export function useClearPageSessionState() {
  const context = useContext(PageSessionStateContext);
  if (!context) {
    throw new Error("useClearPageSessionState must be used within PageSessionStateProvider.");
  }
  return context.clearAllForCurrentUser;
}
