import type { CostTransactionDetail } from "../../features/cost-statistics/types";
import CostTransactionDetailPanel from "./CostTransactionDetailPanel";

type CostTransactionDetailModalProps = {
  detail: CostTransactionDetail["transaction"];
  onClose: () => void;
};

export default function CostTransactionDetailModal({ detail, onClose }: CostTransactionDetailModalProps) {
  return (
    <div className="cost-detail-modal-layer" role="presentation">
      <button
        aria-label="关闭流水详情"
        className="cost-detail-modal-backdrop"
        type="button"
        onClick={onClose}
      />
      <section aria-modal="true" className="cost-detail-modal" role="dialog" aria-labelledby="cost-detail-modal-title">
        <header className="cost-detail-modal-header">
          <div>
            <h2 id="cost-detail-modal-title">流水详情</h2>
            <p>查看当前成本流水对应的项目归属、费用分类和银行原始字段。</p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="cost-detail-modal-body">
          <CostTransactionDetailPanel detail={detail} />
        </div>
      </section>
    </div>
  );
}
