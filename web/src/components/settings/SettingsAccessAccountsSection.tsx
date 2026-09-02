import { Button, Checkbox, Input } from "@heroui/react";
import { Search, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { assignablePageOptions } from "../../app/pageRegistry";
import type { WorkbenchAccessUser } from "../../features/workbench/types";
import type { SettingsAccessAccountsSectionProps } from "./types";

const OA_SEARCH_DELAY_MS = 250;

export default function SettingsAccessAccountsSection({
  controlsDisabled,
  administrator,
  managedAccessAccounts,
  isLoading,
  isSaving,
  status,
  validationMessage,
  onAddAccessAccount,
  onSearchAccessUsers,
  onUpdateManagedAccessAccount,
  onDeleteManagedAccessAccount,
  onSave,
}: SettingsAccessAccountsSectionProps) {
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<WorkbenchAccessUser[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const selectedAccount = managedAccessAccounts.find((account) => account.id === selectedAccountId)
    ?? managedAccessAccounts[0]
    ?? null;

  useEffect(() => {
    if (selectedAccountId && managedAccessAccounts.some((account) => account.id === selectedAccountId)) return;
    setSelectedAccountId(managedAccessAccounts[0]?.id ?? null);
  }, [managedAccessAccounts, selectedAccountId]);

  useEffect(() => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setResults([]);
      setSearchError(null);
      setIsSearching(false);
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setIsSearching(true);
      setSearchError(null);
      onSearchAccessUsers(normalizedQuery, controller.signal)
        .then((users) => {
          if (controller.signal.aborted) return;
          const existing = new Set(managedAccessAccounts.map((account) => account.username));
          setResults(users.filter((user) => !existing.has(user.username) && user.username !== administrator?.username));
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setResults([]);
            setSearchError("OA 账户查询失败，请稍后重试。");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsSearching(false);
        });
    }, OA_SEARCH_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [administrator?.username, managedAccessAccounts, onSearchAccessUsers, query]);

  const pageGroups = useMemo(() => [
    { key: "finance", label: "财务业务", pages: assignablePageOptions.filter((page) => page.group === "finance") },
    { key: "system", label: "系统操作", pages: assignablePageOptions.filter((page) => page.group === "system") },
  ], []);

  const updateSelectedPages = (pageKeys: string[]) => {
    if (!selectedAccount) return;
    onUpdateManagedAccessAccount(selectedAccount.id, (account) => ({
      ...account,
      pageKeys: [...new Set(pageKeys)].sort(),
    }));
  };

  const addUser = (user: WorkbenchAccessUser) => {
    if (!user.active || controlsDisabled) return;
    onAddAccessAccount(user);
    setSelectedAccountId(`access-${user.username}`);
    setQuery("");
    setResults([]);
  };

  return (
    <section aria-labelledby="settings-section-access-accounts-title" className="settings-section-panel settings-access-section" id="settings-section-access-accounts" role="region">
      <header className="settings-section-header settings-access-header">
        <h3 id="settings-section-access-accounts-title">访问账户</h3>
        <div className="settings-access-admin-inline" aria-label="权限管理员">
          <ShieldCheck aria-hidden="true" size={16} />
          <span><strong>{administrator?.username ?? "005"}</strong><small>{administrator?.displayName || "权限管理员"}</small></span>
        </div>
      </header>

      {status ? <div className={`settings-inline-alert settings-inline-alert--${status.tone}`} role={status.tone === "error" ? "alert" : "status"}>{status.message}</div> : null}
      {validationMessage ? <div className="settings-inline-alert settings-inline-alert--error" role="alert">{validationMessage}</div> : null}
      {isLoading ? <div className="settings-inline-alert settings-inline-alert--info" role="status">正在加载访问账户...</div> : null}

      <div className="settings-access-workspace">
        <aside className="settings-access-account-pane" aria-label="账户列表">
          <div className="settings-access-search">
            <Search aria-hidden="true" size={15} />
            <Input aria-label="搜索 OA 账户" disabled={controlsDisabled} placeholder="输入账户或姓名" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
          </div>
          {query.trim() ? (
            <div className="settings-access-search-results" role="listbox" aria-label="OA 账户搜索结果">
              {isSearching ? <span className="settings-access-search-state">正在查询 OA...</span> : null}
              {!isSearching && searchError ? <span className="settings-access-search-state settings-access-search-state--error">{searchError}</span> : null}
              {!isSearching && !searchError && results.length === 0 ? <span className="settings-access-search-state">未找到可新增的有效账户</span> : null}
              {results.map((user) => (
                <button key={user.username} aria-label={`新增账户 ${user.username}`} className="settings-access-search-result" disabled={!user.active || controlsDisabled} role="option" type="button" onClick={() => addUser(user)}>
                  <UserPlus aria-hidden="true" size={15} />
                  <span><strong>{user.username}</strong><small>{user.displayName || "未设置姓名"}</small></span>
                  {!user.active ? <em>已停用</em> : null}
                </button>
              ))}
            </div>
          ) : null}

          <div className="settings-access-account-list">
            {managedAccessAccounts.length === 0 ? <div className="settings-access-empty">暂无账户</div> : managedAccessAccounts.map((account) => (
              <div key={account.id} className={`settings-access-account-row${selectedAccount?.id === account.id ? " is-selected" : ""}`}>
                <Button className="settings-access-account-select" slot={null} variant="tertiary" onPress={() => setSelectedAccountId(account.id)}>
                  <strong>{account.username}</strong>
                  <small>{account.displayName || "OA 未返回姓名"}</small>
                  <span>{account.pageKeys.length} 个页面{account.oaStatus !== "active" ? " · OA 状态异常" : ""}</span>
                </Button>
                <Button aria-label={`删除账户 ${account.username}`} className="settings-access-delete" isDisabled={controlsDisabled} isIconOnly size="sm" variant="tertiary" onPress={() => onDeleteManagedAccessAccount(account.id)}>
                  <Trash2 aria-hidden="true" size={15} />
                </Button>
              </div>
            ))}
          </div>
        </aside>

        <div className="settings-access-page-pane" aria-label="页面访问权限">
          {selectedAccount ? (
            <>
              <div className="settings-access-page-toolbar">
                <div><strong>{selectedAccount.username}</strong><span>可访问页面</span></div>
                <div>
                  <Button isDisabled={controlsDisabled} size="sm" variant="tertiary" onPress={() => updateSelectedPages(assignablePageOptions.map((page) => page.pageKey))}>全选</Button>
                  <Button isDisabled={controlsDisabled} size="sm" variant="tertiary" onPress={() => updateSelectedPages([])}>清空</Button>
                </div>
              </div>
              <div className="settings-access-page-groups">
                {pageGroups.map((group) => (
                  <section key={group.key} className="settings-access-page-group" aria-labelledby={`settings-access-group-${group.key}`}>
                    <h4 id={`settings-access-group-${group.key}`}>{group.label}<span>{group.pages.filter((page) => selectedAccount.pageKeys.includes(page.pageKey)).length}/{group.pages.length}</span></h4>
                    <div className="settings-access-page-list">
                      {group.pages.map((page) => {
                        const selected = selectedAccount.pageKeys.includes(page.pageKey);
                        return (
                          <Checkbox key={page.pageKey} className="settings-access-page-checkbox" isDisabled={controlsDisabled} isSelected={selected} slot={null} onChange={() => updateSelectedPages(selected ? selectedAccount.pageKeys.filter((key) => key !== page.pageKey) : [...selectedAccount.pageKeys, page.pageKey])}>
                            <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>{page.label}</span>
                          </Checkbox>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            </>
          ) : <div className="settings-access-page-empty">请选择账户</div>}
        </div>
      </div>

      <footer className="settings-access-footer">
        <Button isDisabled={controlsDisabled || isLoading || isSaving || validationMessage !== null} isPending={isSaving} variant="primary" onPress={() => void onSave()}>
          {isSaving ? "保存中..." : "保存访问权限"}
        </Button>
      </footer>
    </section>
  );
}
