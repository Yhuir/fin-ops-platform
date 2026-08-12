import { createHash } from "node:crypto";
import { readFile, rename, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import type { Page, TestInfo } from "@playwright/test";

type OperationLatencyField =
  | "firstVisibleResponseLatencyMs"
  | "apiLatencyMs"
  | "operationBarrierLatencyMs"
  | "finalSettledLatencyMs";

export type OperationLatencyMetadata = {
  route?: string;
  pageKey: string;
  module?: string;
  operationId: string;
  visibleLabel: string;
  actionType: string;
};

export type OperationLatencyMark = <T>(field: OperationLatencyField, observed: Promise<T>) => Promise<T>;
export type OperationLatencyRecorder = (
  metadata: OperationLatencyMetadata,
  run: (mark: OperationLatencyMark) => Promise<void>,
) => Promise<void>;

type OperationLatencyRecord = Required<Pick<OperationLatencyMetadata, "pageKey" | "operationId" | "visibleLabel" | "actionType">> & {
  route: string;
  module: string;
  startTimestamp: string;
  firstVisibleResponseLatencyMs: number | null;
  apiLatencyMs: number | null;
  operationBarrierLatencyMs: number | null;
  finalSettledLatencyMs: number | null;
  pass: boolean;
  failureReason: string | null;
};

function currentRoute(page: Page) {
  try {
    return new URL(page.url()).pathname;
  } catch {
    return page.url();
  }
}

function safeName(value: string) {
  return value.replace(/[^A-Za-z0-9_.-]+/g, "_");
}

function errorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export function createOperationLatencyRecorder(
  page: Page,
  testInfo: TestInfo,
  defaults: Pick<OperationLatencyMetadata, "route" | "pageKey" | "module">,
): OperationLatencyRecorder {
  return async (metadata, run) => {
    const startTimestamp = new Date().toISOString();
    const start = performance.now();
    const record: OperationLatencyRecord = {
      route: metadata.route ?? defaults.route ?? currentRoute(page),
      pageKey: metadata.pageKey ?? defaults.pageKey,
      module: metadata.module ?? defaults.module ?? metadata.pageKey ?? defaults.pageKey,
      operationId: metadata.operationId,
      visibleLabel: metadata.visibleLabel,
      actionType: metadata.actionType,
      startTimestamp,
      firstVisibleResponseLatencyMs: null,
      apiLatencyMs: null,
      operationBarrierLatencyMs: null,
      finalSettledLatencyMs: null,
      pass: false,
      failureReason: null,
    };

    const elapsed = () => Math.round((performance.now() - start) * 100) / 100;
    const mark: OperationLatencyMark = async (field, observed) => {
      const value = await observed;
      record[field] = elapsed();
      return value;
    };

    try {
      await run(mark);
      record.pass = true;
    } catch (error) {
      record.failureReason = errorMessage(error);
      throw error;
    } finally {
      if (!metadata.route && !defaults.route) {
        record.route = currentRoute(page);
      }
      const attachmentName = `operation-latency-${safeName(record.operationId)}.json`;
      const attachmentPath = testInfo.outputPath(attachmentName);
      await writeFile(attachmentPath, JSON.stringify(record, null, 2));
      await testInfo.attach(attachmentName, {
        path: attachmentPath,
        contentType: "application/json",
      });
    }
  };
}

export type WorkbenchDirectCommitVisibilityRunMode = "isolated" | "production_smoke";

export type WorkbenchDirectCommitVisibilitySampleBinding = {
  sample_id: string;
  batch_id: string;
  transaction_ids: string[];
  business_identity: string;
  exact_scope: string;
};

type WorkbenchDirectCommitVisibilitySample = WorkbenchDirectCommitVisibilitySampleBinding & {
  canonical_read_us: number;
  browser_render_us: number;
  receipt_to_dom_us: number;
};

type WorkbenchDirectCommitVisibilityRun = {
  evidence_environment: "isolated_prod_equivalent_direct_canonical_get" | "production_smoke";
  production_p99_claim: boolean;
  sample_count: number;
  samples: WorkbenchDirectCommitVisibilitySample[];
  distributions_us: Record<string, { p50: number; p95: number; p99: number }>;
  receipt_to_dom_p99_us: number;
  slo_us: number;
  pass: boolean;
};

export type WorkbenchDirectCommitVisibilityRecorder = {
  startAtMutationReceipt: (binding: WorkbenchDirectCommitVisibilitySampleBinding) => {
    markCanonicalReadVisible: () => void;
    markDomVisible: () => void;
    complete: () => WorkbenchDirectCommitVisibilitySample;
  };
  writeReport: () => Promise<void>;
};

const workbenchDirectCommitVisibilityReportPath = fileURLToPath(new URL(
  "../../../.planning/phases/40-performance-contract-hot-path-closure/40-workbench-direct-commit-visibility-p99.json",
  import.meta.url,
));

function monotonicMicroseconds() {
  return Math.round(performance.now() * 1_000);
}

function redact(value: string) {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function percentile(values: number[], fraction: number) {
  if (values.length === 0) throw new Error("cannot calculate a percentile without samples");
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1))];
}

