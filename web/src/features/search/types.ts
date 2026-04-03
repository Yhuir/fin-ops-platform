export type WorkbenchSearchScope = "all" | "oa" | "bank" | "invoice";

export type WorkbenchSearchStatus = "all" | "paired" | "open" | "ignored" | "processed_exception";

export type WorkbenchSearchZoneHint = "paired" | "open" | "ignored" | "processed_exception";

export type WorkbenchSearchRecordType = "oa" | "bank" | "invoice";

export type WorkbenchSearchJumpTarget = {
  month: string;
  rowId: string;
  zoneHint: WorkbenchSearchZoneHint;
  recordType: WorkbenchSearchRecordType;
};

export type WorkbenchSearchResult = {
  rowId: string;
  recordType: WorkbenchSearchRecordType;
  month: string;
  zoneHint: WorkbenchSearchZoneHint;
  matchedField: string;
  title: string;
  primaryMeta: string;
  secondaryMeta: string;
  statusLabel: string;
  jumpTarget: WorkbenchSearchJumpTarget;
};

export type WorkbenchSearchSummary = {
  total: number;
  oa: number;
  bank: number;
  invoice: number;
};

export type WorkbenchSearchResponse = {
  query: string;
  summary: WorkbenchSearchSummary;
  oaResults: WorkbenchSearchResult[];
  bankResults: WorkbenchSearchResult[];
  invoiceResults: WorkbenchSearchResult[];
};
