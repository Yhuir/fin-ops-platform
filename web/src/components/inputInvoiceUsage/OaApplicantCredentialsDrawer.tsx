import { AlertDialog, Button, Chip, ComboBox, Input, Label, ListBox, Table, TextField } from "@heroui/react";
import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import { applicantLabel, type OaApplicantCredential, type OaApplicantCredentialDraft } from "../../features/inputInvoiceUsage/oaApplicantCredentials";
import type { useOaApplicantCredentials } from "../../features/inputInvoiceUsage/useOaApplicantCredentials";
import "./oaApplicantCredentials.css";

type Props = ReturnType<typeof useOaApplicantCredentials> & { open: boolean; onClose: () => void };
const emptyDraft: OaApplicantCredentialDraft = { oaUserId: "", password: "", remark: "" };
export default function OaApplicantCredentialsDrawer({ open, onClose, credentials, users, loaded, loading, usersLoaded, usersLoading, usersError, busy, error, save, remove, reload, clearError }: Props) {
  const [editing, setEditing] = useState<OaApplicantCredential | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [confirmation, setConfirmation] = useState<{ kind: "discard"; next: OaApplicantCredential | null | "close" | "reload" } | { kind: "delete"; credential: OaApplicantCredential } | null>(null);
  useEffect(() => { if (!open) { setDraft(emptyDraft); setEditing(null); setConfirmation(null); } }, [open]);
  const dirty = draft.password !== "" || (!editing && draft.oaUserId !== "") || draft.remark !== (editing?.remark ?? "");
  const select = (item: OaApplicantCredential | null) => { clearError(); setEditing(item); setDraft({ oaUserId: item?.oaUserId ?? "", password: "", remark: item?.remark ?? "" }); };
  const request = (next: OaApplicantCredential | null | "close" | "reload") => {
    if (busy) return;
    if (dirty) setConfirmation({ kind: "discard", next });
    else if (next === "close") onClose();
    else if (next === "reload") { select(null); reload(); }
    else select(next);
  };
  const matches = editing && !editing.oaUserId ? users.filter(user => user.username.toLowerCase() === editing.oaUsername.toLowerCase()) : [];
  const userId = editing ? editing.oaUserId ?? (matches.length === 1 && matches[0].active ? matches[0].userId : "") : draft.oaUserId;
  const selectedUser = users.find(user => user.userId === userId);
  const verified = Boolean(editing?.verifiedAt && editing.oaUserId);
  const hasSavedPassword = Boolean(editing?.hasCredential && editing.credentialStatus === "configured");
  const identityError = editing && !editing.oaUserId && usersLoaded && !userId ? "原登录账号不存在、已停用或无法唯一匹配，请检查 OA 账号。" : "";
  const otherCredentials = credentials.filter(item => item.targetApplicantCode !== editing?.targetApplicantCode);
  const configuredIds = new Set(otherCredentials.map(item => item.oaUserId).filter(id => id !== null));
  const legacyAccounts = new Set(otherCredentials.filter(item => !item.oaUserId).map(item => item.oaUsername.toLowerCase()));
  const disabledUserIds = users.filter(user => !user.active || configuredIds.has(user.userId)
    || legacyAccounts.has(user.username.toLowerCase()))
    .map(user => user.userId);
  const canSave = loaded && !busy && Boolean(userId) && (editing
    ? (!verified || dirty) && (hasSavedPassword || draft.password.length > 0)
    : usersLoaded && Boolean(selectedUser?.active) && !disabledUserIds.includes(userId) && draft.password.length > 0);
  const saveLabel = editing ? verified ? "保存修改" : "验证并保存" : "保存凭据";
  return <>
    <AppDrawer open={open} onClose={() => request("close")} title="OA 申请人凭据" closeLabel="关闭 OA 申请人凭据" width="min(760px, 100vw)" className="oa-credentials-drawer" closeDisabled={busy} isDismissable ariaBusy={loading || busy}
      footer={<div className="oa-credentials-actions">{editing ? <Button variant="tertiary" isDisabled={busy || !loaded} onPress={() => request(null)}>取消编辑</Button> : null}<Button variant="secondary" isDisabled={busy} onPress={() => request("close")}>返回反提</Button><Button variant="primary" isPending={busy} isDisabled={!canSave} onPress={() => void save({ ...draft, oaUserId: userId }, editing)}>{saveLabel}</Button></div>}>
      <div className="oa-credentials-body">
        {error ? <div role="alert" className="oa-credentials-error">{error}<Button size="sm" variant="tertiary" isDisabled={busy || loading} onPress={() => request("reload")}>重新加载</Button></div> : null}
        {usersError ? <div role="alert" className="oa-credentials-error">{usersError}<Button size="sm" variant="tertiary" isDisabled={busy || loading || usersLoading} onPress={() => request("reload")}>重新加载</Button></div> : null}
        {loading ? <div role="status">正在加载</div> : null}
        {loaded ? <>
          <Table><Table.ScrollContainer><Table.Content aria-label="反提 OA 申请人凭据">
            <Table.Header><Table.Column isRowHeader>反提 OA 申请人</Table.Column><Table.Column>登录账号</Table.Column><Table.Column>状态</Table.Column><Table.Column>操作</Table.Column></Table.Header>
            <Table.Body renderEmptyState={() => "暂无申请人"}>{credentials.map(item => <Table.Row id={item.targetApplicantCode} key={item.targetApplicantCode}>
              <Table.Cell>{applicantLabel(item.targetApplicantName, item.remark)}</Table.Cell><Table.Cell>{item.oaUsername}</Table.Cell>
              <Table.Cell><Chip size="sm" color={item.verifiedAt && item.oaUserId && item.enabled ? "success" : "default"}>{!item.enabled ? "已停用" : item.verifiedAt && item.oaUserId ? "已验证" : item.hasCredential ? "已保存 · 待验证" : "未配置密码"}</Chip></Table.Cell>
              <Table.Cell><div className="oa-credentials-row-actions"><Button size="sm" variant="tertiary" isDisabled={busy} onPress={() => request(item)}>编辑</Button><Button size="sm" variant="danger-soft" isIconOnly aria-label={`删除${applicantLabel(item.targetApplicantName, item.remark)}`} isDisabled={busy} onPress={() => setConfirmation({ kind: "delete", credential: item })}><Trash2 size={16} /></Button></div></Table.Cell>
            </Table.Row>)}</Table.Body>
          </Table.Content></Table.ScrollContainer></Table>
          <div className="oa-credentials-form">
            {editing ? <TextField isReadOnly value={`${editing.targetApplicantName} · ${editing.oaUsername}`}><Label>OA 申请人 / 登录账号</Label><Input /></TextField> :
            <ComboBox selectedKey={draft.oaUserId || null} onSelectionChange={key => setDraft(current => ({ ...current, oaUserId: key === null ? "" : String(key), password: "" }))} isDisabled={busy || !usersLoaded} disabledKeys={disabledUserIds} menuTrigger="focus">
              <Label>OA 申请人 / 登录账号</Label><ComboBox.InputGroup><Input /><ComboBox.Trigger /></ComboBox.InputGroup>
              <ComboBox.Popover><ListBox items={users} renderEmptyState={() => "无匹配账号"}>{user => <ListBox.Item id={user.userId} textValue={`${user.displayName} · ${user.username}`}><span>{user.displayName} · {user.username}</span>{!user.active ? <Chip size="sm">已停用</Chip> : null}</ListBox.Item>}</ListBox></ComboBox.Popover>
            </ComboBox>}
            {usersLoading && (!editing || !editing.oaUserId) ? <div role="status" className="oa-credentials-hint">正在读取 OA 账号</div> : null}
            {identityError ? <div role="alert" className="oa-credentials-error">{identityError}</div> : null}
            <TextField isDisabled={busy} value={draft.password} onChange={password => setDraft(current => ({ ...current, password }))}><Label>OA 登录密码</Label><Input type="password" autoComplete="new-password" aria-describedby={hasSavedPassword ? "oa-credentials-password-hint" : undefined} /></TextField>
            {hasSavedPassword ? <p id="oa-credentials-password-hint" className="oa-credentials-hint">{verified ? "密码已保存，留空保留原密码。" : "密码已保存，留空使用原密码验证。"}</p> : null}
            <TextField isDisabled={busy} value={draft.remark} onChange={remark => setDraft(current => ({ ...current, remark }))}><Label>备注（选填）</Label><Input maxLength={100} /></TextField>
          </div>
        </> : null}
      </div>
    </AppDrawer>
    <AlertDialog.Backdrop isOpen={confirmation !== null} onOpenChange={value => { if (!value && !busy) setConfirmation(null); }}>
      <AlertDialog.Container size="sm"><AlertDialog.Dialog><AlertDialog.Header><AlertDialog.Heading>{confirmation?.kind === "delete" ? "删除反提 OA 申请人？" : "放弃未保存的修改？"}</AlertDialog.Heading></AlertDialog.Header>
        {confirmation?.kind === "delete" ? <AlertDialog.Body>删除 {applicantLabel(confirmation.credential.targetApplicantName, confirmation.credential.remark)} 的凭据配置。历史记录保留，暂存批次将无法继续使用此凭据。</AlertDialog.Body> : null}
        <AlertDialog.Footer><Button variant="secondary" isDisabled={busy} onPress={() => setConfirmation(null)}>取消</Button><Button variant="danger" isPending={busy} isDisabled={busy} onPress={async () => {
          if (!confirmation) return;
          if (confirmation.kind === "delete") { const item = confirmation.credential; setConfirmation(null); if (await remove(item) && editing?.targetApplicantCode === item.targetApplicantCode) select(null); }
          else { const next = confirmation.next; setConfirmation(null); if (next === "close") onClose(); else if (next === "reload") { select(null); reload(); } else select(next); }
        }}>{confirmation?.kind === "delete" ? "删除" : "放弃修改"}</Button></AlertDialog.Footer>
      </AlertDialog.Dialog></AlertDialog.Container>
    </AlertDialog.Backdrop>
  </>;
}
