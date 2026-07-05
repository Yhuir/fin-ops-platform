import { writeFile } from "node:fs/promises";

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
