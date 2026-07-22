import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";

export type PageRuntimeContextValue = {
  pageKey: string;
  active: boolean;
  activationGeneration: number;
};

const PageRuntimeContext = createContext<PageRuntimeContextValue | null>(null);

export function PageRuntimeProvider({
  children,
  value,
}: {
  children: ReactNode;
  value: PageRuntimeContextValue;
}) {
  const memoizedValue = useMemo(() => value, [value.active, value.activationGeneration, value.pageKey]);
  return (
    <PageRuntimeContext.Provider value={memoizedValue}>
      {children}
    </PageRuntimeContext.Provider>
  );
}

export function usePageActivation(expectedPageKey?: string) {
  const context = useContext(PageRuntimeContext);
  if (!context) {
    throw new Error("usePageActivation must be used within PageRuntimeProvider.");
  }
  if (expectedPageKey && expectedPageKey !== context.pageKey) {
    throw new Error(`usePageActivation expected pageKey "${expectedPageKey}" but received "${context.pageKey}".`);
  }
  return context;
}

export function useOptionalPageActivation(expectedPageKey?: string) {
  const context = useContext(PageRuntimeContext);
  if (!context) {
    return { pageKey: expectedPageKey ?? "standalone", active: true, activationGeneration: 0 };
  }
  if (expectedPageKey && expectedPageKey !== context.pageKey) {
    throw new Error(`useOptionalPageActivation expected pageKey "${expectedPageKey}" but received "${context.pageKey}".`);
  }
  return context;
}

export function useActivePageEvent<EventType extends Event = Event>(
  eventName: string,
  handler: (event: EventType) => void,
) {
  const { active } = usePageActivation();
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const eventListener = (event: Event) => {
    if (active && document.visibilityState !== "hidden") {
      handlerRef.current(event as EventType);
    }
    };
    window.addEventListener(eventName, eventListener);
    return () => window.removeEventListener(eventName, eventListener);
  }, [active, eventName]);
}
