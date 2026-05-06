import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

afterEach(() => {
  vi.restoreAllMocks();
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
