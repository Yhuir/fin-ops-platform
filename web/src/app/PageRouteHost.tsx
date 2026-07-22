import { Navigate, matchPath, useLocation } from "react-router-dom";
import { Suspense, useEffect, useMemo, useState } from "react";

import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import type { AppPageRoute } from "./pageRegistry";

function routeMatchesPath(route: AppPageRoute, pathname: string) {
  return Boolean(matchPath({ path: route.path, end: route.end ?? true }, pathname));
}

function findRoute(routes: AppPageRoute[], pathname: string) {
  return routes.find((route) => routeMatchesPath(route, pathname)) ?? null;
}

function PageRouteFallback({ pageKey }: { pageKey: string }) {
  return (
    <div className="page-route-loading" data-testid={`page-route-loading-${pageKey}`} role="status" aria-live="polite">
      正在加载页面
    </div>
  );
}

export default function PageRouteHost({ routes }: { routes: AppPageRoute[] }) {
  const location = useLocation();
  const matchedRoute = useMemo(() => findRoute(routes, location.pathname), [location.pathname, routes]);
  const [runtime, setRuntime] = useState(() => ({
    active: document.visibilityState !== "hidden",
    activationGeneration: 1,
  }));

  useEffect(() => {
    const setActive = (active: boolean, reactivate = false) => {
      setRuntime((current) => {
        if (current.active === active && !reactivate) {
          return current;
        }
        return {
          active,
          activationGeneration: active && (!current.active || reactivate)
            ? current.activationGeneration + 1
            : current.activationGeneration,
        };
      });
    };
    const handleFocus = () => setActive(document.visibilityState !== "hidden", true);
    const handleBlur = () => setActive(false);
    const handleVisibilityChange = () => setActive(document.visibilityState !== "hidden");

    window.addEventListener("focus", handleFocus);
    window.addEventListener("blur", handleBlur);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("blur", handleBlur);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  if (!matchedRoute) {
    return <Navigate replace to="/" />;
  }

  const PageComponent = matchedRoute.component;

  return (
    <PageRuntimeProvider
      value={{
        pageKey: matchedRoute.pageKey,
        active: runtime.active,
        activationGeneration: runtime.activationGeneration,
      }}
    >
      <Suspense fallback={<PageRouteFallback pageKey={matchedRoute.pageKey} />}>
        <PageComponent />
      </Suspense>
    </PageRuntimeProvider>
  );
}
