import { expect, type ConsoleMessage, type Page, type Request, type Response } from "@playwright/test";

type PageDiagnosticEvent = {
  category: string;
  detail: string;
};

export type PageDiagnostics = {
  events: PageDiagnosticEvent[];
  dispose: () => void;
};

const MAX_DIAGNOSTIC_EVENTS = 40;
const DEFAULT_PAGE_READY_TIMEOUT_MS = 15_000;

function boundedPush(events: PageDiagnosticEvent[], event: PageDiagnosticEvent) {
  events.push(event);
  if (events.length > MAX_DIAGNOSTIC_EVENTS) {
    events.splice(0, events.length - MAX_DIAGNOSTIC_EVENTS);
  }
}

function shortUrl(value: string) {
  try {
    const url = new URL(value);
    return `${url.pathname}${url.search}`;
  } catch {
    return value;
  }
}

function relevantRequest(request: Request) {
  return ["document", "script", "stylesheet", "xhr", "fetch"].includes(request.resourceType());
}

export function startPageDiagnostics(page: Page): PageDiagnostics {
  const events: PageDiagnosticEvent[] = [];

  const onConsole = (message: ConsoleMessage) => {
    if (message.type() === "debug") {
      return;
    }
    boundedPush(events, {
      category: `console:${message.type()}`,
      detail: message.text(),
    });
  };
  const onPageError = (error: Error) => {
    boundedPush(events, {
      category: "pageerror",
      detail: error.stack || error.message,
    });
  };
  const onRequest = (request: Request) => {
    if (!relevantRequest(request)) {
      return;
    }
    boundedPush(events, {
      category: `request:${request.resourceType()}`,
      detail: `${request.method()} ${shortUrl(request.url())}`,
    });
  };
  const onRequestFailed = (request: Request) => {
    boundedPush(events, {
      category: `requestfailed:${request.resourceType()}`,
      detail: `${request.method()} ${shortUrl(request.url())} ${request.failure()?.errorText ?? ""}`.trim(),
    });
  };
  const onResponse = (response: Response) => {
    if (response.status() < 400) {
      return;
    }
    boundedPush(events, {
      category: `response:${response.status()}`,
      detail: `${response.request().method()} ${shortUrl(response.url())}`,
    });
  };

  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("request", onRequest);
  page.on("requestfailed", onRequestFailed);
  page.on("response", onResponse);

  return {
    events,
    dispose: () => {
      page.off("console", onConsole);
      page.off("pageerror", onPageError);
      page.off("request", onRequest);
      page.off("requestfailed", onRequestFailed);
      page.off("response", onResponse);
    },
  };
}

async function pageRouteFallbacks(page: Page) {
  return page.locator('[data-testid^="page-route-loading-"]').evaluateAll((nodes) => nodes.map((node) => ({
    testId: node.getAttribute("data-testid") ?? "",
    text: (node.textContent ?? "").trim(),
  }))).catch((caught: unknown) => [{
    testId: "diagnostic-error",
    text: caught instanceof Error ? caught.message : String(caught),
  }]);
}

async function compactMainText(page: Page) {
  const text = await page.locator("main").innerText({ timeout: 500 }).catch(() => "");
  return text.replace(/\s+/g, " ").trim().slice(0, 500);
}

async function buildPageReadyFailureMessage(
  page: Page,
  testId: string,
  routeDescription: string,
  diagnostics: PageDiagnostics,
  caught: unknown,
) {
  const fallbacks = await pageRouteFallbacks(page);
  const mainText = await compactMainText(page);
  const eventLines = diagnostics.events.length
    ? diagnostics.events.map((event) => `- ${event.category}: ${event.detail}`).join("\n")
    : "- no console/pageerror/request failure events captured";
  const fallbackLines = fallbacks.length
    ? fallbacks.map((fallback) => `- ${fallback.testId}: ${fallback.text}`).join("\n")
    : "- none";
  const originalMessage = caught instanceof Error ? caught.message : String(caught);

  return [
    `Timed out waiting for page root "${testId}" after navigating to ${routeDescription}.`,
    `Current URL: ${page.url()}`,
    "Route-level loading fallbacks:",
    fallbackLines,
    "Main text:",
    mainText || "- empty",
    "Recent browser diagnostics:",
    eventLines,
    "Original Playwright error:",
    originalMessage,
  ].join("\n");
}

export async function expectPageReady(
  page: Page,
  testId: string,
  options: {
    diagnostics?: PageDiagnostics;
    routeDescription?: string;
    timeoutMs?: number;
  } = {},
) {
  const diagnostics = options.diagnostics ?? startPageDiagnostics(page);
  try {
    await expect(page.getByTestId(testId)).toBeVisible({
      timeout: options.timeoutMs ?? DEFAULT_PAGE_READY_TIMEOUT_MS,
    });
  } catch (caught) {
    throw new Error(await buildPageReadyFailureMessage(
      page,
      testId,
      options.routeDescription ?? page.url(),
      diagnostics,
      caught,
    ));
  } finally {
    if (!options.diagnostics) {
      diagnostics.dispose();
    }
  }
}

export async function gotoAndExpectPageReady(
  page: Page,
  path: string,
  testId: string,
  options: {
    diagnostics?: PageDiagnostics;
    timeoutMs?: number;
  } = {},
) {
  const diagnostics = options.diagnostics ?? startPageDiagnostics(page);
  try {
    await page.goto(path);
    await expectPageReady(page, testId, {
      diagnostics,
      routeDescription: path,
      timeoutMs: options.timeoutMs,
    });
  } finally {
    if (!options.diagnostics) {
      diagnostics.dispose();
    }
  }
}
