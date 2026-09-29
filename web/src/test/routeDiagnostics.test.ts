import { afterEach, expect, test, vi } from "vitest";
import { reportRouteFailure } from "../app/routeDiagnostics";

afterEach(() => vi.restoreAllMocks());

test("keeps diagnostic fields useful without exposing queries or business values", () => {
  const report = vi.spyOn(console, "error").mockImplementation(() => undefined);
  reportRouteFailure("render", "/input-invoice-usage?token=secret", new Error(
    "private business value https://www.yn-sourcing.com/fin-ops/assets/Page-old.js?token=secret",
  ));
  const diagnostic = report.mock.calls[0][1];
  expect(diagnostic).toMatchObject({
    phase: "render", route: "/input-invoice-usage", kind: "module_load_failed", asset: "/fin-ops/assets/Page-old.js",
  });
  expect(diagnostic.build).toBe("test");
  expect(JSON.stringify(diagnostic)).not.toMatch(/secret|private|token/);
});

test("preloading reports a warning without hiding or navigating the current page", () => {
  const report = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  reportRouteFailure("preload", "/cash?section=flows", new Error("failure"));
  expect(report).toHaveBeenCalledWith("fin-ops route failure", expect.objectContaining({
    route: "/cash", phase: "preload", kind: "page_failed", asset: null,
  }));
});