function summarizeDirectCommitVisibilityRun(
  samples: WorkbenchDirectCommitVisibilitySample[],
  evidenceEnvironment: WorkbenchDirectCommitVisibilityRun["evidence_environment"],
): WorkbenchDirectCommitVisibilityRun {
  const fields = {
    canonical_read_us: samples.map((sample) => sample.canonical_read_us),
    browser_render_us: samples.map((sample) => sample.browser_render_us),
    receipt_to_dom_us: samples.map((sample) => sample.receipt_to_dom_us),
  };
  const distributionsUs = Object.fromEntries(Object.entries(fields).map(([name, values]) => [name, {
    p50: percentile(values, 0.50),
    p95: percentile(values, 0.95),
    p99: percentile(values, 0.99),
  }]));
  const receiptToDomP99 = distributionsUs.receipt_to_dom_us.p99;
  return {
    evidence_environment: evidenceEnvironment,
    production_p99_claim: false,
    sample_count: samples.length,
    samples,
    distributions_us: distributionsUs,
    receipt_to_dom_p99_us: receiptToDomP99,
    slo_us: 3_000_000,
    pass: receiptToDomP99 <= 3_000_000,
  };
}

export function createWorkbenchDirectCommitVisibilityRecorder(
  mode: WorkbenchDirectCommitVisibilityRunMode,
  requestedSampleCount: number,
): WorkbenchDirectCommitVisibilityRecorder {
  const samples: WorkbenchDirectCommitVisibilitySample[] = [];
  return {
    startAtMutationReceipt(binding) {
      if (!binding.exact_scope || binding.exact_scope === "all") {
        throw new Error("an exact non-all scope is required");
      }
      const mutationReceiptAt = monotonicMicroseconds();
      let canonicalReadAt: number | null = null;
      let domVisibleAt: number | null = null;
      return {
        markCanonicalReadVisible: () => {
          if (canonicalReadAt !== null) throw new Error("canonical read was already recorded");
          canonicalReadAt = monotonicMicroseconds();
        },
        markDomVisible: () => {
          if (domVisibleAt !== null) throw new Error("DOM visibility was already recorded");
          domVisibleAt = monotonicMicroseconds();
        },
        complete: () => {
          if (canonicalReadAt === null || domVisibleAt === null) {
            throw new Error("canonical read and DOM visibility must both be recorded");
          }
          if (!(mutationReceiptAt <= canonicalReadAt && canonicalReadAt <= domVisibleAt)) {
            throw new Error("Workbench direct commit visibility marks are not monotonic");
          }
          const canonicalReadUs = canonicalReadAt - mutationReceiptAt;
          const browserRenderUs = domVisibleAt - canonicalReadAt;
          const receiptToDomUs = domVisibleAt - mutationReceiptAt;
          if (canonicalReadUs + browserRenderUs !== receiptToDomUs) {
            throw new Error("direct commit visibility segments do not equal receipt-to-DOM total");
          }
          const sample: WorkbenchDirectCommitVisibilitySample = {
            sample_id: redact(binding.sample_id),
            batch_id: redact(binding.batch_id),
            transaction_ids: binding.transaction_ids.map(redact),
            business_identity: redact(binding.business_identity),
            exact_scope: redact(binding.exact_scope),
            canonical_read_us: canonicalReadUs,
            browser_render_us: browserRenderUs,
            receipt_to_dom_us: receiptToDomUs,
          };
          samples.push(sample);
          return sample;
        },
      };
    },
    async writeReport() {
      if (mode === "isolated" && (requestedSampleCount < 100 || samples.length < requestedSampleCount)) {
        throw new Error("isolated Workbench direct commit visibility evidence requires at least 100 complete samples");
      }
      if (mode === "production_smoke" && (requestedSampleCount !== 1 || samples.length !== 1)) {
        throw new Error("production Workbench direct commit visibility smoke requires exactly one sample");
      }
      let existing: Record<string, unknown> = {};
      try {
        existing = JSON.parse(await readFile(workbenchDirectCommitVisibilityReportPath, "utf-8")) as Record<string, unknown>;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
      const report: Record<string, unknown> = {
        version: 2,
        generated_at: new Date().toISOString(),
        isolated: mode === "isolated"
          ? summarizeDirectCommitVisibilityRun(samples, "isolated_prod_equivalent_direct_canonical_get")
          : existing.isolated,
        production_smoke: mode === "production_smoke"
          ? summarizeDirectCommitVisibilityRun(samples, "production_smoke")
          : existing.production_smoke,
      };
      const isolated = report.isolated as WorkbenchDirectCommitVisibilityRun | undefined;
      if (mode === "production_smoke" && (
        !isolated
        || isolated.evidence_environment !== "isolated_prod_equivalent_direct_canonical_get"
        || isolated.sample_count < 100
        || !isolated.pass
      )) {
        throw new Error("production smoke cannot replace missing or failed isolated p99 evidence");
      }
      const temporaryPath = `${workbenchDirectCommitVisibilityReportPath}.${process.pid}.tmp`;
      await writeFile(temporaryPath, `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
      await rename(temporaryPath, workbenchDirectCommitVisibilityReportPath);
      if (mode === "isolated" && !(report.isolated as WorkbenchDirectCommitVisibilityRun).pass) {
        throw new Error("Workbench browser-inclusive direct total p99 exceeds 3000ms");
      }
    },
  };
}
