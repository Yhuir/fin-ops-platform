import { Alert } from "@heroui/react";
import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  confirmImportFiles,
  discardImportSession,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import type { ImportSessionPayload } from "../../features/imports/types";
import type { BankAccountMapping } from "../../features/workbench/types";
import ManualBankTransactionBatchEditor from "./ManualBankTransactionBatchEditor";

type ManualBankTransactionEntryDrawerProps = {
  bankAccounts: BankAccountMapping[];
  disabled?: boolean;
  open: boolean;
  onClose: () => void;
  onImportAccepted: (payload: ImportSessionPayload) => void;
};

export default function ManualBankTransactionEntryDrawer({
  bankAccounts,
  disabled = false,
  open,
  onClose,
  onImportAccepted,
}: ManualBankTransactionEntryDrawerProps) {
  const [completed, setCompleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  const [previewSessionId, setPreviewSessionId] = useState<string | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [editorKey, setEditorKey] = useState(0);

  useEffect(() => {
    if (!open) {
      setCompleted(false);
      setPreviewSessionId(null);
      setCloseError(null);
      setEditorKey((current) => current + 1);
    }
  }, [open]);

  async function closeDrawer() {
    setCloseError(null);
    if (closing || busy) return;
    setClosing(true);
    if (previewSessionId) {
      try {
        await discardImportSession(previewSessionId);
      } catch (caught) {
        setCloseError(resolveImportApiErrorMessage(caught, "放弃预览失败，抽屉已保留。"));
        setClosing(false);
        return;
      }
    }
    setPreviewSessionId(null);
    setClosing(false);
    onClose();
  }

  return (
    <AppDrawer
      completion={completed ? "流水录入已提交" : undefined}
      closeDisabled={busy || closing}
      className="manual-bank-entry"
      closeLabel="关闭流水录入"
      onClose={() => { void closeDrawer(); }}
      open={open}
      title="流水录入"
      width="min(760px, 100vw)"
    >
      {closeError ? <Alert className="manual-bank-entry__notice manual-bank-entry__notice--danger">{closeError}</Alert> : null}
      <ManualBankTransactionBatchEditor
        bankAccounts={bankAccounts}
        disabled={disabled}
        key={editorKey}
        onBusyChange={setBusy}
        onPreviewSessionChange={setPreviewSessionId}
        onSubmit={async (preview) => {
          const payload = await confirmImportFiles(preview.importSession.session.id, preview.fileIds);
          setPreviewSessionId(null);
          onImportAccepted(payload);
          setCompleted(true);
        }}
      />
    </AppDrawer>
  );
}
