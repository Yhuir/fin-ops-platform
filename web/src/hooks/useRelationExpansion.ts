import { useCallback, useRef, useState } from 'react';

type RelationExpansionView = 'invoices' | 'sources';

// A list response owns the expansion. Replacing it invalidates the old members.
export function useRelationExpansion(rows: readonly unknown[]) {
  const [selection, setSelection] = useState<{ rows: typeof rows; id: string; view: RelationExpansionView; expanded: boolean } | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const current = selection?.rows === rows ? selection : null;
  const toggle = useCallback((id: string, view: RelationExpansionView) => {
    setSelection(previous => {
      if (previous?.rows === rows && previous.id === id && previous.view === view) {
        if (previous.expanded) opener.current?.focus({ preventScroll: true });
        return { ...previous, expanded: !previous.expanded };
      }
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      return { rows, id, view, expanded: true };
    });
  }, [rows]);
  const rowId = current?.id ?? null;
  const view = current?.view ?? null;
  const exited = useCallback(() => {
    setSelection(previous => previous?.rows === rows && previous.id === rowId && previous.view === view && !previous.expanded ? null : previous);
    if (document.activeElement === document.body) opener.current?.focus({ preventScroll: true });
  }, [rows, rowId, view]);
  return { rowId, view, expanded: current?.expanded ?? false, toggle, exited };
}
