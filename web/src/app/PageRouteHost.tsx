import { Navigate, matchPath, useLocation } from "react-router-dom";
import { Suspense, useEffect, useMemo } from "react";

import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import { useOptionalSessionPermissions } from "../contexts/SessionContext";
import { pageLabelForKey, type AppPageRoute } from "./pageRegistry";

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
  const { canAdminAccess } = useOptionalSessionPermissions();
  const matchedRoute = useMemo(() => findRoute(routes, location.pathname), [location.pathname, routes]);

  useEffect(() => {
    if (!matchedRoute) {
      return;
    }
    document.title = `${pageLabelForKey(matchedRoute.pageKey)} · 财务运营平台`;
    document.getElementById("main-content")?.focus({ preventScroll: true });
  }, [matchedRoute]);

  if (!matchedRoute) {
    return <Navigate replace to="/" />;
  }
  if (matchedRoute.requiresAdmin && !canAdminAccess) {
    return <Navigate replace to="/" />;
  }

  const PageComponent = matchedRoute.component;

  return (
    <PageRuntimeProvider
      value={{
        pageKey: matchedRoute.pageKey,
        active: true,
        activationGeneration: 1,
      }}
    >
      <Suspense fallback={<PageRouteFallback pageKey={matchedRoute.pageKey} />}>
        <PageComponent />
      </Suspense>
    </PageRuntimeProvider>
  );
}
