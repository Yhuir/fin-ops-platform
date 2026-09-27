import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

// JSDOM does not implement Web Animations. Native Tabs indicators are exercised in Playwright.
Object.defineProperty(HTMLElement.prototype, "getAnimations", { configurable: true, value: () => [] });

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
