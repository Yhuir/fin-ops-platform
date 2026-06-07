import { useEffect, useState } from "react";

import type { OutputInvoiceCollectionStatusRulesResponse } from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

type CollectionStatusRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<OutputInvoiceCollectionStatusRulesResponse>;
  onClose: () => void;
};

export default function CollectionStatusRulesDrawer({
  open,
  loadRules,
  onClose,
}: CollectionStatusRulesDrawerProps) {
  const [payload, setPayload] = useState<OutputInvoiceCollectionStatusRulesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收款状态规则加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadRules, open]);

  return (
    <AppDrawer
      className="output-invoice-collection-drawer output-invoice-collection-drawer--wide"
      closeLabel="关闭收款状态规则"
      onClose={onClose}
      open={open}
      subtitle="Sheet6 静态规则，只读展示"
      title="收款状态规则"
      width="min(900px, 58vw)"
    >
      <div className="output-invoice-collection-drawer__body">
        {loading ? (
          <div aria-label="正在加载收款状态规则">
            <StatePanel compact tone="loading" title="正在读取规则" />
          </div>
        ) : null}
        {error ? <StatePanel compact tone="error">{error}</StatePanel> : null}
        {payload ? (
          <>
            <div className="output-invoice-collection-tag-strip">
              {payload.version ? <span className="output-invoice-collections-table-tag">版本 {payload.version}</span> : null}
              <span className="output-invoice-collections-table-tag output-invoice-collections-table-tag--info">只读</span>
            </div>
            <div className="output-invoice-collection-rules-table-frame">
              <table aria-label="Sheet6 销项发票收款情况规则" className="output-invoice-collection-rules-table">
                <thead>
                  <tr>
                    <th scope="col">收款状态</th>
                    <th scope="col">识别方式</th>
                    <th scope="col">规则</th>
                    <th scope="col">必要事实</th>
                    <th scope="col">优先级</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.rules.map((rule) => (
                    <tr key={rule.id || rule.code || rule.label}>
                      <td className="output-invoice-collection-rules-table__strong">{rule.label}</td>
                      <td>{rule.recognitionMode || "未注明"}</td>
                      <td>
                        <span className="output-invoice-collection-rules-table__description">{rule.description}</span>
                        {rule.workbenchRequirement ? (
                          <span className="output-invoice-collection-rules-table__muted">{rule.workbenchRequirement}</span>
                        ) : null}
                      </td>
                      <td>{(rule.requiredFacts ?? []).join(" / ") || "—"}</td>
                      <td>{rule.priority}</td>
                    </tr>
                  ))}
                  {payload.rules.length === 0 ? (
                    <tr>
                      <td colSpan={5}>暂无规则。</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            {payload.futureWriteBoundary ? (
              <section className="output-invoice-collection-detail-card">
                <h3>后续服务边界</h3>
                <div className="output-invoice-collection-boundary-list">
                  {Object.entries(payload.futureWriteBoundary).map(([key, value]) => (
                    <p key={key}>{key}: {String(value)}</p>
                  ))}
                </div>
              </section>
            ) : null}
          </>
        ) : null}
      </div>
    </AppDrawer>
  );
}
