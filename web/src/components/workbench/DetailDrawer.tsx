import type { ComponentProps } from "react";
import SourceDetailDrawer from "../../features/SourceDetailDrawer";
import type { WorkbenchRecord } from "../../features/workbench/types";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onBankSplitSaved?: ComponentProps<typeof SourceDetailDrawer>["onBankSplitSaved"];
};

export default function DetailDrawer({ row, loading, error, onClose, onBankSplitSaved }: DetailDrawerProps) {
  return <SourceDetailDrawer open={Boolean(row)} target={row ? { kind: row.recordType, id: row.id } : null}
    sections={row?.sourceSections ?? []} loading={loading} error={error}
    onClose={onClose} onBankSplitSaved={onBankSplitSaved} />;
}
