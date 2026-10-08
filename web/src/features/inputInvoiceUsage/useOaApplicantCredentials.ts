import { useEffect, useState } from "react";
import { deleteOaApplicantCredential, loadOaApplicantCredentials, saveOaApplicantCredential, type OaApplicantCredential, type OaApplicantCredentialDraft, type OaApplicantUser } from "./oaApplicantCredentials";

export function useOaApplicantCredentials(open: boolean, onChanged: (deletedCode?: string) => void, onSaved: () => void) {
  const [credentials, setCredentials] = useState<OaApplicantCredential[]>([]);
  const [users, setUsers] = useState<OaApplicantUser[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) { setCredentials([]); setUsers([]); setLoaded(false); setLoading(false); setError(""); return; }
    const controller = new AbortController();
    setLoading(true); setLoaded(false); setError("");
    loadOaApplicantCredentials(controller.signal).then(result => {
      if (!controller.signal.aborted) { setCredentials(result.credentials); setUsers(result.users); setLoaded(true); }
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "申请人加载失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, revision]);
  const save = async (draft: OaApplicantCredentialDraft, existing: OaApplicantCredential | null) => {
    setBusy(true); setError("");
    try { await saveOaApplicantCredential(draft, existing); onChanged(); onSaved(); return true; }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); return false; }
    finally { setBusy(false); }
  };
  const remove = async (credential: OaApplicantCredential) => {
    setBusy(true); setError("");
    try {
      await deleteOaApplicantCredential(credential);
      setCredentials(current => current.filter(item => item.targetApplicantCode !== credential.targetApplicantCode));
      onChanged(credential.targetApplicantCode); return true;
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败"); return false; }
    finally { setBusy(false); }
  };
  return { credentials, users, loaded, loading, busy, error, save, remove, reload: () => setRevision(value => value + 1) };
}
