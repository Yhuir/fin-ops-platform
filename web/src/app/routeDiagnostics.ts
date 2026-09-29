declare const __APP_BUILD_ID__: string;

export function reportRouteFailure(phase: "preload" | "render", route: string, error: unknown) {
  const failure = error instanceof Error ? error : null;
  // Do not log raw messages/stacks: rendering errors may contain business values.
  const asset = failure?.message.match(/\/fin-ops\/assets\/[A-Za-z0-9_.-]+\.(?:js|css)/)?.[0] ?? null;
  const diagnostic = {
    build: __APP_BUILD_ID__,
    route: route.split(/[?#]/)[0],
    phase,
    kind: asset ? "module_load_failed" : "page_failed",
    asset,
  };
  if (phase === "preload") {
    console.warn("fin-ops route failure", diagnostic);
  } else {
    console.error("fin-ops route failure", diagnostic);
  }
}
