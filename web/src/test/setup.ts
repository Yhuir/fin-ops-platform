import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";

// JSDOM does not implement Web Animations. Native Tabs indicators are exercised in Playwright.
Object.defineProperty(HTMLElement.prototype, "getAnimations", { configurable: true, value: () => [] });

// JSDOM has no layout observer; responsive geometry is verified in real Chromium.
beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn()})));
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: () => {
    const animation = { cancel: () => { animation.onfinish = null; }, onfinish: null as null | (() => void) };
    queueMicrotask(() => animation.onfinish?.());
    return animation;
  }});
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  try {
    const prefix = "finops:pageSession:v1:";
    Object.keys(window.sessionStorage).forEach((key) => {
      if (key.startsWith(prefix)) {
        window.sessionStorage.removeItem(key);
      }
    });
  } catch {
    // jsdom storage may be unavailable in a few isolated tests.
  }
});
