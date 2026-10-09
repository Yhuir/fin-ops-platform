import { useCallback, useRef, useState } from 'react';

// A list response owns the expansion. Replacing it invalidates the old members.
export function useRelationExpansion(rows: readonly unknown[]) {
  const [selection, setSelection] = useState<{ rows: typeof rows; id: string; expanded: boolean } | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const current = selection?.rows === rows ? selection : null;
  const toggle = useCallback((id: string) => {
    setSelection(previous => {
      if (previous?.rows === rows && previous.id === id) {
        if (previous.expanded) opener.current?.focus({ preventScroll: true });
        return { ...previous, expanded: !previous.expanded };
      }
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      return { rows, id, expanded: true };
    });
  }, [rows]);
  const exited = useCallback(() => {
    setSelection(previous => previous?.expanded ? previous : null);
    if (document.activeElement === document.body) opener.current?.focus({ preventScroll: true });
  }, []);
  return { rowId: current?.id ?? null, expanded: current?.expanded ?? false, toggle, exited };
}
