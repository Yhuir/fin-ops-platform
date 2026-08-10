import {
  expect,
  test as base,
  type ConsoleMessage,
  type Dialog,
  type Locator,
  type Page,
  type Request,
} from "@playwright/test";

export type { Download, TestInfo } from "@playwright/test";

type BrowserDiagnostic = {
  category: string;
  detail: string;
};

const MAX_BROWSER_DIAGNOSTICS = 30;
const productionDiagnosticsRedactionEnabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";

function pushDiagnostic(events: BrowserDiagnostic[], event: BrowserDiagnostic) {
  events.push(event);
  if (events.length > MAX_BROWSER_DIAGNOSTICS) {
    events.splice(0, events.length - MAX_BROWSER_DIAGNOSTICS);
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

function redactProductionPath(value: string) {
  try {
    const url = new URL(value, "https://production-smoke.local");
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "api") {
      return "/api/<redacted>";
    }
    if (parts[0] === "fin-ops") {
      return parts[1] ? `/fin-ops/${parts[1]}/<redacted>` : "/fin-ops/";
    }
    return parts[0] ? `/${parts[0]}/<redacted>` : "/";
  } catch {
    return "<redacted>";
  }
}

function redactProductionDiagnosticDetail(event: BrowserDiagnostic) {
  if (!productionDiagnosticsRedactionEnabled) {
    return event;
  }
  if (event.category === "requestfailed") {
    const [method = "REQUEST", url = ""] = event.detail.split(/\s+/, 2);
    return { ...event, detail: `${method} ${redactProductionPath(url)} request_failed` };
  }
  return { ...event, detail: "<redacted>" };
}

function relevantFailedRequest(request: Request) {
  return ["document", "script", "stylesheet", "xhr", "fetch"].includes(request.resourceType());
}

function isExpectedBrowserNetworkConsole(text: string) {
  return /Failed to load resource: the server responded with a status of \d{3} \(/.test(text);
}

function isExpectedLifecycleAbort(request: Request) {
  return request.failure()?.errorText.includes("net::ERR_ABORTED") ?? false;
}

function pushBrowserDiagnostic(events: BrowserDiagnostic[], event: BrowserDiagnostic) {
  pushDiagnostic(events, redactProductionDiagnosticDetail(event));
}

export const test = base.extend<{ browserDiagnostics: BrowserDiagnostic[] }>({
  browserDiagnostics: [async ({ page }, use) => {
    const diagnostics: BrowserDiagnostic[] = [];

    const onConsole = (message: ConsoleMessage) => {
      if (message.type() === "error") {
        const text = message.text();
        if (!isExpectedBrowserNetworkConsole(text)) {
          pushBrowserDiagnostic(diagnostics, { category: "console.error", detail: text });
        }
      }
    };
    const onPageError = (error: Error) => {
      pushBrowserDiagnostic(diagnostics, { category: "pageerror", detail: error.stack || error.message });
    };
    const onRequestFailed = (request: Request) => {
      if (!relevantFailedRequest(request) || isExpectedLifecycleAbort(request)) {
        return;
      }
      pushBrowserDiagnostic(diagnostics, {
        category: "requestfailed",
        detail: `${request.method()} ${shortUrl(request.url())} ${request.failure()?.errorText ?? ""}`.trim(),
      });
    };
    const onDialog = async (dialog: Dialog) => {
      pushBrowserDiagnostic(diagnostics, {
        category: "dialog",
        detail: `${dialog.type()} ${dialog.message()}`,
      });
      await dialog.dismiss().catch(() => undefined);
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    page.on("requestfailed", onRequestFailed);
    page.on("dialog", onDialog);

    await use(diagnostics);

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("requestfailed", onRequestFailed);
    page.off("dialog", onDialog);

    expect(diagnostics, [
      "Unexpected browser diagnostics were captured.",
      ...diagnostics.map((event) => `- ${event.category}: ${event.detail}`),
    ].join("\n")).toEqual([]);
  }, { auto: true }],
});

export async function setCheckbox(checkbox: Locator, selected = true) {
  if (await checkbox.isChecked() === selected) {
    return;
  }
  const label = checkbox.locator("xpath=ancestor::label[1]");
  await (await label.count() ? label : checkbox).click();
}

export { expect, type Locator, type Page, type Request };
