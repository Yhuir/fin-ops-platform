import { useEffect, useRef } from "react";

import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import {
  subscribeFinanceDomainEvent,
  type FinanceDomainEvent,
  type FinanceDomainEventName,
} from "../features/domainEvents";

export function useActiveFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  handler: (event: FinanceDomainEvent) => void,
) {
  const { active } = useOptionalPageActivation();
  const activeRef = useRef(active);
  const handlerRef = useRef(handler);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => (
    subscribeFinanceDomainEvent(eventName, (event) => {
      if (activeRef.current && document.visibilityState !== "hidden") {
        handlerRef.current(event);
      }
    })
  ), [eventName]);
}
