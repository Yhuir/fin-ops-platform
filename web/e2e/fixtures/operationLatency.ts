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

export type WorkbenchVisibilityRunMode = "isolated" | "production_smoke";

export type WorkbenchVisibilitySampleBinding = {
  sample_id: string;
  batch_id: string;
  transaction_ids: string[];
  business_identity: string;
  exact_scope: string;
};

type WorkbenchVisibilityMarks = {
  t0: number;
  t1: number | null;
  t2: number | null;
  t3: number | null;
  t4: number | null;
};

type WorkbenchVisibilitySample = WorkbenchVisibilitySampleBinding & {
  g0: string;
  g1: string;
  marks: Required<WorkbenchVisibilityMarks>;
  segmentsMicroseconds: {
    canonicalCommit: number;
    statusProofEnqueue: number;
    workerPublish: number;
    browserReloadRender: number;
  };
  segmentSumMicroseconds: number;
  totalMicroseconds: number;
};

type WorkbenchVisibilityRun = {
  sample_count: number;
  samples: WorkbenchVisibilitySample[];
  distributionsMicroseconds: Record<string, { p50: number; p95: number; p99: number }>;
  total_p99_microseconds: number;
  slo_microseconds: number;
  pass: boolean;
};

export type WorkbenchVisibilitySegmentRecorder = {
  start: (binding: WorkbenchVisibilitySampleBinding, g0: string) => {
    markT1: () => void;
    markT2: () => void;
    markT3: (g1: string) => void;
    markT4: () => void;
    complete: () => WorkbenchVisibilitySample;
  };
  writeReport: () => Promise<void>;
};

const workbenchVisibilityReportPath = fileURLToPath(new URL(
  "../../../.planning/phases/40-performance-contract-hot-path-closure/40-workbench-visibility-p99.json",
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

function summarizeVisibilityRun(samples: WorkbenchVisibilitySample[]): WorkbenchVisibilityRun {
  const fields = {
    canonicalCommit: samples.map((sample) => sample.segmentsMicroseconds.canonicalCommit),
    statusProofEnqueue: samples.map((sample) => sample.segmentsMicroseconds.statusProofEnqueue),
    workerPublish: samples.map((sample) => sample.segmentsMicroseconds.workerPublish),
    browserReloadRender: samples.map((sample) => sample.segmentsMicroseconds.browserReloadRender),
    total: samples.map((sample) => sample.totalMicroseconds),
  };
  const distributionsMicroseconds = Object.fromEntries(Object.entries(fields).map(([name, values]) => [name, {
    p50: percentile(values, 0.50),
    p95: percentile(values, 0.95),
    p99: percentile(values, 0.99),
  }]));
  const totalP99 = distributionsMicroseconds.total.p99;
  return {
    sample_count: samples.length,
    samples,
    distributionsMicroseconds,
    total_p99_microseconds: totalP99,
    slo_microseconds: 3_000_000,
    pass: totalP99 <= 3_000_000,
  };
}

export function createWorkbenchVisibilitySegmentRecorder(
  mode: WorkbenchVisibilityRunMode,
  requestedSampleCount: number,
): WorkbenchVisibilitySegmentRecorder {
  const samples: WorkbenchVisibilitySample[] = [];
  return {
    start(binding, g0) {
      if (!g0 || binding.exact_scope === "all") throw new Error("baseline generation and exact scope are required");
      const marks: WorkbenchVisibilityMarks = { t0: monotonicMicroseconds(), t1: null, t2: null, t3: null, t4: null };
      let g1 = "";
      const mark = (name: "t1" | "t2" | "t3" | "t4") => {
        if (marks[name] !== null) throw new Error(`${name} was already recorded`);
        marks[name] = monotonicMicroseconds();
      };
      return {
        markT1: () => mark("t1"),
        markT2: () => mark("t2"),
        markT3: (activeGenerationId) => {
          if (!activeGenerationId || activeGenerationId === g0) throw new Error("t3 requires a new active generation");
          g1 = activeGenerationId;
          mark("t3");
        },
        markT4: () => mark("t4"),
        complete: () => {
          if (Object.values(marks).some((value) => value === null) || !g1) throw new Error("t0..t4 and g0..g1 must be complete");
          const completeMarks = marks as Required<WorkbenchVisibilityMarks>;
          if (!(completeMarks.t0 <= completeMarks.t1 && completeMarks.t1 <= completeMarks.t2
            && completeMarks.t2 <= completeMarks.t3 && completeMarks.t3 <= completeMarks.t4)) {
            throw new Error("Workbench visibility marks are not monotonic");
          }
          const segmentsMicroseconds = {
            canonicalCommit: completeMarks.t1 - completeMarks.t0,
            statusProofEnqueue: completeMarks.t2 - completeMarks.t1,
            workerPublish: completeMarks.t3 - completeMarks.t2,
            browserReloadRender: completeMarks.t4 - completeMarks.t3,
          };
          const segmentSumMicroseconds = Object.values(segmentsMicroseconds).reduce((sum, value) => sum + value, 0);
          const totalMicroseconds = completeMarks.t4 - completeMarks.t0;
          if (segmentSumMicroseconds !== totalMicroseconds) throw new Error("segment sum does not equal total");
          const sample: WorkbenchVisibilitySample = {
            sample_id: redact(binding.sample_id),
            batch_id: redact(binding.batch_id),
            transaction_ids: binding.transaction_ids.map(redact),
            business_identity: redact(binding.business_identity),
            exact_scope: redact(binding.exact_scope),
            g0,
            g1,
            marks: completeMarks,
            segmentsMicroseconds,
            segmentSumMicroseconds,
            totalMicroseconds,
          };
          samples.push(sample);
          return sample;
        },
      };
    },
    async writeReport() {
      if (mode === "isolated" && (requestedSampleCount < 100 || samples.length < requestedSampleCount)) {
        throw new Error("isolated Workbench visibility evidence requires at least 100 complete samples");
      }
      if (mode === "production_smoke" && (requestedSampleCount !== 1 || samples.length !== 1)) {
        throw new Error("production Workbench visibility smoke requires exactly one sample");
      }
      let existing: Record<string, unknown> = {};
      try {
        existing = JSON.parse(await readFile(workbenchVisibilityReportPath, "utf-8")) as Record<string, unknown>;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
      const report: Record<string, unknown> = {
        version: 1,
        generated_at: new Date().toISOString(),
        isolated: mode === "isolated" ? summarizeVisibilityRun(samples) : existing.isolated,
        production_smoke: mode === "production_smoke" ? summarizeVisibilityRun(samples) : existing.production_smoke,
      };
      const isolated = report.isolated as WorkbenchVisibilityRun | undefined;
      if (mode === "production_smoke" && (!isolated || isolated.sample_count < 100 || !isolated.pass)) {
        throw new Error("production smoke cannot replace missing or failed isolated p99 evidence");
      }
      if (mode === "isolated" && !(report.isolated as WorkbenchVisibilityRun).pass) {
        throw new Error("Workbench browser-inclusive total p99 exceeds 3000ms");
      }
      const temporaryPath = `${workbenchVisibilityReportPath}.${process.pid}.tmp`;
      await writeFile(temporaryPath, `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
      await rename(temporaryPath, workbenchVisibilityReportPath);
    },
  };
}
