import { useEffect, useRef } from "react";

import { useOptionalPageSessionState } from "../contexts/PageSessionStateContext";

type ScrollPosition = {
  top: number;
  left: number;
};

export type PageScrollSessionOptions = {
  pageKey: string;
  scrollKey: string;
  ttlMs?: number;
  debounceMs?: number;
  version?: number;
};

const DEFAULT_SCROLL_SESSION_TTL_MS = 24 * 60 * 60 * 1000;

function isScrollPosition(value: unknown): value is ScrollPosition {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Record<string, unknown>;
  return (
    typeof payload.top === "number"
    && Number.isFinite(payload.top)
    && typeof payload.left === "number"
    && Number.isFinite(payload.left)
  );
}

function normalizeScrollPosition(value: ScrollPosition): ScrollPosition {
  return {
    top: Math.max(0, Math.round(value.top)),
    left: Math.max(0, Math.round(value.left)),
  };
}

export function usePageScrollSession<ElementType extends HTMLElement>({
  pageKey,
  scrollKey,
  ttlMs = DEFAULT_SCROLL_SESSION_TTL_MS,
  debounceMs = 100,
  version = 1,
}: PageScrollSessionOptions) {
  const elementRef = useRef<ElementType | null>(null);
  const restoredRef = useRef(false);
  const session = useOptionalPageSessionState<ScrollPosition>({
    pageKey,
    stateKey: `scroll.${scrollKey}`,
    version,
    initialValue: { top: 0, left: 0 },
    ttlMs,
    storage: "session",
    validate: isScrollPosition,
    debounceMs,
  });
  const sessionValueRef = useRef(session.value);

  useEffect(() => {
    sessionValueRef.current = session.value;
  }, [session.value]);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) {
      return undefined;
    }

    if (!restoredRef.current) {
      element.scrollTop = sessionValueRef.current.top;
      element.scrollLeft = sessionValueRef.current.left;
      restoredRef.current = true;
    }

    const persistScroll = () => {
      session.setValue(normalizeScrollPosition({
        top: element.scrollTop,
        left: element.scrollLeft,
      }));
    };

    element.addEventListener("scroll", persistScroll, { passive: true });
    return () => {
      persistScroll();
      element.removeEventListener("scroll", persistScroll);
    };
  }, [session.setValue]);

  return elementRef;
}
