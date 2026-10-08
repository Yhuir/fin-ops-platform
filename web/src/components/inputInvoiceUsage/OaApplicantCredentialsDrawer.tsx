import { AlertDialog, Button, Chip, ComboBox, Input, Label, ListBox, Table, TextField } from "@heroui/react";
import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import { applicantLabel, type OaApplicantCredential, type OaApplicantCredentialDraft } from "../../features/inputInvoiceUsage/oaApplicantCredentials";
import type { useOaApplicantCredentials } from "../../features/inputInvoiceUsage/useOaApplicantCredentials";
import "./oaApplicantCredentials.css";

type Props = ReturnType<typeof useOaApplicantCredentials> & { open: boolean; onClose: () => void };
const emptyDraft: OaApplicantCredentialDraft = { oaUserId: "", password: "", remark: "" };
export default function OaApplicantCredentialsDrawer({ open, onClose, credentials, users, loaded, loading, busy, error, save, remove, reload }: Props) {
  const [editing, setEditing] = useState<OaApplicantCredential | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [confirmation, setConfirmation] = useState<{ kind: "discard"; next: OaApplicantCredential | null | "close" | "reload" } | { kind: "delete"; credential: OaApplicantCredential } | null>(null);
  useEffect(() => { if (!open) { setDraft(emptyDraft); setEditing(null); setConfirmation(null); } }, [open]);
  const dirty = draft.password !== "" || draft.oaUserId !== (editing?.oaUserId ?? "") || draft.remark !== (editing?.remark ?? "");
  const select = (item: OaApplicantCredential | null) => { setEditing(item); setDraft({ oaUserId: item?.oaUserId ?? "", password: "", remark: item?.remark ?? "" }); };
  const request = (next: OaApplicantCredential | null | "close" | "reload") => {
    if (busy) return;
    if (dirty) setConfirmation({ kind: "discard", next });
    else if (next === "close") onClose();
    else if (next === "reload") { select(null); reload(); }
    else select(next);
  };
  const selectedUser = users.find(user => user.userId === draft.oaUserId);
  return <>
    <AppDrawer open={open} onClose={() => request("close")} title="OA 申请人凭据" closeLabel="关闭 OA 申请人凭据" width="min(760px, 100vw)" className="oa-credentials-drawer" closeDisabled={busy} isDismissable ariaBusy={loading || busy}
      footer={<div className="oa-credentials-actions"><Button variant="secondary" isDisabled={busy} onPress={() => request("close")}>返回反提</Button><Button variant="primary" isPending={busy} isDisabled={!loaded || loading || busy || !selectedUser?.active || draft.password.length === 0} onPress={() => void save(draft, editing)}>保存凭据</Button></div>}>
      <div className="oa-credentials-body">
        {error ? <div role="alert" className="oa-credentials-error">{error}<Button size="sm" variant="tertiary" isDisabled={busy || loading} onPress={() => request("reload")}>重新加载</Button></div> : null}
        {loading ? <div role="status">正在加载</div> : null}
        {loaded ? <>
          <div className="oa-credentials-toolbar"><Button size="sm" variant="secondary" isDisabled={busy} onPress={() => request(null)}>新增申请人</Button></div>
          <Table><Table.ScrollContainer><Table.Content aria-label="反提 OA 申请人凭据">
            <Table.Header><Table.Column isRowHeader>反提 OA 申请人</Table.Column><Table.Column>登录账号</Table.Column><Table.Column>状态</Table.Column><Table.Column>操作</Table.Column></Table.Header>
            <Table.Body renderEmptyState={() => "暂无申请人"}>{credentials.map(item => <Table.Row id={item.targetApplicantCode} key={item.targetApplicantCode}>
              <Table.Cell>{applicantLabel(item.targetApplicantName, item.remark)}</Table.Cell><Table.Cell>{item.oaUsername}</Table.Cell>
              <Table.Cell><Chip size="sm" color={item.verifiedAt && item.enabled ? "success" : "default"}>{!item.enabled ? "已停用" : item.verifiedAt ? "已验证" : "待验证"}</Chip></Table.Cell>
              <Table.Cell><div className="oa-credentials-row-actions"><Button size="sm" variant="tertiary" isDisabled={busy} onPress={() => request(item)}>编辑</Button><Button size="sm" variant="danger-soft" isIconOnly aria-label={`删除${applicantLabel(item.targetApplicantName, item.remark)}`} isDisabled={busy} onPress={() => setConfirmation({ kind: "delete", credential: item })}><Trash2 size={16} /></Button></div></Table.Cell>
            </Table.Row>)}</Table.Body>
          </Table.Content></Table.ScrollContainer></Table>
          <div className="oa-credentials-form">
            <ComboBox selectedKey={draft.oaUserId || null} onSelectionChange={key => setDraft(current => ({ ...current, oaUserId: key === null ? "" : String(key), password: "" }))} isDisabled={busy || Boolean(editing?.oaUserId)} disabledKeys={users.filter(user => !user.active).map(user => user.userId)} menuTrigger="focus">
              <Label>OA 申请人 / 登录账号</Label><ComboBox.InputGroup><Input /><ComboBox.Trigger /></ComboBox.InputGroup>
              <ComboBox.Popover><ListBox items={users} renderEmptyState={() => "无匹配账号"}>{user => <ListBox.Item id={user.userId} textValue={`${user.displayName} · ${user.username}`}><span>{user.displayName} · {user.username}</span>{!user.active ? <Chip size="sm">已停用</Chip> : null}</ListBox.Item>}</ListBox></ComboBox.Popover>
            </ComboBox>
            <TextField isDisabled={busy} value={draft.password} onChange={password => setDraft(current => ({ ...current, password }))}><Label>OA 登录密码</Label><Input type="password" autoComplete="new-password" /></TextField>
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
