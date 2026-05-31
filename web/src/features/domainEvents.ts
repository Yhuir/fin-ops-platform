export const FINANCE_DOMAIN_EVENTS = {
  workbenchRelationUpdated: "workbenchRelationUpdated",
  bankTransactionCategoryUpdated: "bankTransactionCategoryUpdated",
  bankAutoTagRulesUpdated: "bankAutoTagRulesUpdated",
  turnoverRelationUpdated: "turnoverRelationUpdated",
  turnoverLedgerExtraUpdated: "turnoverLedgerExtraUpdated",
  invoiceFactUpdated: "invoiceFactUpdated",
  etcBusinessBatchUpdated: "etcBusinessBatchUpdated",
} as const;

export type FinanceDomainEventName = typeof FINANCE_DOMAIN_EVENTS[keyof typeof FINANCE_DOMAIN_EVENTS];

export type FinanceDomainEventDetail = {
  affectedMonths?: string[];
  affectedRowIds?: string[];
  source?: string;
  action?: string;
  relationId?: string;
  [key: string]: unknown;
};

export type FinanceDomainEvent = CustomEvent<FinanceDomainEventDetail>;

const FINANCE_DOMAIN_BROADCAST_CHANNEL = "finops:finance-domain-events";
const FINANCE_DOMAIN_EVENT_ORIGIN = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

let financeDomainBroadcastChannel: BroadcastChannel | null = null;
let financeDomainBroadcastSubscriberCount = 0;

function isFinanceDomainEventName(value: unknown): value is FinanceDomainEventName {
  return typeof value === "string" && Object.values(FINANCE_DOMAIN_EVENTS).includes(value as FinanceDomainEventName);
}

function normalizeEventDetail(value: unknown): FinanceDomainEventDetail {
  return value && typeof value === "object" ? value as FinanceDomainEventDetail : {};
}

function dispatchFinanceDomainEvent(eventName: FinanceDomainEventName, detail: FinanceDomainEventDetail): void {
  window.dispatchEvent(new CustomEvent(eventName, { detail }));
}

function ensureFinanceDomainBroadcastChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") {
    return null;
  }
  if (financeDomainBroadcastChannel) {
    return financeDomainBroadcastChannel;
  }
  financeDomainBroadcastChannel = new BroadcastChannel(FINANCE_DOMAIN_BROADCAST_CHANNEL);
  financeDomainBroadcastChannel.onmessage = (message) => {
    const payload = message.data as { eventName?: unknown; detail?: unknown; origin?: unknown } | undefined;
    if (!payload || payload.origin === FINANCE_DOMAIN_EVENT_ORIGIN || !isFinanceDomainEventName(payload.eventName)) {
      return;
    }
    dispatchFinanceDomainEvent(payload.eventName, normalizeEventDetail(payload.detail));
  };
  return financeDomainBroadcastChannel;
}

export function eventAffectedMonths(event: Event): string[] {
  const detail = event instanceof CustomEvent && event.detail && typeof event.detail === "object"
    ? event.detail as { affectedMonths?: unknown; affected_months?: unknown }
    : {};
  const rawMonths = Array.isArray(detail.affectedMonths)
    ? detail.affectedMonths
    : Array.isArray(detail.affected_months)
      ? detail.affected_months
      : [];
  return rawMonths.map((month) => String(month).trim()).filter(Boolean);
}

export function emitFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  detail: FinanceDomainEventDetail = {},
): void {
  dispatchFinanceDomainEvent(eventName, detail);
  ensureFinanceDomainBroadcastChannel()?.postMessage({
    eventName,
    detail,
    origin: FINANCE_DOMAIN_EVENT_ORIGIN,
  });
}

export function subscribeFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  handler: (event: FinanceDomainEvent) => void,
): () => void {
  const channel = ensureFinanceDomainBroadcastChannel();
  if (channel) {
    financeDomainBroadcastSubscriberCount += 1;
  }
  const eventHandler = (event: Event) => {
    handler(event as FinanceDomainEvent);
  };
  window.addEventListener(eventName, eventHandler);
  return () => {
    window.removeEventListener(eventName, eventHandler);
    if (channel) {
      financeDomainBroadcastSubscriberCount = Math.max(0, financeDomainBroadcastSubscriberCount - 1);
      if (financeDomainBroadcastSubscriberCount === 0 && financeDomainBroadcastChannel) {
        financeDomainBroadcastChannel.close();
        financeDomainBroadcastChannel = null;
      }
    }
  };
}
