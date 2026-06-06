import { Navigate, matchPath, useLocation } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import { usePageSessionScope } from "../contexts/PageSessionStateContext";
import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import type { AppPageRoute } from "./pageRegistry";

type CachedPage = {
  route: AppPageRoute;
  lastActiveAt: number;
  activationGeneration: number;
};

type PageCacheState = {
  scopeKey: string;
  pages: CachedPage[];
};

const DEFAULT_MAX_ENTRIES = 20;

function routeMatchesPath(route: AppPageRoute, pathname: string) {
  return Boolean(matchPath({ path: route.path, end: route.end ?? true }, pathname));
}

function findRoute(routes: AppPageRoute[], pathname: string) {
  return routes.find((route) => routeMatchesPath(route, pathname)) ?? null;
}

function createCachedPage(route: AppPageRoute, now: number): CachedPage {
  return {
    route,
    lastActiveAt: now,
    activationGeneration: 1,
  };
}

function pruneCachedPages(entries: CachedPage[], activePageKey: string, now: number, maxEntries: number) {
  const byIdleTtl = entries.filter((entry) => {
    if (entry.route.pageKey === activePageKey) {
      return true;
    }
    if (!entry.route.maxIdleMs) {
      return true;
    }
    return now - entry.lastActiveAt <= entry.route.maxIdleMs;
  });
  if (byIdleTtl.length <= maxEntries) {
    return byIdleTtl;
  }
  const activeEntry = byIdleTtl.find((entry) => entry.route.pageKey === activePageKey);
  const inactiveEntries = byIdleTtl
    .filter((entry) => entry.route.pageKey !== activePageKey)
    .sort((left, right) => right.lastActiveAt - left.lastActiveAt)
    .slice(0, Math.max(0, maxEntries - (activeEntry ? 1 : 0)));
  return activeEntry ? [...inactiveEntries, activeEntry] : inactiveEntries.slice(0, maxEntries);
}

function upsertCachedPage(entries: CachedPage[], route: AppPageRoute, now: number, maxEntries: number) {
  const existing = entries.find((entry) => entry.route.pageKey === route.pageKey);
  const nextEntry = existing
    ? {
      ...existing,
      route,
      lastActiveAt: now,
      activationGeneration: existing.activationGeneration + 1,
    }
    : createCachedPage(route, now);
  const withoutCurrent = entries.filter((entry) => entry.route.pageKey !== route.pageKey);
  return pruneCachedPages([...withoutCurrent, nextEntry], route.pageKey, now, maxEntries);
}

function sameCachedPages(left: CachedPage[], right: CachedPage[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((entry, index) => {
    const other = right[index];
    return (
      entry.route.pageKey === other.route.pageKey
      && entry.route.path === other.route.path
      && entry.lastActiveAt === other.lastActiveAt
      && entry.activationGeneration === other.activationGeneration
    );
  });
}

export default function PageKeepAliveHost({
  routes,
  maxEntries = DEFAULT_MAX_ENTRIES,
}: {
  routes: AppPageRoute[];
  maxEntries?: number;
}) {
  const location = useLocation();
  const { userScope, generation } = usePageSessionScope();
  const matchedRoute = useMemo(() => findRoute(routes, location.pathname), [location.pathname, routes]);
  const sessionScopeKey = `${userScope}:${generation}`;
  const [cacheState, setCacheState] = useState<PageCacheState>({
    scopeKey: sessionScopeKey,
    pages: [],
  });
  const cachedPages = cacheState.scopeKey === sessionScopeKey ? cacheState.pages : [];

  useEffect(() => {
    if (!matchedRoute?.keepAlive) {
      return;
    }
    const now = Date.now();
    setCacheState((current) => {
      const currentPages = current.scopeKey === sessionScopeKey ? current.pages : [];
      const nextPages = upsertCachedPage(currentPages, matchedRoute, now, maxEntries);
      if (current.scopeKey === sessionScopeKey && sameCachedPages(currentPages, nextPages)) {
        return current;
      }
      return {
        scopeKey: sessionScopeKey,
        pages: nextPages,
      };
    });
  }, [matchedRoute, maxEntries, sessionScopeKey]);

  if (!matchedRoute) {
    return <Navigate replace to="/" />;
  }

  if (!matchedRoute.keepAlive) {
    const CurrentComponent = matchedRoute.component;
    return (
      <PageRuntimeProvider
        value={{
          pageKey: matchedRoute.pageKey,
          active: true,
          activationGeneration: 1,
        }}
      >
        <CurrentComponent />
      </PageRuntimeProvider>
    );
  }

  const entriesForRender = cachedPages.some((entry) => entry.route.pageKey === matchedRoute.pageKey)
    ? cachedPages
    : [...cachedPages, createCachedPage(matchedRoute, Date.now())];

  return (
    <>
      {entriesForRender.map((entry) => {
        const active = entry.route.pageKey === matchedRoute.pageKey;
        const PageComponent = entry.route.component;
        const inertProps = active ? {} : { inert: true };
        return (
          <div
            key={`${sessionScopeKey}:${entry.route.pageKey}:v${entry.route.sessionVersion}`}
            data-testid={`page-frame-${entry.route.pageKey}`}
            data-page-key={entry.route.pageKey}
            aria-hidden={active ? "false" : "true"}
            {...inertProps}
            style={{
              display: active ? "contents" : "none",
            }}
          >
            <PageRuntimeProvider
              value={{
                pageKey: entry.route.pageKey,
                active,
                activationGeneration: entry.activationGeneration,
              }}
            >
              <PageComponent />
            </PageRuntimeProvider>
          </div>
        );
      })}
    </>
  );
}
